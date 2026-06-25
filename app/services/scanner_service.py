import logging
from datetime import UTC, datetime
from dataclasses import dataclass, field

import pandas as pd
import yfinance as yf
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.core.indicators import asl, ema, ppo, rsi, sma
from app.core.risk_engine import calculate_risk_reward, get_entry_price
from app.models.alert import Alert
from app.schemas.alert import AlertStatus, OpportunitySource
from app.schemas.tradingview import TradingViewSignal
from app.services.alert_service import create_alert

logger = logging.getLogger(__name__)


@dataclass
class ScannerTickerResult:
    ticker: str
    signal: TradingViewSignal | None
    status: str
    reason: str
    debug: dict | None = None


@dataclass
class ScannerWatchlistResult:
    scanned: int
    created_alerts: list[Alert]
    skipped: list[ScannerTickerResult]
    created_debug: list[ScannerTickerResult] = field(default_factory=list)

    @property
    def created_tickers(self) -> list[str]:
        return [alert.ticker for alert in self.created_alerts]


def _series_from_column(data: pd.DataFrame, column: str) -> pd.Series | None:
    if column not in data.columns:
        return None
    series = data[column]
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    return series.dropna().astype(float)


def _close_series(data: pd.DataFrame) -> pd.Series:
    close = _series_from_column(data, "Close")
    if close is None:
        return pd.Series(dtype=float)
    return close


def safe_float(value) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _value_or_none(value) -> float | None:
    return safe_float(value)


def _reason_from_conditions(conditions: list[str]) -> str:
    return "Scanner automático detectó oportunidad: " + "; ".join(conditions) + "."


def _build_signal(
    ticker: str,
    reason: str,
    close: float,
    sma30: float | None,
    asl21: float | None,
    ema150: float | None,
    ema200: float | None,
    rsi14: float | None,
    rsi_ma21: float | None,
    ppo_value: float | None,
    ppo_signal: float | None,
    ppo_hist: float | None,
    ppo_hist_prev: float | None,
    support: float,
    resistance: float,
    target: float,
    stop_loss: float | None,
    volume_ok: bool | None,
) -> TradingViewSignal:
    return TradingViewSignal(
        ticker=ticker,
        market="USA",
        timeframe="1D",
        source=OpportunitySource.MIXED,
        reason=reason,
        close=close,
        sma30=sma30,
        asl21=asl21,
        ema150=ema150,
        ema200=ema200,
        rsi=rsi14,
        rsi_ma=rsi_ma21,
        koncorde_azul=None,
        koncorde_azul_prev=None,
        koncorde_marron=None,
        koncorde_marron_prev=None,
        koncorde_media=None,
        ppo=ppo_value,
        ppo_signal=ppo_signal,
        ppo_hist=ppo_hist,
        ppo_hist_prev=ppo_hist_prev,
        volume_ok=volume_ok,
        support=support,
        resistance=resistance,
        target=target,
        stop_loss=stop_loss,
        weekly_context=None,
        monthly_context=None,
        fundamental_context=None,
        notes="Generado por scanner automático básico.",
    )


