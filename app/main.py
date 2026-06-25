import asyncio
from contextlib import asynccontextmanager
from datetime import UTC, datetime

from fastapi import Depends, FastAPI, HTTPException, Query, status
from sqlalchemy.orm import Session

from app.config import get_settings
from app.database.base import Base
from app.core.market_hours import get_market_session_status, is_market_open
from app.database.session import SessionLocal, engine, ensure_sqlite_schema, get_db
from app.integrations.discord import send_discord_message
from app.integrations.tradingview import validate_tradingview_secret
from app.models.alert import Alert
from app.models.backtest import BacktestResult
from app.models.decision import Decision
from app.schemas.alert import AlertResponse, AlertStatus
from app.schemas.backtest import BacktestResultResponse, BacktestRunResponse
from app.schemas.dashboard import DashboardSummaryResponse
from app.schemas.scanner import ScannerRequest, ScannerResponse
from app.schemas.tradingview import TradingViewSignal
from app.schemas.watchlist import WatchlistTickerCreate, WatchlistTickerResponse, WatchlistTickerUpdate
from app.services.alert_service import (
    archive_alert,
    archive_test_alerts,
    archive_watchlist_alerts,
    create_alert,
    list_active_alerts,
    list_archived_alerts,
    list_watchlist_alerts,
)
from app.services.confirmation_service import confirm_alert_with_signal, run_pre_close_confirmation
from app.services.backtest_service import backtest_summary, list_backtests, run_backtest_for_decision, run_backtests_for_pending_buy_decisions
from app.services.dashboard_service import get_dashboard_summary
from app.services.decision_service import decision_summary, get_decision, list_decisions, list_decisions_by_ticker
from app.services.scanner_service import scan_watchlist
from app.services.scheduler_service import get_scheduler_status, run_scheduled_watchlist_scan, scheduler_loop
from app.services.watchlist_service import (
    create_watchlist_ticker,
    disable_watchlist_ticker,
    get_watchlist_ticker,
    list_enabled_watchlist_tickers,
    list_watchlist_tickers,
    seed_default_watchlist,
    update_watchlist_ticker,
)

# MVP: create tables on startup. Replace with Alembic migrations before production.
Base.metadata.create_all(bind=engine)
ensure_sqlite_schema()


@asynccontextmanager
async def lifespan(app: FastAPI):
    settings = get_settings()
    scheduler_task: asyncio.Task | None = None
    app.state.scheduler_enabled = settings.enable_scheduler

    if settings.enable_scheduler:
        scheduler_task = asyncio.create_task(
            scheduler_loop(SessionLocal, settings.scheduler_interval_seconds)
        )
        app.state.scheduler_task = scheduler_task

    try:
        yield
    finally:
        if scheduler_task is not None:
            scheduler_task.cancel()
            try:
                await scheduler_task
            except asyncio.CancelledError:
                pass


OPENAPI_TAGS = [
    {"name": "System", "description": "Estado general de la API."},
    {"name": "Webhooks", "description": "Integraciones entrantes desde TradingView y pruebas de Discord."},
    {"name": "Scanner", "description": "Ejecucion manual del scanner de oportunidades."},
    {"name": "Scheduler", "description": "Estado y ejecucion manual del scheduler automatico."},
    {"name": "Watchlist", "description": "Administracion de tickers monitoreados."},
    {"name": "Alerts", "description": "Consulta y administracion del ciclo de vida de alertas."},
    {"name": "Confirmations", "description": "Confirmacion pre-cierre de alertas activas."},
    {"name": "Decisions", "description": "Historial y resumen de decisiones del bot."},
    {"name": "Backtesting", "description": "Ejecucion y consulta de resultados de backtesting."},
    {"name": "Dashboard", "description": "Resumen centralizado del estado general del bot."},
]


app = FastAPI(title=get_settings().app_name, lifespan=lifespan, openapi_tags=OPENAPI_TAGS)


@app.get("/", tags=["System"], summary="Health check")
def health_check() -> dict[str, str]:
    return {"status": "ok", "app": get_settings().app_name}


