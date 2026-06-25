from fastapi import APIRouter

from app.config import get_settings
from app.database.session import SessionLocal
from app.services.scheduler_service import get_scheduler_status, run_scheduled_watchlist_scan

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


@router.get("/status", summary="Get scheduler status")
def scheduler_status() -> dict:
    settings = get_settings()
    return get_scheduler_status(settings.enable_scheduler, settings.scheduler_interval_seconds)


@router.post("/run-once", summary="Run scheduler once")
async def scheduler_run_once() -> dict:
    settings = get_settings()
    return await run_scheduled_watchlist_scan(SessionLocal, scanner_batch_size=settings.scanner_batch_size)