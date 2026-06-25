from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.decision import Decision
from app.schemas.alert import FinalDecision, RiskLevel


def list_decisions(db: Session) -> list[Decision]:
    return db.query(Decision).order_by(Decision.created_at.desc()).all()


def get_decision(db: Session, decision_id: int) -> Decision | None:
    return db.get(Decision, decision_id)


def list_decisions_by_ticker(db: Session, ticker: str) -> list[Decision]:
    return (
        db.query(Decision)
        .filter(func.upper(Decision.ticker) == ticker.strip().upper())
        .order_by(Decision.created_at.desc())
        .all()
    )


def get_decision_by_alert_id(db: Session, alert_id: int) -> Decision | None:
    return db.query(Decision).filter(Decision.alert_id == alert_id).first()


def _risk_key(final_risk: str) -> str:
    value = final_risk.split()[0] if final_risk else ""
    return value if value in {"BAJO", "MEDIO", "ALTO", "EXTREMO"} else value


def decision_summary(db: Session) -> dict:
    decisions = db.query(Decision).all()
    by_risk = {risk.name: 0 for risk in RiskLevel}
    compramos = 0
    no_compramos = 0

    for decision in decisions:
        if decision.decision == FinalDecision.COMPRAMOS.value:
            compramos += 1
        elif decision.decision == FinalDecision.NO_COMPRAMOS.value:
            no_compramos += 1

        risk = _risk_key(decision.final_risk)
        if risk in by_risk:
            by_risk[risk] += 1

    return {
        "total": len(decisions),
        "compramos": compramos,
        "no_compramos": no_compramos,
        "by_risk": by_risk,
    }