def scan_ticker(ticker: str, force_alert: bool = False) -> ScannerTickerResult:
    normalized_ticker = ticker.strip().upper()
    if not normalized_ticker:
        return ScannerTickerResult(ticker=ticker, signal=None, status="error", reason="Ticker vacío")

    logger.info("Scanner: escaneando ticker=%s", normalized_ticker)
    try:
        data = yf.download(
            normalized_ticker,
            period="300d",
            interval="1d",
            progress=False,
            auto_adjust=False,
        )
        rows = 0 if data is None else len(data)
        logger.info("Scanner: ticker=%s filas_descargadas=%s", normalized_ticker, rows)
        if data is None or data.empty or len(data) < 50:
            return ScannerTickerResult(
                ticker=normalized_ticker,
                signal=None,
                status="no_data",
                reason="yfinance no trajo datos suficientes",
            )

        close = _close_series(data)
        if len(close) < 50:
            return ScannerTickerResult(
                ticker=normalized_ticker,
                signal=None,
                status="no_data",
                reason="yfinance no trajo cierres suficientes",
            )

        sma30_series = sma(close, 30)
        asl21_series = asl(close, 21)
        ema150_series = ema(close, 150)
        ema200_series = ema(close, 200)
        rsi14_series = rsi(close, 14)
        rsi_ma21_series = sma(rsi14_series, 21)
        ppo_line, ppo_signal_series, ppo_hist_series = ppo(close)

        latest_close = safe_float(close.iloc[-1])
        previous_close = safe_float(close.iloc[-2])
        if latest_close is None or latest_close <= 0:
            return ScannerTickerResult(
                ticker=normalized_ticker,
                signal=None,
                status="no_data",
                reason="Close invalido o no disponible",
            )
        latest_sma30 = _value_or_none(sma30_series.iloc[-1])
        previous_sma30 = _value_or_none(sma30_series.iloc[-2])
        latest_asl21 = _value_or_none(asl21_series.iloc[-1])
        latest_ema150 = _value_or_none(ema150_series.iloc[-1])
        latest_ema200 = _value_or_none(ema200_series.iloc[-1])
        latest_rsi = _value_or_none(rsi14_series.iloc[-1])
        latest_rsi_ma = _value_or_none(rsi_ma21_series.iloc[-1])
        latest_ppo = _value_or_none(ppo_line.iloc[-1])
        latest_ppo_signal = _value_or_none(ppo_signal_series.iloc[-1])
        latest_ppo_hist = _value_or_none(ppo_hist_series.iloc[-1])
        previous_ppo_hist = _value_or_none(ppo_hist_series.iloc[-2])

        high = _series_from_column(data, "High")
        low = _series_from_column(data, "Low")
        if high is None:
            high = close
        if low is None:
            low = close
        previous_high = high.shift(1)
        previous_low = low.shift(1)
        resistance = safe_float(previous_high.rolling(20).max().iloc[-1])
        support = safe_float(previous_low.rolling(20).min().iloc[-1])
        if support is None or resistance is None:
            return ScannerTickerResult(
                ticker=normalized_ticker,
                signal=None,
                status="no_data",
                reason="Soporte o resistencia no disponible",
            )

        volume = _series_from_column(data, "Volume")
        latest_volume = safe_float(volume.iloc[-1]) if volume is not None and len(volume) else None
        avg_volume_20 = safe_float(volume.tail(20).mean()) if volume is not None and len(volume) >= 20 else None
        volume_ok = None
        if latest_volume is not None and avg_volume_20 is not None and avg_volume_20 > 0:
            volume_ok = latest_volume >= avg_volume_20 * 0.8

        entry_price = resistance if latest_close < resistance else latest_close
        target = resistance if resistance > latest_close and resistance > entry_price else entry_price * 1.03
        if target is None or target <= entry_price or target <= latest_close:
            target = entry_price * 1.03
        if target <= entry_price:
            debug = {"close": latest_close, "resistance": resistance, "support": support, "entry_price": entry_price, "target": target}
            return ScannerTickerResult(
                normalized_ticker,
                None,
                "no_opportunity",
                "Target inv\u00e1lido o sin upside suficiente",
                debug,
            )
        stop_loss = support if support < entry_price else latest_sma30

        logger.info(
            "Scanner: ticker=%s close=%s rsi=%s ppo=%s sma30=%s",
            normalized_ticker,
            latest_close,
            latest_rsi,
            latest_ppo,
            latest_sma30,
        )

        evaluated_conditions = {
            "close_crossed_sma30": (
                latest_sma30 is not None
                and previous_sma30 is not None
                and previous_close is not None
                and latest_close > latest_sma30
                and previous_close <= previous_sma30
            ),
            "rsi_in_buy_zone": latest_rsi is not None and 50 <= latest_rsi <= 68,
            "ppo_bullish": (
                latest_ppo is not None
                and latest_ppo_signal is not None
                and latest_ppo_hist is not None
                and latest_ppo > latest_ppo_signal
                and latest_ppo_hist > 0
            ),
            "near_resistance": resistance > 0 and latest_close >= resistance * 0.98,
            "close_above_sma30_and_asl21": (
                latest_sma30 is not None
                and latest_asl21 is not None
                and latest_close > latest_sma30
                and latest_close > latest_asl21
            ),
        }
        debug = {
            "close": latest_close,
            "sma30": latest_sma30,
            "asl21": latest_asl21,
            "ema150": latest_ema150,
            "ema200": latest_ema200,
            "rsi": latest_rsi,
            "ppo": latest_ppo,
            "ppo_signal": latest_ppo_signal,
            "ppo_hist": latest_ppo_hist,
            "support": support,
            "resistance": resistance,
            "entry_price": entry_price,
            "target": target,
            "stop_loss": stop_loss,
            "risk_reward": calculate_risk_reward(entry_price, target, stop_loss),
            "volume": latest_volume,
            "avg_volume_20": avg_volume_20,
            "volume_ok": volume_ok,
            "conditions": evaluated_conditions,
        }

        conditions: list[str] = []
        if evaluated_conditions["close_crossed_sma30"]:
            conditions.append("precio recupera SMA30")
        if evaluated_conditions["rsi_in_buy_zone"]:
            conditions.append("RSI en zona compradora sana")
        if evaluated_conditions["ppo_bullish"]:
            conditions.append("PPO-Min/Max confirma impulso positivo")
        if evaluated_conditions["near_resistance"]:
            conditions.append("precio cerca de resistencia con posible ruptura")
        if evaluated_conditions["close_above_sma30_and_asl21"]:
            conditions.append("precio sobre SMA30 y ASL21")

        if not conditions and not force_alert:
            reason = "No cumple condiciones de oportunidad"
            logger.info("Scanner: ticker=%s status=no_opportunity reason=%s", normalized_ticker, reason)
            return ScannerTickerResult(normalized_ticker, None, "no_opportunity", reason, debug)

        reason = "Alerta forzada para test del scanner." if force_alert and not conditions else _reason_from_conditions(conditions)
        signal = _build_signal(
            ticker=normalized_ticker,
            reason=reason,
            close=latest_close,
            sma30=latest_sma30,
            asl21=latest_asl21,
            ema150=latest_ema150,
            ema200=latest_ema200,
            rsi14=latest_rsi,
            rsi_ma21=latest_rsi_ma,
            ppo_value=latest_ppo,
            ppo_signal=latest_ppo_signal,
            ppo_hist=latest_ppo_hist,
            ppo_hist_prev=previous_ppo_hist,
            support=support,
            resistance=resistance,
            target=target,
            stop_loss=stop_loss,
            volume_ok=volume_ok,
        )
        logger.info("Scanner: ticker=%s status=alert_created reason=%s", normalized_ticker, reason)
        return ScannerTickerResult(normalized_ticker, signal, "alert_created", reason, debug)
    except Exception as exc:
        logger.exception("Scanner: ticker=%s status=error", normalized_ticker)
        return ScannerTickerResult(normalized_ticker, None, "error", str(exc))