@app.post("/webhooks/test-discord", tags=["Webhooks"], summary="Test Discord webhook")
async def test_discord_webhook() -> dict[str, str]:
    embed = {
        "title": "Mu Trading Bot - Test Discord",
        "description": "Webhook de Discord configurado correctamente.",
        "color": 0x3498DB,
    }
    await send_discord_message(content=None, embeds=[embed])
    return {"status": "discord_test_sent"}


@app.post("/webhooks/tradingview", response_model=AlertResponse, tags=["Webhooks"], summary="Receive TradingView signal")
async def tradingview_webhook(
    signal: TradingViewSignal,
    _: None = Depends(validate_tradingview_secret),
    db: Session = Depends(get_db),
) -> AlertResponse:
    _alert, score, risk = await create_alert(db, signal)
    return AlertResponse(status="alert_sent", ticker=signal.ticker, score=score, risk=risk)


def _scanner_payload_from_result(result, debug: bool, session_status: str | None = None) -> ScannerResponse:
    skipped = []
    for item in result.skipped:
        payload = {"ticker": item.ticker, "status": item.status, "reason": item.reason}
        if debug and item.debug is not None:
            payload["debug"] = item.debug
        skipped.append(payload)

    created = None
    if debug:
        created = [
            {
                "ticker": item.ticker,
                "status": item.status,
                "reason": item.reason,
                "debug": item.debug,
            }
            for item in result.created_debug
        ]

    created_active_alerts = sum(1 for alert in result.created_alerts if getattr(alert, "status", None) == AlertStatus.EN_OBSERVACION.value)
    created_watchlist = sum(1 for alert in result.created_alerts if getattr(alert, "status", None) == AlertStatus.WATCHLIST.value)
    return ScannerResponse(
        status="scanner_completed",
        session_status=session_status,
        scanned=result.scanned,
        created_alerts=len(result.created_alerts),
        created_active_alerts=created_active_alerts,
        created_watchlist=created_watchlist,
        created_tickers=result.created_tickers,
        skipped=skipped,
        created=created,
    )


async def _run_scanner_for_tickers(
    tickers: list[str],
    allow_after_hours: bool,
    debug: bool,
    force_alert: bool,
    db: Session,
) -> ScannerResponse:
    current_datetime = datetime.now(UTC)
    session_status = get_market_session_status(current_datetime)
    market_open = is_market_open(current_datetime)

    if not market_open and not allow_after_hours:
        return ScannerResponse(
            status="market_closed",
            session_status=session_status,
            scanned=len(tickers),
            created_alerts=0,
            created_active_alerts=0,
            created_watchlist=0,
            created_tickers=[],
            skipped=[],
            message="Mercado cerrado. Ejecutar scanner en horario de mercado o usar allow_after_hours=true para watchlist.",
        )

    alert_status = AlertStatus.EN_OBSERVACION if market_open else AlertStatus.WATCHLIST
    watchlist = not market_open and allow_after_hours
    result = await scan_watchlist(
        db,
        tickers,
        force_alert=force_alert,
        alert_status=alert_status,
        watchlist=watchlist,
    )
    return _scanner_payload_from_result(result, debug=debug, session_status=None if market_open else session_status)


