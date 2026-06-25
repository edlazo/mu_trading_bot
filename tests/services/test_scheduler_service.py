from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import app.services.scheduler_service as scheduler_service
from app.config import get_settings
from app.core.market_hours import (
    USA_MARKET_HOURS,
    get_confirmation_time,
    get_market_session_status,
    is_confirmation_time,
    is_market_open,
    is_weekday_market_day,
)
from app.main import app
from app.models.alert import Alert
from app.schemas.tradingview import TradingViewSignal
from app.services.market_data_service import get_updated_signal_for_alert
from app.services.scheduler_service import run_scheduled_pre_close_confirmation, run_scheduler_check
from tests.routes.test_webhook_routes import EXAMPLE_SIGNAL

NEW_YORK = ZoneInfo("America/New_York")


@pytest.mark.asyncio
async def test_scheduler_calls_confirmation_runner():
    called = False

    async def fake_confirmation_runner(db):
        nonlocal called
        called = True
        assert db == "db-session"
        return []

    decisions = await run_scheduled_pre_close_confirmation("db-session", fake_confirmation_runner)

    assert called is True
    assert decisions == []



@pytest.mark.asyncio
async def test_scheduler_does_not_execute_twice_on_same_market_day():
    scheduler_service.last_confirmation_date = None
    calls = 0

    class FakeSession:
        def close(self):
            pass

    def db_session_factory():
        return FakeSession()

    async def fake_confirmation_runner(db):
        nonlocal calls
        calls += 1
        return []

    current_datetime = datetime(2026, 6, 23, 15, 30, 30, tzinfo=NEW_YORK)

    async def fake_watchlist_scanner(db):
        return []

    first_run = await run_scheduler_check(db_session_factory, current_datetime, fake_confirmation_runner, fake_watchlist_scanner)
    second_run = await run_scheduler_check(db_session_factory, current_datetime, fake_confirmation_runner, fake_watchlist_scanner)

    assert first_run is True
    assert second_run is True
    assert calls == 1

    scheduler_service.last_confirmation_date = None



def test_scheduler_is_disabled_by_default_in_settings():
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.enable_scheduler is False



def test_scheduler_does_not_start_automatically_when_disabled():
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        assert test_client.app.state.scheduler_enabled is False
        assert not hasattr(test_client.app.state, "scheduler_task")




from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import app.services.scheduler_service as scheduler_service
from app.services.scanner_service import ScannerWatchlistResult
from app.services.scheduler_service import run_scheduled_watchlist_scan

NEW_YORK = ZoneInfo("America/New_York")


def reset_scheduler_state():
    scheduler_service.is_scan_running = False
    scheduler_service.last_run_at = None
    scheduler_service.last_result = None
    scheduler_service.last_confirmation_date = None
    scheduler_service.last_confirmation_at = None
    scheduler_service.last_confirmation_result = None



@pytest.mark.asyncio
async def test_run_scheduled_watchlist_scan_uses_only_enabled_tickers(db_session, monkeypatch):
    reset_scheduler_state()
    from app.models.watchlist import WatchlistTicker

    db_session.add(WatchlistTicker(ticker="AAPL", market="USA", enabled=True))
    db_session.add(WatchlistTicker(ticker="MSFT", market="USA", enabled=False))
    db_session.commit()
    captured = {}

    class Factory:
        def __call__(self):
            return db_session

    async def fake_scan_watchlist(db, tickers, **kwargs):
        captured["tickers"] = tickers
        return ScannerWatchlistResult(scanned=len(tickers), created_alerts=[], skipped=[])

    monkeypatch.setattr("app.services.scheduler_service.is_market_open", lambda current_datetime: True)
    monkeypatch.setattr("app.services.scheduler_service.get_market_session_status", lambda current_datetime: "open")
    monkeypatch.setattr("app.services.scheduler_service.scan_watchlist", fake_scan_watchlist)

    result = await run_scheduled_watchlist_scan(Factory(), datetime(2026, 6, 23, 10, 0, tzinfo=NEW_YORK))

    assert result["status"] == "scanner_completed"
    assert captured["tickers"] == ["AAPL"]



@pytest.mark.asyncio
async def test_scheduler_status_includes_confirmation_state_after_run(db_session):
    reset_scheduler_state()
    from app.models.decision import Decision

    class Factory:
        def __call__(self):
            return db_session

    async def fake_confirmation_runner(db):
        return [
            Decision(
                alert_id=1,
                ticker="AAPL",
                final_score=80,
                final_risk="BAJO ??",
                decision="COMPRAMOS",
                reason="ok",
            )
        ]

    async def fake_watchlist_scanner(db):
        return ScannerWatchlistResult(scanned=0, created_alerts=[], skipped=[])

    await scheduler_service.run_scheduler_check(
        Factory(),
        datetime(2026, 6, 23, 15, 30, 30, tzinfo=NEW_YORK),
        fake_confirmation_runner,
        fake_watchlist_scanner,
    )

    payload = scheduler_service.get_scheduler_status(False, 300)
    assert payload["last_confirmation_date"] == "2026-06-23"
    assert payload["last_confirmation_result"]["confirmed"] == 1
    assert payload["last_confirmation_result"]["rejected"] == 0



@pytest.mark.asyncio
async def test_scheduler_executes_confirmation_when_confirmation_time(db_session):
    reset_scheduler_state()
    calls = 0

    class Factory:
        def __call__(self):
            return db_session

    async def fake_confirmation_runner(db):
        nonlocal calls
        calls += 1
        return []

    async def fake_watchlist_scanner(db):
        return ScannerWatchlistResult(scanned=0, created_alerts=[], skipped=[])

    result = await scheduler_service.run_scheduler_check(
        Factory(),
        datetime(2026, 6, 23, 15, 30, 0, tzinfo=NEW_YORK),
        fake_confirmation_runner,
        fake_watchlist_scanner,
    )

    assert result is True
    assert calls == 1
    assert scheduler_service.last_confirmation_date.isoformat() == "2026-06-23"



@pytest.mark.asyncio
async def test_scheduler_does_not_execute_confirmation_twice_same_day(db_session):
    reset_scheduler_state()
    calls = 0

    class Factory:
        def __call__(self):
            return db_session

    async def fake_confirmation_runner(db):
        nonlocal calls
        calls += 1
        return []

    async def fake_watchlist_scanner(db):
        return ScannerWatchlistResult(scanned=0, created_alerts=[], skipped=[])

    current_datetime = datetime(2026, 6, 23, 15, 30, 30, tzinfo=NEW_YORK)
    await scheduler_service.run_scheduler_check(Factory(), current_datetime, fake_confirmation_runner, fake_watchlist_scanner)
    await scheduler_service.run_scheduler_check(Factory(), current_datetime, fake_confirmation_runner, fake_watchlist_scanner)

    assert calls == 1