def _risk_reward_skip_result(ticker: str, signal: TradingViewSignal, debug: dict | None) -> ScannerTickerResult | None:
    entry_price = get_entry_price(signal)
    risk_reward = calculate_risk_reward(entry_price, signal.target, signal.stop_loss)
    enriched_debug = debug or {}
    enriched_debug.update(
        {
            "entry_price": entry_price,
            "target": signal.target,
            "stop_loss": signal.stop_loss,
            "risk_reward": risk_reward,
        }
    )

    invalid_structure = (
        signal.target is None
        or signal.stop_loss is None
        or signal.target <= entry_price
        or signal.stop_loss >= entry_price
        or risk_reward is None
    )
    if invalid_structure:
        return ScannerTickerResult(
            ticker,
            None,
            "invalid_risk_reward",
            "R/R inv?lido: target, entrada o stop no permiten calcular una oportunidad operativa",
            enriched_debug,
        )

    if risk_reward < 1.0:
        return ScannerTickerResult(
            ticker,
            None,
            "technical_signal_invalid_rr",
            "Hay senal tecnica, pero el R/R no alcanza el minimo operativo",
            enriched_debug,
        )

    return None


async def scan_watchlist(
    db: Session,
    tickers: list[str],
    force_alert: bool = False,
    alert_status: AlertStatus = AlertStatus.EN_OBSERVACION,
    watchlist: bool = False,
) -> ScannerWatchlistResult:
    created_alerts: list[Alert] = []
    created_debug: list[ScannerTickerResult] = []
    skipped: list[ScannerTickerResult] = []

    for ticker in tickers:
        normalized_ticker = ticker.strip().upper()
        if not normalized_ticker:
            skipped.append(ScannerTickerResult(ticker=ticker, signal=None, status="error", reason="Ticker vac\u00edo"))
            continue

        logger.info("Scanner: evaluando ticker=%s", normalized_ticker)
        try:
            duplicate_status = alert_status.value
            existing_alerts = (
                db.query(Alert)
                .filter(func.upper(Alert.ticker) == normalized_ticker)
                .filter(Alert.status == duplicate_status)
                .all()
            )
            if alert_status is AlertStatus.WATCHLIST:
                today = datetime.now(UTC).date()
                existing_alert = next(
                    (alert for alert in existing_alerts if alert.created_at and alert.created_at.date() == today),
                    None,
                )
            else:
                existing_alert = existing_alerts[0] if existing_alerts else None

            if existing_alert is not None:
                is_watchlist_duplicate = alert_status is AlertStatus.WATCHLIST
                status = "duplicate_watchlist" if is_watchlist_duplicate else "duplicate_active_alert"
                reason = "Ya existe una watchlist para este ticker hoy" if is_watchlist_duplicate else "Ya existe una alerta activa"
                logger.info("Scanner: ticker=%s status=%s reason=%s", normalized_ticker, status, reason)
                skipped.append(ScannerTickerResult(normalized_ticker, None, status, reason))
                continue

            result = scan_ticker(normalized_ticker, force_alert=force_alert)
            if result.signal is None:
                skipped.append(result)
                continue

            skip_result = _risk_reward_skip_result(normalized_ticker, result.signal, result.debug)
            if skip_result is not None:
                skipped.append(skip_result)
                continue

            alert, _score, _risk = await create_alert(db, result.signal, status=alert_status, watchlist=watchlist)
            created_alerts.append(alert)
            created_debug.append(result)
        except Exception as exc:
            logger.exception("Scanner: ticker=%s status=error", normalized_ticker)
            skipped.append(ScannerTickerResult(normalized_ticker, None, "error", str(exc)))

    return ScannerWatchlistResult(
        scanned=len(tickers),
        created_alerts=created_alerts,
        skipped=skipped,
        created_debug=created_debug,
    )