@app.post("/scanner/run", response_model=ScannerResponse, response_model_exclude_none=True, tags=["Scanner"], summary="Run scanner")
async def run_scanner(
    request: ScannerRequest,
    allow_after_hours: bool = Query(default=False),
    debug: bool = Query(default=False),
    force_alert: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> ScannerResponse:
    return await _run_scanner_for_tickers(
        request.tickers,
        allow_after_hours=allow_after_hours,
        debug=debug,
        force_alert=force_alert,
        db=db,
    )


@app.post("/scanner/run-watchlist", response_model=ScannerResponse, response_model_exclude_none=True, tags=["Scanner"], summary="Run watchlist scanner")
async def run_watchlist_scanner(
    allow_after_hours: bool = Query(default=False),
    debug: bool = Query(default=False),
    force_alert: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> ScannerResponse:
    tickers = [item.ticker for item in list_enabled_watchlist_tickers(db)]
    return await _run_scanner_for_tickers(
        tickers,
        allow_after_hours=allow_after_hours,
        debug=debug,
        force_alert=force_alert,
        db=db,
    )


@app.get("/dashboard/summary", response_model=DashboardSummaryResponse, tags=["Dashboard"], summary="Get dashboard summary")
def dashboard_summary(db: Session = Depends(get_db)) -> DashboardSummaryResponse:
    return get_dashboard_summary(db)

@app.get("/scheduler/status", tags=["Scheduler"], summary="Get scheduler status")
def scheduler_status() -> dict:
    settings = get_settings()
    return get_scheduler_status(settings.enable_scheduler, settings.scheduler_interval_seconds)


@app.post("/scheduler/run-once", tags=["Scheduler"], summary="Run scheduler once")
async def scheduler_run_once() -> dict:
    return await run_scheduled_watchlist_scan(SessionLocal)


@app.get("/watchlist", response_model=list[WatchlistTickerResponse], tags=["Watchlist"], summary="Get watchlist")
def get_watchlist(db: Session = Depends(get_db)) -> list:
    return list_watchlist_tickers(db)


@app.post("/watchlist", response_model=WatchlistTickerResponse, status_code=status.HTTP_201_CREATED, tags=["Watchlist"], summary="Add watchlist ticker")
def add_watchlist_ticker(
    payload: WatchlistTickerCreate,
    db: Session = Depends(get_db),
):
    existing = get_watchlist_ticker(db, payload.ticker, payload.market)
    if existing is not None:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail="Ticker already exists in watchlist")
    return create_watchlist_ticker(db, payload)


@app.post("/watchlist/seed-defaults", tags=["Watchlist"], summary="Seed default watchlist")
def seed_watchlist_defaults(db: Session = Depends(get_db)) -> dict:
    created = seed_default_watchlist(db)
    return {
        "status": "watchlist_seeded",
        "created": len(created),
        "tickers": [item.ticker for item in created],
    }


@app.patch("/watchlist/{ticker}", response_model=WatchlistTickerResponse, tags=["Watchlist"], summary="Update watchlist ticker")
def patch_watchlist_ticker(
    ticker: str,
    payload: WatchlistTickerUpdate,
    db: Session = Depends(get_db),
):
    item = get_watchlist_ticker(db, ticker)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist ticker not found")
    return update_watchlist_ticker(db, item, payload)


@app.delete("/watchlist/{ticker}", response_model=WatchlistTickerResponse, tags=["Watchlist"], summary="Disable watchlist ticker")
def delete_watchlist_ticker(
    ticker: str,
    db: Session = Depends(get_db),
):
    item = get_watchlist_ticker(db, ticker)
    if item is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Watchlist ticker not found")
    return disable_watchlist_ticker(db, item)


def _alert_payload(alert: Alert) -> dict:
    return {
        "id": alert.id,
        "ticker": alert.ticker,
        "market": alert.market,
        "timeframe": alert.timeframe,
        "source": alert.source,
        "reason": alert.reason,
        "score": alert.preliminary_score,
        "risk": alert.preliminary_risk,
        "entry_price": alert.entry_price,
        "risk_reward": alert.risk_reward,
        "status": alert.status,
        "created_at": alert.created_at.isoformat(),
    }


@app.get("/alerts/active", tags=["Alerts"], summary="Get active alerts")
def active_alerts(db: Session = Depends(get_db)) -> list[dict]:
    return [_alert_payload(alert) for alert in list_active_alerts(db)]


@app.get("/alerts/watchlist", tags=["Alerts"], summary="Get watchlist alerts")
def watchlist_alerts(db: Session = Depends(get_db)) -> list[dict]:
    return [_alert_payload(alert) for alert in list_watchlist_alerts(db)]


@app.get("/alerts/archived", tags=["Alerts"], summary="Get archived alerts")
def archived_alerts(db: Session = Depends(get_db)) -> list[dict]:
    return [_alert_payload(alert) for alert in list_archived_alerts(db)]


@app.patch("/alerts/{alert_id}/archive", tags=["Alerts"], summary="Archive alert")
def archive_single_alert(alert_id: int, db: Session = Depends(get_db)) -> dict:
    alert = db.get(Alert, alert_id)
    if alert is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Alert not found")
    return _alert_payload(archive_alert(db, alert))


@app.post("/alerts/archive-watchlist", tags=["Alerts"], summary="Archive watchlist alerts")
def archive_all_watchlist_alerts(db: Session = Depends(get_db)) -> dict:
    archived_count = archive_watchlist_alerts(db)
    return {"status": "archived", "archived_count": archived_count}


@app.post("/alerts/archive-test-alerts", tags=["Alerts"], summary="Archive test alerts")
def archive_all_test_alerts(db: Session = Depends(get_db)) -> dict:
    archived_count = archive_test_alerts(db)
    return {"status": "archived", "archived_count": archived_count}


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


@app.get("/decisions", tags=["Decisions"], summary="Get decisions")
def decisions_history(db: Session = Depends(get_db)) -> list[dict]:
    return [_decision_payload(decision) for decision in list_decisions(db)]


@app.get("/decisions/summary", tags=["Decisions"], summary="Get decisions summary")
def decisions_summary(db: Session = Depends(get_db)) -> dict:
    return decision_summary(db)


@app.get("/decisions/by-ticker/{ticker}", tags=["Decisions"], summary="Get decisions by ticker")
def decisions_history_by_ticker(ticker: str, db: Session = Depends(get_db)) -> list[dict]:
    return [_decision_payload(decision) for decision in list_decisions_by_ticker(db, ticker)]


@app.get("/decisions/{decision_id}", tags=["Decisions"], summary="Get decision")
def decision_detail(decision_id: int, db: Session = Depends(get_db)) -> dict:
    decision = get_decision(db, decision_id)
    if decision is None:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Decision not found")
    return _decision_payload(decision)


def _backtest_payload(result: BacktestResult) -> BacktestResultResponse:
    return BacktestResultResponse.model_validate(result)


@app.post("/backtests/decisions/{decision_id}", response_model=BacktestResultResponse, tags=["Backtesting"], summary="Run decision backtesting")
def backtest_decision(
    decision_id: int,
    days: int = Query(default=10, ge=1, le=120),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> BacktestResultResponse:
    return _backtest_payload(run_backtest_for_decision(db, decision_id, days=days, force=force))


@app.post("/backtests/run", response_model=BacktestRunResponse, tags=["Backtesting"], summary="Run backtesting")
def run_pending_backtests(
    days: int = Query(default=10, ge=1, le=120),
    force: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> BacktestRunResponse:
    results, skipped = run_backtests_for_pending_buy_decisions(db, days=days, force=force)
    return BacktestRunResponse(
        status="backtest_completed",
        requested=len(results) + skipped,
        created=len(results),
        skipped=skipped,
        results=[_backtest_payload(result) for result in results],
    )


@app.get("/backtests", response_model=list[BacktestResultResponse], tags=["Backtesting"], summary="Get backtests")
def backtests_history(db: Session = Depends(get_db)) -> list[BacktestResultResponse]:
    return [_backtest_payload(result) for result in list_backtests(db)]


@app.get("/backtests/summary", tags=["Backtesting"], summary="Get backtesting summary")
def backtests_summary(
    include_errors: bool = Query(default=False),
    db: Session = Depends(get_db),
) -> dict:
    return backtest_summary(db, include_errors=include_errors)


@app.post("/confirmations/pre-close/{alert_id}", tags=["Confirmations"], summary="Confirm alert pre-close")
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
@app.post("/confirmations/pre-close", tags=["Confirmations"], summary="Run pre-close confirmation")
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
