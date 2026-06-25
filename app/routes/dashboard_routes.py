from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.dashboard_service import get_dashboard_summary

router = APIRouter(prefix="/dashboard", tags=["Dashboard"])


@router.get("/summary", response_model=DashboardSummaryResponse, summary="Get dashboard summary")
def dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummaryResponse:
    return get_dashboard_summary(db)