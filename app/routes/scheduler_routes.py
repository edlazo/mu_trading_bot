from fastapi import APIRouter, Query

from app.config import get_settings
from app.database.session import SessionLocal
from app.services.scheduler_service import get_scheduler_status, run_scheduler_once

router = APIRouter(prefix="/scheduler", tags=["Scheduler"])


@router.get("/status", summary="Get scheduler status")
def scheduler_status() -> dict:
    settings = get_settings()
    return get_scheduler_status(
        settings.enable_scheduler,
        settings.scheduler_interval_seconds,
        scanner_batch_size=settings.scanner_batch_size,
    )


@router.post("/run-once", summary="Run scheduler once")
async def scheduler_run_once(force_pre_close: bool = Query(default=False)) -> dict:
    settings = get_settings()
    return await run_scheduler_once(
        SessionLocal,
        scanner_batch_size=settings.scanner_batch_size,
        force_pre_close=force_pre_close,
    )