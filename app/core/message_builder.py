from datetime import UTC, datetime
from enum import StrEnum

from app.core.risk_engine import calculate_risk_reward, get_entry_price
from app.integrations.discord_payloads import risk_color
from app.schemas.alert import FinalDecision, RiskLevel
from app.schemas.tradingview import TradingViewSignal


def _truncate(value: str, max_length: int = 1000) -> str:
    if len(value) <= max_length:
        return value
    return value[: max_length - 3].rstrip() + "..."


def _format_price(value: float | None) -> str:
    return f"{value:.2f}" if value is not None else "No disponible"


def _format_source(source: StrEnum | str) -> str:
    labels = {
        "chart": "Gráfico",
        "indicators": "Indicadores",
        "fundamentals": "Fundamentos",
        "mixed": "Gráfico + indicadores / mixto",
    }
    return labels.get(str(source), str(source))


def _entry_text(signal: TradingViewSignal) -> str:
    if signal.resistance is not None and signal.close < signal.resistance:
        return f"Confirmaci\u00f3n sobre resistencia {_format_price(signal.resistance)}"
    if signal.resistance is not None and signal.close >= signal.resistance:
        return f"Entrada estimada a precio actual tras ruptura {_format_price(signal.close)}"
    if signal.sma30 is not None:
        return f"Arriba de SMA30 {_format_price(signal.sma30)}"
    return f"Zona t\u00e9cnica relevante / precio actual {_format_price(signal.close)}"

def _target_text(signal: TradingViewSignal) -> str:
    if signal.target is not None:
        return _format_price(signal.target)
    if signal.resistance is not None:
        return f"Próxima resistencia {_format_price(signal.resistance)}"
    return "Próxima resistencia"


def _stop_loss_text(signal: TradingViewSignal) -> str:
    if signal.stop_loss is not None:
        return _format_price(signal.stop_loss)
    if signal.support is not None:
        return f"Soporte técnico {_format_price(signal.support)}"
    if signal.sma30 is not None:
        return f"Pérdida de SMA30 {_format_price(signal.sma30)}"
    return "Soporte técnico / zona de invalidación"


def _technical_reading(signal: TradingViewSignal) -> str:
    readings: list[str] = []

    if signal.rsi is not None:
        if 50 <= signal.rsi <= 68:
            readings.append("RSI en zona compradora sana.")
        elif 68 < signal.rsi <= 72:
            readings.append("RSI alcista, aunque cerca de zona de precaución.")
        elif signal.rsi > 75:
            readings.append("RSI elevado, posible entrada extendida.")

    if (
        signal.koncorde_azul is not None
        and signal.koncorde_marron is not None
        and signal.koncorde_media is not None
        and signal.koncorde_azul > 0
        and signal.koncorde_marron > signal.koncorde_media
    ):
        readings.append("KONCORDE acompaña con presión compradora.")

    if (
        signal.ppo is not None
        and signal.ppo_signal is not None
        and signal.ppo_hist is not None
        and signal.ppo > signal.ppo_signal
        and signal.ppo_hist > 0
    ):
        readings.append("PPO-Min/Max confirma impulso positivo.")

    if signal.sma30 is not None and signal.close > signal.sma30:
        readings.append("Precio sobre SMA30.")

    if signal.ema150 is not None and signal.ema200 is not None:
        ema_avg = (signal.ema150 + signal.ema200) / 2
        if signal.close > ema_avg:
            readings.append("Precio sobre EMAs largas.")

    if not readings:
        return "Lectura técnica pendiente de confirmación."
    return " ".join(readings)


def _risk_reward_text(signal: TradingViewSignal) -> str:
    risk_reward = calculate_risk_reward(get_entry_price(signal), signal.target, signal.stop_loss)
    return f"{risk_reward:.2f}:1" if risk_reward is not None else "No disponible"


def _missing_signal_data(signal: TradingViewSignal) -> list[str]:
    missing: list[str] = []
    if signal.stop_loss is None:
        missing.append("stop loss")
    if signal.target is None:
        missing.append("objetivo")
    if signal.volume_ok is None:
        missing.append("volumen")
    return missing


def _decision_text(decision: FinalDecision) -> str:
    return "Compramos" if decision is FinalDecision.COMPRAMOS else "No compramos"


def _decision_icon(decision: FinalDecision) -> str:
    return "✅" if decision is FinalDecision.COMPRAMOS else "❌"


def _suggested_action(decision: FinalDecision) -> str:
    if decision is FinalDecision.COMPRAMOS:
        return "Revisar gráfico, CEDEAR, liquidez y definir ejecución."
    return "Mantener en observación o descartar según evolución."


