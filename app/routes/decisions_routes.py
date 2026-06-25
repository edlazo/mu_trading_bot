from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.models.decision import Decision
from app.services.decision_service import decision_summary, get_decision, list_decisions, list_decisions_by_ticker

router = APIRouter(prefix="/decisions", tags=["Decisions"])


def _decision_payload(decision: Decision) -> dict:
    return {
        "id": decision.id,
        "alert_id": decision.alert_id,
        "ticker": decision.ticker,
        "decision": decision.decision,
        "reason": decision.reason,
        "risk": decision.final_risk,
        "score": decision.final_score,
        "entry_price": decision.entry_price,
        "target": decision.target,
        "stop_loss": decision.stop_loss,
        "risk_reward": decision.risk_reward,
        "created_at": decision.created_at.isoformat(),
    }


@router.get("", summary="Get decisions")
def decisions_history(db: Session = Depends(get_db)) -> list[dict]:
    return [_decision_payload(decision) for decision in list_decisions(db)]


@router.get("/summary", summary="Get decisions summary")
def decisions_summary(db: Session = Depends(get_db)) -> dict:
    return decision_summary(db)


@router.get("/by-ticker/{ticker}", summary="Get decisions by ticker")
def decisions_history_by_ticker(ticker: str, db: Session = Depends(get_db)) -> list[dict]:
    return [_decision_payload(decision) for decision in list_decisions_by_ticker(db, ticker)]


@router.get("/{decision_id}", summary="Get decision")
def decision_detail(decision_id: int, db: Session = Depends(get_db)) -> dict:
    decision = get_decision(db, decision_id)
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return _decision_payload(decision)