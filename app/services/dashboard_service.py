from sqlalchemy.orm import Session

from app.config import get_settings
from app.models.alert import Alert
from app.models.watchlist import WatchlistTicker
from app.schemas.alert import AlertStatus
from app.schemas.dashboard import DashboardSummaryResponse
from app.services.backtest_service import backtest_summary
from app.services.decision_service import decision_summary
from app.services.scheduler_service import get_scheduler_status


def get_dashboard_summary(db: Session) -> DashboardSummaryResponse:
    settings = get_settings()
    scheduler = get_scheduler_status(
        settings.enable_scheduler,
        settings.scheduler_interval_seconds,
        scanner_batch_size=settings.scanner_batch_size,
    )

    scanner_summary = {
        "watchlist_enabled_count": db.query(WatchlistTicker).filter(WatchlistTicker.enabled.is_(True)).count(),
        "active_alerts": db.query(Alert).filter(Alert.status == AlertStatus.EN_OBSERVACION.value).count(),
        "watchlist_alerts": db.query(Alert).filter(Alert.status == AlertStatus.WATCHLIST.value).count(),
        "archived_alerts": db.query(Alert).filter(Alert.status == AlertStatus.ARCHIVED.value).count(),
    }

    scheduler_summary = {
        "enabled": scheduler["enabled"],
        "interval_seconds": scheduler["interval_seconds"],
        "is_running": scheduler["is_running"],
        "last_run_at": scheduler["last_run_at"],
        "last_result": scheduler["last_result"],
        "last_pre_close_run_at": scheduler["last_pre_close_run_at"],
        "last_pre_close_result": scheduler["last_pre_close_result"],
        "scanner_batch_size": scheduler["scanner_batch_size"],
        "scanner_next_offset": scheduler["scanner_next_offset"],
        "is_pre_close_window": scheduler["is_pre_close_window"],
    }

    return DashboardSummaryResponse(
        scanner=scanner_summary,
        decisions=decision_summary(db),
        backtesting=backtest_summary(db),
        scheduler=scheduler_summary,
    )