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


def test_scheduler_status_endpoint_returns_state(client):
    reset_scheduler_state()

    response = client.get("/scheduler/status")

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["interval_seconds"] == 300
    assert payload["is_running"] is False
    assert payload["last_run_at"] is None
    assert payload["last_result"] is None
    assert payload["last_confirmation_at"] is None
    assert payload["last_confirmation_result"] is None
    assert payload["last_confirmation_date"] is None


def test_scheduler_run_once_executes_watchlist_scanner(client, monkeypatch):
    reset_scheduler_state()
    client.post("/watchlist", json={"ticker": "AAPL", "market": "USA"})
    captured = {}

    async def fake_scan_watchlist(db, tickers, **kwargs):
        captured["tickers"] = tickers
        return ScannerWatchlistResult(scanned=len(tickers), created_alerts=[], skipped=[])

    monkeypatch.setattr("app.services.scheduler_service.is_market_open", lambda current_datetime: True)
    monkeypatch.setattr("app.services.scheduler_service.get_market_session_status", lambda current_datetime: "open")
    monkeypatch.setattr("app.services.scheduler_service.scan_watchlist", fake_scan_watchlist)

    response = client.post("/scheduler/run-once")

    assert response.status_code == 200
    assert captured["tickers"] == ["AAPL"]
    assert response.json()["status"] == "scanner_completed"
    assert response.json()["scanned"] == 1


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


def test_scheduler_run_once_market_closed_does_not_create_operational_alerts(client, monkeypatch):
    reset_scheduler_state()
    client.post("/watchlist", json={"ticker": "AAPL", "market": "USA"})

    monkeypatch.setattr("app.services.scheduler_service.is_market_open", lambda current_datetime: False)
    monkeypatch.setattr("app.services.scheduler_service.get_market_session_status", lambda current_datetime: "post_market")

    response = client.post("/scheduler/run-once")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "market_closed"
    assert payload["created_alerts"] == 0
    assert client.get("/alerts/active").json() == []


def test_scheduler_run_once_records_error_without_breaking_app(client, monkeypatch):
    reset_scheduler_state()

    async def failing_scan_watchlist(db, tickers, **kwargs):
        raise RuntimeError("boom")

    monkeypatch.setattr("app.services.scheduler_service.is_market_open", lambda current_datetime: True)
    monkeypatch.setattr("app.services.scheduler_service.get_market_session_status", lambda current_datetime: "open")
    monkeypatch.setattr("app.services.scheduler_service.scan_watchlist", failing_scan_watchlist)

    response = client.post("/scheduler/run-once")

    assert response.status_code == 200
    assert response.json() == {"status": "error", "error": "boom"}
    status_response = client.get("/scheduler/status")
    assert status_response.json()["last_result"] == {"status": "error", "error": "boom"}


def test_scheduler_run_once_skips_when_scan_is_running(client):
    reset_scheduler_state()
    scheduler_service.is_scan_running = True

    response = client.post("/scheduler/run-once")

    assert response.status_code == 200
    assert response.json() == {"status": "skipped", "reason": "scan_already_running"}
    scheduler_service.is_scan_running = False


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
