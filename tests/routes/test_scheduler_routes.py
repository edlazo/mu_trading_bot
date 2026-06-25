from datetime import datetime
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import app.services.scheduler_service as scheduler_service
from app.config import get_settings
from app.main import app
from app.services.scanner_service import ScannerWatchlistResult
from app.services.scheduler_service import run_scheduled_watchlist_scan

NEW_YORK = ZoneInfo("America/New_York")


def reset_scheduler_state():
    scheduler_service.is_running = False
    scheduler_service.is_scan_running = False
    scheduler_service.scanner_batch_offset = 0
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
scheduler_service.scanner_batch_offset = 0




def test_scheduler_starts_on_lifespan_when_enabled(monkeypatch):
    reset_scheduler_state()
    monkeypatch.setenv("ENABLE_SCHEDULER", "true")
    monkeypatch.setenv("SCHEDULER_INTERVAL_SECONDS", "1200")
    get_settings.cache_clear()

    try:
        with TestClient(app) as test_client:
            response = test_client.get("/scheduler/status")
            assert response.status_code == 200
            payload = response.json()
            assert payload["enabled"] is True
            assert payload["interval_seconds"] == 1200
            assert payload["is_running"] is True
    finally:
        get_settings.cache_clear()
        scheduler_service.is_running = False


def test_market_closed_run_once_does_not_stop_scheduler_loop(client, monkeypatch):
    reset_scheduler_state()
    scheduler_service.is_running = True
    client.post("/watchlist", json={"ticker": "AAPL", "market": "USA"})

    monkeypatch.setattr("app.services.scheduler_service.is_market_open", lambda current_datetime: False)
    monkeypatch.setattr("app.services.scheduler_service.get_market_session_status", lambda current_datetime: "post_market")

    response = client.post("/scheduler/run-once")

    assert response.status_code == 200
    assert response.json()["status"] == "market_closed"
    assert client.get("/scheduler/status").json()["is_running"] is True
    scheduler_service.is_running = False

def test_scheduler_batch_advances_offset_and_resets(client, monkeypatch):
    reset_scheduler_state()
    import asyncio

    for ticker in ["TSLA", "AAPL", "NVDA", "MSFT"]:
        client.post("/watchlist", json={"ticker": ticker, "market": "USA"})

    scanned_batches = []

    async def fake_scan_watchlist(db, tickers, **kwargs):
        scanned_batches.append(tickers)
        return ScannerWatchlistResult(scanned=len(tickers), created_alerts=[], skipped=[])

    monkeypatch.setattr("app.services.scheduler_service.is_market_open", lambda current_datetime: True)
    monkeypatch.setattr("app.services.scheduler_service.get_market_session_status", lambda current_datetime: "open")
    monkeypatch.setattr("app.services.scheduler_service.scan_watchlist", fake_scan_watchlist)

    first = asyncio.run(run_scheduled_watchlist_scan(__import__("app.database.session", fromlist=["SessionLocal"]).SessionLocal, scanner_batch_size=2))
    second = asyncio.run(run_scheduled_watchlist_scan(__import__("app.database.session", fromlist=["SessionLocal"]).SessionLocal, scanner_batch_size=2))

    assert scanned_batches == [["AAPL", "MSFT"], ["NVDA", "TSLA"]]
    assert first["offset"] == 0
    assert first["next_offset"] == 2
    assert first["has_more"] is True
    assert second["offset"] == 2
    assert second["has_more"] is False
    assert second["next_offset"] is None
    assert scheduler_service.scanner_batch_offset == 0
