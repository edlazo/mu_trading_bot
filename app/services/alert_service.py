from sqlalchemy import or_
from sqlalchemy.orm import Session

from app.core.message_builder import build_alert_embed, build_alert_message
from app.core.opportunity_engine import calculate_preliminary_score
from app.core.risk_engine import calculate_risk_reward, classify_preliminary_risk, get_entry_price
from app.integrations.discord import send_discord_message
from app.models.alert import Alert
from app.schemas.alert import AlertStatus
from app.schemas.tradingview import TradingViewSignal


def signal_from_alert(alert: Alert) -> TradingViewSignal:
    return TradingViewSignal(
        ticker=alert.ticker,
        market=alert.market,
        timeframe=alert.timeframe,
        source=alert.source,
        reason=alert.reason,
        close=alert.close,
        sma30=alert.sma30,
        asl21=alert.asl21,
        ema150=alert.ema150,
        ema200=alert.ema200,
        rsi=alert.rsi,
        rsi_ma=alert.rsi_ma,
        koncorde_azul=alert.koncorde_azul,
        koncorde_azul_prev=alert.koncorde_azul_prev,
        koncorde_marron=alert.koncorde_marron,
        koncorde_marron_prev=alert.koncorde_marron_prev,
        koncorde_media=alert.koncorde_media,
        ppo=alert.ppo,
        ppo_signal=alert.ppo_signal,
        ppo_hist=alert.ppo_hist,
        ppo_hist_prev=alert.ppo_hist_prev,
        volume_ok=alert.volume_ok,
        support=alert.support,
        resistance=alert.resistance,
        target=alert.target,
        stop_loss=alert.stop_loss,
        weekly_context=alert.weekly_context,
        monthly_context=alert.monthly_context,
        fundamental_context=alert.fundamental_context,
        notes=alert.notes,
    )


async def create_alert(
    db: Session,
    signal: TradingViewSignal,
    status: AlertStatus = AlertStatus.EN_OBSERVACION,
    watchlist: bool = False,
) -> tuple[Alert, int, str]:
    score = calculate_preliminary_score(signal)
    entry_price = get_entry_price(signal)
    risk_reward = calculate_risk_reward(entry_price, signal.target, signal.stop_loss)
    risk = classify_preliminary_risk(score, risk_reward)
    alert_data = signal.model_dump()
    if watchlist:
        extra_note = "Oportunidad detectada fuera de horario. Revisar en próxima rueda."
        alert_data["notes"] = f"{alert_data.get('notes')} {extra_note}" if alert_data.get("notes") else extra_note
    alert = Alert(
        **alert_data,
        entry_price=entry_price,
        risk_reward=risk_reward,
        preliminary_score=score,
        preliminary_risk=risk.value,
        status=status.value,
    )
    db.add(alert)
    db.commit()
    db.refresh(alert)

    _text_fallback = build_alert_message(signal, score, risk, watchlist=watchlist)
    embed = build_alert_embed(signal, score, risk, watchlist=watchlist)
    await send_discord_message(content=None, embeds=[embed])
    return alert, score, risk.value


def list_active_alerts(db: Session) -> list[Alert]:
    return (
        db.query(Alert)
        .filter(Alert.status == AlertStatus.EN_OBSERVACION.value)
        .order_by(Alert.created_at.desc())
        .all()
    )

def list_watchlist_alerts(db: Session) -> list[Alert]:
    return (
        db.query(Alert)
        .filter(Alert.status == AlertStatus.WATCHLIST.value)
        .order_by(Alert.created_at.desc())
        .all()
    )

def archive_alert(db: Session, alert: Alert) -> Alert:
    alert.status = AlertStatus.ARCHIVED.value
    db.add(alert)
    db.commit()
    db.refresh(alert)
    return alert


def archive_watchlist_alerts(db: Session) -> int:
    alerts = db.query(Alert).filter(Alert.status == AlertStatus.WATCHLIST.value).all()
    for alert in alerts:
        alert.status = AlertStatus.ARCHIVED.value
        db.add(alert)
    db.commit()
    return len(alerts)


def archive_test_alerts(db: Session) -> int:
    alerts = (
        db.query(Alert)
        .filter(Alert.status != AlertStatus.ARCHIVED.value)
        .filter(
            or_(
                Alert.reason.ilike("%Alerta forzada%"),
                Alert.reason.ilike("%test%"),
                Alert.reason.ilike("%prueba%"),
            )
        )
        .all()
    )
    for alert in alerts:
        alert.status = AlertStatus.ARCHIVED.value
        db.add(alert)
    db.commit()
    return len(alerts)


def list_archived_alerts(db: Session) -> list[Alert]:
    return (
        db.query(Alert)
        .filter(Alert.status == AlertStatus.ARCHIVED.value)
        .order_by(Alert.created_at.desc())
        .all()
    )
