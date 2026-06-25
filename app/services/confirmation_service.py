from sqlalchemy.orm import Session

from app.core.decision_engine import make_final_decision
from app.core.risk_engine import calculate_risk_reward, get_entry_price
from app.core.message_builder import (
    build_pre_close_summary,
    build_pre_close_summary_embed,
    build_single_confirmation_embed,
    build_single_confirmation_message,
)
from app.integrations.discord import send_discord_message
from app.models.alert import Alert
from app.models.decision import Decision
from app.schemas.alert import AlertStatus, FinalDecision
from app.schemas.tradingview import TradingViewSignal
from app.services.alert_service import list_active_alerts, signal_from_alert
from app.services.decision_service import get_decision_by_alert_id
from app.services.market_data_service import get_updated_signal_for_alert


def _status_for_decision(final_decision: FinalDecision) -> str:
    return (
        AlertStatus.COMPRAMOS.value
        if final_decision is FinalDecision.COMPRAMOS
        else AlertStatus.NO_COMPRAMOS.value
    )


def _decision_from_signal(
    alert: Alert,
    signal: TradingViewSignal,
    final_decision: FinalDecision,
    reason: str,
    score: int,
    risk_value: str,
) -> Decision:
    entry_price = get_entry_price(signal)
    risk_reward = calculate_risk_reward(entry_price, signal.target, signal.stop_loss)
    return Decision(
        alert_id=alert.id,
        ticker=alert.ticker,
        final_score=score,
        final_risk=risk_value,
        decision=final_decision.value,
        reason=reason,
        entry_price=entry_price,
        target=signal.target,
        stop_loss=signal.stop_loss,
        risk_reward=risk_reward,
    )


async def confirm_alert_with_signal(db: Session, alert: Alert, signal: TradingViewSignal) -> Decision:
    existing_decision = get_decision_by_alert_id(db, alert.id)
    if existing_decision is not None:
        alert.status = existing_decision.decision
        db.commit()
        db.refresh(existing_decision)
        return existing_decision

    final_decision, reason, score, risk = make_final_decision(signal)
    alert.status = _status_for_decision(final_decision)

    decision = _decision_from_signal(alert, signal, final_decision, reason, score, risk.value)
    db.add(decision)
    db.commit()
    db.refresh(decision)

    _text_fallback = build_single_confirmation_message(alert.ticker, final_decision, risk, reason, score, signal=signal)
    embed = build_single_confirmation_embed(alert.ticker, final_decision, risk, reason, score, signal=signal)
    await send_discord_message(content=None, embeds=[embed])
    return decision


async def run_pre_close_confirmation(db: Session, use_updated_data: bool = True) -> list[Decision]:
    alerts = list_active_alerts(db)
    decisions: list[Decision] = []
    summary_items = []

    for alert in alerts:
        signal = get_updated_signal_for_alert(alert) if use_updated_data else signal_from_alert(alert)
        existing_decision = get_decision_by_alert_id(db, alert.id)
        if existing_decision is not None:
            alert.status = existing_decision.decision
            continue

        final_decision, reason, score, risk = make_final_decision(signal)
        alert.status = _status_for_decision(final_decision)
        decision = _decision_from_signal(alert, signal, final_decision, reason, score, risk.value)
        db.add(decision)
        decisions.append(decision)
        summary_items.append((alert.ticker, final_decision, risk, reason))

    db.commit()
    for decision in decisions:
        db.refresh(decision)

    if summary_items:
        _text_fallback = build_pre_close_summary(summary_items)
        embed = build_pre_close_summary_embed(summary_items)
        await send_discord_message(content=None, embeds=[embed])

    return decisions