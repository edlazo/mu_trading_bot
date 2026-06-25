import asyncio
from contextlib import asynccontextmanager

from fastapi import FastAPI

from app.config import get_settings
from app.database.base import Base
from app.database.session import SessionLocal, engine, ensure_sqlite_schema
from app.routes import (
    alerts_router,
    backtests_router,
    confirmations_router,
    dashboard_router,
    decisions_router,
    maintenance_router,
    scanner_router,
    scheduler_router,
    system_router,
    watchlist_router,
    webhooks_router,
)
import app.services.scheduler_service as scheduler_service
from app.services.scheduler_service import scheduler_loop

# MVP: create tables on startup. Replace with Alembic migrations before production.
Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    scheduler_task: asyncio.Task | None = None
    app.state.scheduler_enabled = settings.enable_scheduler

    if settings.enable_scheduler:
        print("Scheduler enabled")
        scheduler_service.is_running = True
        scheduler_task = asyncio.create_task(
            scheduler_loop(SessionLocal, settings.scheduler_interval_seconds)
        )
        app.state.scheduler_task = scheduler_task
    else:
        print("Scheduler disabled")
        scheduler_service.is_running = False
        if hasattr(app.state, "scheduler_task"):
            delattr(app.state, "scheduler_task")

    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass
            finally:
                scheduler_service.is_running = False
                if hasattr(app.state, "scheduler_task"):
                    delattr(app.state, "scheduler_task")


OPENAPI_TAGS = [
    {"name": "System", "description": "Estado general de la API."},
    {"name": "Dashboard", "description": "Resumen centralizado del estado general del bot."},
    {"name": "Webhooks", "description": "Integraciones entrantes desde TradingView y pruebas de Discord."},
    {"name": "Scanner", "description": "Ejecucion manual del scanner de oportunidades."},
    {"name": "Scheduler", "description": "Estado y ejecucion manual del scheduler automatico."},
    {"name": "Watchlist", "description": "Administracion de tickers monitoreados."},
    {"name": "Alerts", "description": "Consulta y administracion del ciclo de vida de alertas."},
    {"name": "Confirmations", "description": "Confirmacion pre-cierre de alertas activas."},
    {"name": "Decisions", "description": "Historial y resumen de decisiones del bot."},
    {"name": "Backtesting", "description": "Ejecucion y consulta de resultados de backtesting."},
    {"name": "Maintenance", "description": "Herramientas de mantenimiento y limpieza de datos de prueba."},
]


app = FastAPI(title=get_settings().app_name, lifespan=lifespan, openapi_tags=OPENAPI_TAGS)

app.include_router(system_router)
app.include_router(dashboard_router)
app.include_router(watchlist_router)
app.include_router(scanner_router)
app.include_router(alerts_router)
app.include_router(confirmations_router)
app.include_router(decisions_router)
app.include_router(backtests_router)
app.include_router(scheduler_router)
app.include_router(maintenance_router)
app.include_router(webhooks_router)