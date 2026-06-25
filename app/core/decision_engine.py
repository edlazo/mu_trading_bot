from app.core.opportunity_engine import calculate_preliminary_score
from app.core.risk_engine import calculate_risk_reward, classify_preliminary_risk, get_entry_price
from app.schemas.alert import FinalDecision, RiskLevel
from app.schemas.tradingview import TradingViewSignal

INVALID_OPERATIONAL_DATA_REASON = "No se confirma compra porque faltan datos operativos o R/R valido."


def make_final_decision(signal: TradingViewSignal) -> tuple[FinalDecision, str, int, RiskLevel]:
    score = calculate_preliminary_score(signal)
    entry_price = get_entry_price(signal)
    risk_reward = calculate_risk_reward(entry_price, signal.target, signal.stop_loss)
    risk = classify_preliminary_risk(score, risk_reward)

    operational_blockers: list[str] = []
    if signal.target is None:
        operational_blockers.append("sin objetivo claro")
    if signal.stop_loss is None:
        operational_blockers.append("sin stop loss claro")
    if signal.target is not None and signal.target <= entry_price:
        operational_blockers.append("objetivo invalido frente a la entrada")
    if signal.stop_loss is not None and signal.stop_loss >= entry_price:
        operational_blockers.append("stop loss invalido")
    if risk_reward is None or risk_reward < 1.5:
        operational_blockers.append("relacion riesgo/beneficio menor a 1.5")

    if operational_blockers:
        reason = f"{INVALID_OPERATIONAL_DATA_REASON} " + " / ".join(operational_blockers)
        return FinalDecision.NO_COMPRAMOS, reason, score, risk

    blockers: list[str] = []
    if risk in {RiskLevel.ALTO, RiskLevel.EXTREMO} or (signal.rsi is not None and signal.rsi > 75):
        blockers.append("Riesgo demasiado alto para confirmar compra.")
    if score < 65:
        blockers.append("score menor a 65")
    if signal.volume_ok is None:
        blockers.append("datos criticos faltantes")
    if signal.rsi is not None and signal.rsi > 75:
        blockers.append("RSI mayor a 75")

    if blockers:
        return FinalDecision.NO_COMPRAMOS, " / ".join(blockers), score, risk

    return FinalDecision.COMPRAMOS, "oportunidad vigente con riesgo aceptable", score, risk