def build_alert_message(signal: TradingViewSignal, score: int, risk: RiskLevel, watchlist: bool = False) -> str:
    missing = _missing_signal_data(signal)
    missing_text = f"\nDatos faltantes relevantes: {', '.join(missing)}." if missing else ""
    is_high_risk_signal = risk == RiskLevel.EXTREMO or _risk_reward_text(signal) == "No disponible"
    title = (
        f"\U0001f1fa\U0001f1f8 ${signal.ticker.upper()} - Watchlist fuera de horario \U0001f552"
        if watchlist
        else (
            f"${signal.ticker.upper()} - Se\u00f1al en observaci\u00f3n de alto riesgo \U0001f534"
            if is_high_risk_signal
            else f"\U0001f1fa\U0001f1f8 ${signal.ticker.upper()} - Alerta de Compra \u26a0\ufe0f"
        )
    )
    description = (
        "Oportunidad detectada fuera de horario. Estado: Watchlist para pr\u00f3xima rueda. No es alerta operativa."
        if watchlist
        else "Se detecta una posible condici\u00f3n de compra. La alerta queda en observaci\u00f3n hasta la confirmaci\u00f3n pre-cierre."
    )
    note = (
        "Nota: Mercado cerrado. Revisar en la pr\u00f3xima rueda. No es alerta operativa."
        if watchlist
        else "Nota: Esta alerta no decide la compra. La decisi\u00f3n final se toma 30 minutos antes del cierre."
    )

    return (
        f"{title}\n\n"
        f"{description}\n\n"
        f"Motivo de alerta: {_format_source(signal.source)}.\n"
        f"Lectura t\u00e9cnica: {_technical_reading(signal)}\n"
        f"Raz\u00f3n: {signal.reason}\n\n"
        f"RIESGO PRELIMINAR: {risk.value}\n"
        f"Score preliminar: {score}/100\n\n"
        f"ENTRADA: {_entry_text(signal)}\n"
        f"OBJ: {_target_text(signal)}\n"
        f"SL: {_stop_loss_text(signal)}\n"
        f"R/R: {_risk_reward_text(signal).lower()}\n"
        f"{missing_text}\n\n"
        f"{note}"
    )

def build_alert_embed(signal: TradingViewSignal, score: int, risk: RiskLevel, watchlist: bool = False) -> dict:
    fields = [
        {"name": "Motivo", "value": _truncate(_format_source(signal.source)), "inline": True},
        {"name": "Lectura t\u00e9cnica", "value": _truncate(_technical_reading(signal)), "inline": False},
        {"name": "Riesgo preliminar", "value": risk.value, "inline": True},
        {"name": "Score preliminar", "value": f"{score}/100", "inline": True},
        {"name": "Entrada", "value": _truncate(_entry_text(signal)), "inline": False},
        {"name": "Objetivo", "value": _truncate(_target_text(signal)), "inline": True},
        {"name": "Stop Loss", "value": _truncate(_stop_loss_text(signal)), "inline": True},
        {"name": "R/R", "value": _risk_reward_text(signal), "inline": True},
    ]
    missing = _missing_signal_data(signal)
    if missing:
        fields.append({"name": "Datos faltantes", "value": _truncate(", ".join(missing)), "inline": False})

    is_high_risk_signal = risk == RiskLevel.EXTREMO or _risk_reward_text(signal) == "No disponible"
    return {
        "title": (
            f"${signal.ticker.upper()} \u00b7 Watchlist fuera de horario \U0001f552"
            if watchlist
            else (
                f"${signal.ticker.upper()} \u00b7 Se\u00f1al en observaci\u00f3n de alto riesgo \U0001f534"
                if is_high_risk_signal
                else f"\U0001f1fa\U0001f1f8 ${signal.ticker.upper()} \u00b7 Alerta de Compra \u26a0\ufe0f"
            )
        ),
        "description": (
            "Oportunidad detectada fuera de horario. Estado: Watchlist para pr\u00f3xima rueda. No es alerta operativa."
            if watchlist
            else "Se detecta una posible condici\u00f3n de compra. La alerta queda en observaci\u00f3n hasta la confirmaci\u00f3n pre-cierre."
        ),
        "color": risk_color(risk),
        "fields": fields,
        "footer": {
            "text": (
                "Mercado cerrado. Revisar en la pr\u00f3xima rueda. No es alerta operativa."
                if watchlist
                else "La decisi\u00f3n final se toma 30 minutos antes del cierre. No ejecuta operaciones autom\u00e1ticamente."
            )
        },
        "timestamp": datetime.now(UTC).isoformat(),
    }

def build_pre_close_summary(items: list[tuple[str, FinalDecision, RiskLevel, str]]) -> str:
    lines = ["Alertas del Bot - Confirmación Pre-Cierre", ""]
    for ticker, decision, risk, reason in items:
        lines.append(f"* {_decision_icon(decision)} ${ticker.upper()} - {_decision_text(decision)}. Riesgo {risk.value.lower()}. {reason}")
    lines.extend(
        [
            "",
            "Nota: La confirmación se genera 30 minutos antes del cierre. No ejecuta operaciones automáticamente. El usuario debe revisar el gráfico, el precio del CEDEAR, la liquidez y decidir si ejecuta.",
        ]
    )
    return "\n".join(lines)


