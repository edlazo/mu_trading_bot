from datetime import UTC, datetime

import pandas as pd
import yfinance as yf
from fastapi import HTTPException, status
from sqlalchemy.orm import Session

from app.models.backtest import BacktestResult
from app.models.decision import Decision
from app.schemas.alert import FinalDecision
from app.schemas.backtest import BacktestOutcome


def _safe_float(value) -> float | None:
    try:
        if value is None or pd.isna(value):
            return None
        return float(value)
    except (TypeError, ValueError):
        return None


def _series_from_column(data: pd.DataFrame, column: str) -> pd.Series | None:
    if column not in data.columns:
        return None
    series = data[column]
    if isinstance(series, pd.DataFrame):
        series = series.iloc[:, 0]
    return series.reset_index(drop=False)


def _row_date(row) -> datetime | None:
    raw_date = row.get("Date") or row.get("Datetime")
    if raw_date is None:
        return None
    timestamp = pd.Timestamp(raw_date)
    if timestamp.tzinfo is None:
        return timestamp.to_pydatetime().replace(tzinfo=UTC)
    return timestamp.to_pydatetime().astimezone(UTC)


def get_backtest_by_decision_id(db: Session, decision_id: int) -> BacktestResult | None:
    return db.query(BacktestResult).filter(BacktestResult.decision_id == decision_id).first()


def list_backtests(db: Session) -> list[BacktestResult]:
    return db.query(BacktestResult).order_by(BacktestResult.created_at.desc()).all()


def _pnl_percent(exit_price: float | None, entry_price: float | None) -> float | None:
    if exit_price is None or entry_price is None or entry_price <= 0:
        return None
    return (exit_price - entry_price) / entry_price * 100


def _error_result(decision: Decision, days: int, reason: str) -> BacktestResult:
    return BacktestResult(
        decision_id=decision.id,
        alert_id=decision.alert_id,
        ticker=decision.ticker,
        entry_price=decision.entry_price,
        target=decision.target,
        stop_loss=decision.stop_loss,
        risk_reward=decision.risk_reward,
        result=BacktestOutcome.ERROR.value,
        days_checked=0,
        exit_price=None,
        exit_date=None,
        pnl_percent=None,
        reason=reason,
    )


def run_backtest_for_decision(db: Session, decision_id: int, days: int = 10, force: bool = False) -> BacktestResult:
    decision = db.get(Decision, decision_id)
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")

    existing_result = get_backtest_by_decision_id(db, decision_id)
    if existing_result is not None and not force:
        return existing_result
    if existing_result is not None and force:
        db.delete(existing_result)
        db.commit()

    if decision.decision != FinalDecision.COMPRAMOS.value:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail="Only COMPRAMOS decisions can be backtested")

    if decision.entry_price is None or decision.target is None or decision.stop_loss is None:
        result = _error_result(decision, days, "Faltan datos operativos para backtesting")
        db.add(result)
        db.commit()
        db.refresh(result)
        return result

    data = yf.download(
        decision.ticker,
        period=f"{max(days + 10, 30)}d",
        interval="1d",
        progress=False,
        auto_adjust=False,
    )
    if data is None or data.empty:
        result = _error_result(decision, days, "yfinance no trajo datos para backtesting")
        db.add(result)
        db.commit()
        db.refresh(result)
        return result

    high = _series_from_column(data, "High")
    low = _series_from_column(data, "Low")
    close = _series_from_column(data, "Close")
    if high is None or low is None or close is None:
        result = _error_result(decision, days, "Datos de high/low/close no disponibles")
        db.add(result)
        db.commit()
        db.refresh(result)
        return result

    merged = high[[high.columns[0], high.columns[-1]]].copy()
    merged.columns = ["Date", "High"]
    merged["Low"] = low[low.columns[-1]].values
    merged["Close"] = close[close.columns[-1]].values
    rows = merged.head(days)

    outcome = BacktestOutcome.NO_RESULT
    exit_price = None
    exit_date = None
    reason = "No toco target ni stop en el periodo evaluado"
    days_checked = len(rows)

    for index, row in rows.iterrows():
        daily_high = _safe_float(row["High"])
        daily_low = _safe_float(row["Low"])
        if daily_high is None or daily_low is None:
            continue

        hit_target = daily_high >= decision.target
        hit_stop = daily_low <= decision.stop_loss
        if hit_target and hit_stop:
            outcome = BacktestOutcome.ERROR
            exit_price = None
            exit_date = _row_date(row)
            reason = "La misma vela toco target y stop; resultado ambiguo"
            days_checked = int(index) + 1
            break
        if hit_target:
            outcome = BacktestOutcome.TARGET_HIT
            exit_price = decision.target
            exit_date = _row_date(row)
            reason = "Target alcanzado antes que stop loss"
            days_checked = int(index) + 1
            break
        if hit_stop:
            outcome = BacktestOutcome.STOP_HIT
            exit_price = decision.stop_loss
            exit_date = _row_date(row)
            reason = "Stop loss alcanzado antes que target"
            days_checked = int(index) + 1
            break

    if outcome is BacktestOutcome.NO_RESULT and len(rows) > 0:
        last_row = rows.iloc[-1]
        exit_price = _safe_float(last_row["Close"])
        exit_date = _row_date(last_row)

    result = BacktestResult(
        decision_id=decision.id,
        alert_id=decision.alert_id,
        ticker=decision.ticker,
        entry_price=decision.entry_price,
        target=decision.target,
        stop_loss=decision.stop_loss,
        risk_reward=decision.risk_reward,
        result=outcome.value,
        days_checked=days_checked,
        exit_price=exit_price,
        exit_date=exit_date,
        pnl_percent=_pnl_percent(exit_price, decision.entry_price),
        reason=reason,
    )
    db.add(result)
    db.commit()
    db.refresh(result)
    return result


def run_backtests_for_pending_buy_decisions(db: Session, days: int = 10, force: bool = False) -> tuple[list[BacktestResult], int]:
    query = db.query(Decision).filter(Decision.decision == FinalDecision.COMPRAMOS.value)
    decisions = query.order_by(Decision.created_at.asc()).all()
    results: list[BacktestResult] = []
    skipped = 0

    for decision in decisions:
        existing_result = get_backtest_by_decision_id(db, decision.id)
        if existing_result is not None and not force:
            skipped += 1
            continue
        results.append(run_backtest_for_decision(db, decision.id, days=days, force=force))

    return results, skipped


def backtest_summary(db: Session) -> dict:
    results = db.query(BacktestResult).all()
    total = len(results)
    target_hit = sum(1 for result in results if result.result == BacktestOutcome.TARGET_HIT.value)
    stop_hit = sum(1 for result in results if result.result == BacktestOutcome.STOP_HIT.value)
    no_result = sum(1 for result in results if result.result == BacktestOutcome.NO_RESULT.value)
    pnl_values = [result.pnl_percent for result in results if result.pnl_percent is not None]
    return {
        "total": total,
        "target_hit": target_hit,
        "stop_hit": stop_hit,
        "no_result": no_result,
        "win_rate": (target_hit / total * 100) if total else 0.0,
        "average_pnl_percent": (sum(pnl_values) / len(pnl_values)) if pnl_values else 0.0,
    }
