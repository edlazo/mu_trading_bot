from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy import func
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.alert import Alert
from app.services.alert_service import (
    archive_alert,
    archive_test_alerts,
    archive_watchlist_alerts,
    list_active_alerts,
    list_archived_alerts,
    list_watchlist_alerts,
)

router = APIRouter(prefix="/alerts", tags=["Alerts"])


def _alert_payload(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "ticker": alert.ticker,
        "market": alert.market,
        "timeframe": alert.timeframe,
        "source": alert.source,
        "reason": alert.reason,
        "close": alert.close,
        "support": alert.support,
        "resistance": alert.resistance,
        "target": alert.target,
        "stop_loss": alert.stop_loss,
        "score": alert.preliminary_score,
        "risk": alert.preliminary_risk,
        "entry_price": alert.entry_price,
        "risk_reward": alert.risk_reward,
        "status": alert.status,
        "created_at": alert.created_at.isoformat(),
    }


@router.get("/active", summary="Get active alerts")
def active_alerts(db: Session = Depends(get_db)) -> list[dict]:
    return [_alert_payload(alert) for alert in list_active_alerts(db)]


@router.get("/watchlist", summary="Get watchlist alerts")
def watchlist_alerts(db: Session = Depends(get_db)) -> list[dict]:
    return [_alert_payload(alert) for alert in list_watchlist_alerts(db)]


@router.get("/archived", summary="Get archived alerts")
def archived_alerts(db: Session = Depends(get_db)) -> list[dict]:
    return [_alert_payload(alert) for alert in list_archived_alerts(db)]


@router.get("/by-ticker/{ticker}", summary="Get alerts by ticker")
def alerts_by_ticker(ticker: str, db: Session = Depends(get_db)) -> list[dict]:
    normalized_ticker = ticker.strip().upper()
    alerts = (
        db.query(Alert)
        .filter(func.upper(Alert.ticker) == normalized_ticker)
        .order_by(Alert.created_at.desc())
        .all()
    )
    return [_alert_payload(alert) for alert in alerts]


@router.get("/{alert_id}", summary="Get alert by id")
def alert_by_id(alert_id: int, db: Session = Depends(get_db)) -> dict:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return _alert_payload(alert)


@router.patch("/{alert_id}/archive", summary="Archive alert")
def archive_single_alert(alert_id: int, db: Session = Depends(get_db)) -> dict:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return _alert_payload(archive_alert(db, alert))


@router.post("/archive-watchlist", summary="Archive watchlist alerts")
def archive_all_watchlist_alerts(db: Session = Depends(get_db)) -> dict:
    archived_count = archive_watchlist_alerts(db)
    return {"status": "archived", "archived_count": archived_count}


@router.post("/archive-test-alerts", summary="Archive test alerts")
def archive_all_test_alerts(db: Session = Depends(get_db)) -> dict:
    archived_count = archive_test_alerts(db)
    return {"status": "archived", "archived_count": archived_count}