def _summary_line(ticker: str, decision: FinalDecision, risk: RiskLevel, reason: str) -> str:
    line = f"{_decision_icon(decision)} ${ticker.upper()} - {_decision_text(decision)}. Riesgo {risk.value.lower()}"
    if len(reason) <= 80:
        line = f"{line}. {reason}"
    return _truncate(line, max_length=180)


def build_pre_close_summary_embed(items: list[tuple[str, FinalDecision, RiskLevel, str]]) -> dict:
    buy_count = sum(1 for _ticker, decision, _risk, _reason in items if decision is FinalDecision.COMPRAMOS)
    no_buy_count = len(items) - buy_count
    lines = [_summary_line(ticker, decision, risk, reason) for ticker, decision, risk, reason in items]

    return {
        "title": "Alertas del Bot · Confirmación Pre-Cierre",
        "description": _truncate("Lista de decisiones:\n\n" + "\n".join(lines), max_length=1000),
        "color": 0x3498DB,
        "fields": [
            {"name": "Total alertas", "value": str(len(items)), "inline": True},
            {"name": "Compramos", "value": str(buy_count), "inline": True},
            {"name": "No compramos", "value": str(no_buy_count), "inline": True},
        ],
        "footer": {"text": "No ejecuta operaciones automáticamente."},
        "timestamp": datetime.now(UTC).isoformat(),
    }


def build_single_confirmation_message(
    ticker: str,
    decision: FinalDecision,
    risk: RiskLevel,
    reason: str,
    score: int,
    signal: TradingViewSignal | None = None,
) -> str:
    risk_reward = _risk_reward_text(signal) if signal is not None else "No disponible"
    details = ""
    if signal is not None:
        details = (
            f"Entrada estimada: {_entry_text(signal)}\n"
            f"Objetivo: {_target_text(signal)}\n"
            f"Stop loss: {_stop_loss_text(signal)}\n"
            f"R/R: {risk_reward}\n"
        )

    note = (
        "Nota: Esta confirmaci\u00f3n no ejecuta operaciones autom\u00e1ticamente. El usuario debe revisar el gr\u00e1fico, el precio del CEDEAR, la liquidez y decidir si ejecuta."
        if decision is FinalDecision.COMPRAMOS
        else "Nota: La alerta queda cerrada."
    )
    return (
        "Confirmaci\u00f3n Pre-Cierre\n\n"
        f"{_decision_icon(decision)} ${ticker.upper()} - {_decision_text(decision)}.\n"
        f"Riesgo final: {risk.value}\n"
        f"Score final: {score}/100\n"
        f"{details}"
        f"Raz\u00f3n: {reason}\n"
        f"Acci\u00f3n sugerida: {_suggested_action(decision)}\n\n"
        f"{note}"
    )

def build_single_confirmation_embed(
    ticker: str,
    decision: FinalDecision,
    risk: RiskLevel,
    reason: str,
    score: int,
    signal: TradingViewSignal | None = None,
) -> dict:
    title = f"{_decision_icon(decision)} ${ticker.upper()} \u00b7 Confirmaci\u00f3n pre-cierre: {_decision_text(decision)}"
    fields = []
    if decision is FinalDecision.COMPRAMOS and signal is not None:
        fields.extend(
            [
                {"name": "Entrada estimada", "value": _truncate(_entry_text(signal)), "inline": False},
                {"name": "Objetivo", "value": _truncate(_target_text(signal)), "inline": True},
                {"name": "Stop loss", "value": _truncate(_stop_loss_text(signal)), "inline": True},
                {"name": "R/R", "value": _risk_reward_text(signal), "inline": True},
                {"name": "Riesgo", "value": risk.value, "inline": True},
                {"name": "Motivo", "value": _truncate(reason), "inline": False},
            ]
        )
    else:
        fields.extend(
            [
                {"name": "Motivo de rechazo", "value": _truncate(reason), "inline": False},
                {"name": "Riesgo", "value": risk.value, "inline": True},
                {"name": "R/R", "value": _risk_reward_text(signal) if signal is not None else "No disponible", "inline": True},
                {"name": "Nota", "value": "La alerta queda cerrada.", "inline": False},
            ]
        )

    fields.append({"name": "Score final", "value": f"{score}/100", "inline": True})
    fields.append({"name": "Acci\u00f3n sugerida", "value": _suggested_action(decision), "inline": False})

    return {
        "title": title,
        "description": f"{_decision_icon(decision)} ${ticker.upper()} - {_decision_text(decision)}.",
        "color": 0x2ECC71 if decision is FinalDecision.COMPRAMOS else 0xE74C3C,
        "fields": fields,
        "footer": {"text": "No ejecuta operaciones autom\u00e1ticamente."},
        "timestamp": datetime.now(UTC).isoformat(),
    }