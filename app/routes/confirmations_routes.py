from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.alert import Alert
from app.schemas.alert import AlertStatus
from app.schemas.tradingview import TradingViewSignal
from app.services.confirmation_service import confirm_alert_with_signal, run_pre_close_confirmation

router = APIRouter(prefix="/confirmations", tags=["Confirmations"])


@router.post("/pre-close/{alert_id}", summary="Confirm alert pre-close")
async def pre_close_confirmation_for_alert(
    alert_id: int,
    signal: TradingViewSignal,
    db: Session = Depends(get_db),
) -> dict:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    if alert.status != AlertStatus.EN_OBSERVACION.value:
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=f"Alert already confirmed or not active: {alert.status}",
        )

    decision = await confirm_alert_with_signal(db, alert, signal)
    return {
        "ticker": decision.ticker,
        "decision": decision.decision,
        "score": decision.final_score,
        "risk": decision.final_risk,
        "reason": decision.reason,
    }


# MVP/testing: bulk confirmation uses stored alert data via the market-data placeholder until fresh data is integrated.
@router.post("/pre-close", summary="Run pre-close confirmation")
async def pre_close_confirmation(db: Session = Depends(get_db)) -> dict:
    decisions = await run_pre_close_confirmation(db)
    confirmed = sum(1 for decision in decisions if decision.decision == "COMPRAMOS")
    rejected = sum(1 for decision in decisions if decision.decision == "NO_COMPRAMOS")
    return {
        "status": "pre_close_confirmation_completed",
        "confirmed": confirmed,
        "rejected": rejected,
        "decisions": [
            {
                "ticker": decision.ticker,
                "decision": decision.decision,
                "score": decision.final_score,
                "risk": decision.final_risk,
                "reason": decision.reason,
            }
            for decision in decisions
        ],
    }