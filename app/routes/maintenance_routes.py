from fastapi import APIRouter, Depends, Query
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.schemas.maintenance import MaintenanceCleanupResponse, MaintenanceTestDataSummary
from app.services.maintenance_service import cleanup_test_data, get_test_data_summary

router = APIRouter(prefix="/maintenance", tags=["Maintenance"])


@router.get("/test-data/summary", response_model=MaintenanceTestDataSummary, summary="Get test data summary")
def maintenance_test_data_summary(db: Session = Depends(get_db)) -> MaintenanceTestDataSummary:
    return get_test_data_summary(db)


@router.post("/cleanup-test-data", response_model=MaintenanceCleanupResponse, summary="Cleanup test data")
def maintenance_cleanup_test_data(
    dry_run: bool = Query(default=True),
    db: Session = Depends(get_db),
) -> MaintenanceCleanupResponse:
    return cleanup_test_data(db, dry_run=dry_run)