from app.routes.system_routes import router as system_router
from app.routes.dashboard_routes import router as dashboard_router
from app.routes.watchlist_routes import router as watchlist_router
from app.routes.scanner_routes import router as scanner_router
from app.routes.alerts_routes import router as alerts_router
from app.routes.confirmations_routes import router as confirmations_router
from app.routes.decisions_routes import router as decisions_router
from app.routes.backtests_routes import router as backtests_router
from app.routes.scheduler_routes import router as scheduler_router
from app.routes.maintenance_routes import router as maintenance_router
from app.routes.webhooks_routes import router as webhooks_router

__all__ = [
    "system_router",
    "dashboard_router",
    "watchlist_router",
    "scanner_router",
    "alerts_router",
    "confirmations_router",
    "decisions_router",
    "backtests_router",
    "scheduler_router",
    "maintenance_router",
    "webhooks_router",
]