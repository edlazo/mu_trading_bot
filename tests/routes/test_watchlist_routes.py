from datetime import datetime
from zoneinfo import ZoneInfo

import pytest

import app.services.scanner_service as scanner_service
from app.schemas.alert import AlertStatus
from app.services.scheduler_service import run_scheduler_check


def test_create_watchlist_ticker(client):
    response = client.post("/watchlist", json={"ticker": "AAPL", "market": "USA", "notes": "Big tech"})

    assert response.status_code == 201
    payload = response.json()
    assert payload["ticker"] == "AAPL"
    assert payload["market"] == "USA"
    assert payload["enabled"] is True
    assert payload["notes"] == "Big tech"


def test_watchlist_does_not_allow_duplicates(client):
    first = client.post("/watchlist", json={"ticker": "AAPL", "market": "USA"})
    second = client.post("/watchlist", json={"ticker": "aapl", "market": "usa"})

    assert first.status_code == 201
    assert second.status_code == 409


def test_get_watchlist_returns_tickers(client):
    client.post("/watchlist", json={"ticker": "AAPL", "market": "USA"})
    client.post("/watchlist", json={"ticker": "MSFT", "market": "USA"})

    response = client.get("/watchlist")

    assert response.status_code == 200
    tickers = [item["ticker"] for item in response.json()]
    assert tickers == ["AAPL", "MSFT"]


def test_patch_watchlist_disables_ticker(client):
    client.post("/watchlist", json={"ticker": "AAPL", "market": "USA"})

    response = client.patch("/watchlist/AAPL", json={"enabled": False, "notes": "paused"})

    assert response.status_code == 200
    payload = response.json()
    assert payload["enabled"] is False
    assert payload["notes"] == "paused"


def test_delete_watchlist_disables_ticker(client):
    client.post("/watchlist", json={"ticker": "AAPL", "market": "USA"})

    response = client.delete("/watchlist/AAPL")

    assert response.status_code == 200
    assert response.json()["enabled"] is False


def test_scanner_run_watchlist_uses_only_enabled_tickers(client, monkeypatch):
    client.post("/watchlist", json={"ticker": "AAPL", "market": "USA"})
    client.post("/watchlist", json={"ticker": "MSFT", "market": "USA"})
    client.patch("/watchlist/MSFT", json={"enabled": False})
    captured = {}

    async def fake_scan_watchlist(db, tickers, force_alert=False, **kwargs):
        captured["tickers"] = tickers
        return scanner_service.ScannerWatchlistResult(scanned=len(tickers), created_alerts=[], skipped=[])

    monkeypatch.setattr("app.main.is_market_open", lambda current_datetime: True)
    monkeypatch.setattr("app.main.get_market_session_status", lambda current_datetime: "open")
    monkeypatch.setattr("app.main.scan_watchlist", fake_scan_watchlist)

    response = client.post("/scanner/run-watchlist")

    assert response.status_code == 200
    assert captured["tickers"] == ["AAPL"]
    assert response.json()["scanned"] == 1


def test_scanner_run_watchlist_respects_market_closed(client, monkeypatch):
    client.post("/watchlist", json={"ticker": "AAPL", "market": "USA"})
    monkeypatch.setattr("app.main.is_market_open", lambda current_datetime: False)
    monkeypatch.setattr("app.main.get_market_session_status", lambda current_datetime: "post_market")

    response = client.post("/scanner/run-watchlist")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "market_closed"
    assert payload["created_alerts"] == 0
    assert payload["scanned"] == 1


@pytest.mark.asyncio
async def test_scheduler_watchlist_scanner_runs_when_market_open(monkeypatch):
    calls = 0

    class FakeSession:
        def close(self):
            pass

    def db_session_factory():
        return FakeSession()

    async def fake_watchlist_scanner(db):
        nonlocal calls
        calls += 1
        return scanner_service.ScannerWatchlistResult(scanned=0, created_alerts=[], skipped=[])

    current_datetime = datetime(2026, 6, 23, 10, 0, tzinfo=ZoneInfo("America/New_York"))

    ran = await run_scheduler_check(
        db_session_factory,
        current_datetime=current_datetime,
        watchlist_scanner_runner=fake_watchlist_scanner,
    )

    assert ran is True
    assert calls == 1


def test_seed_default_watchlist(client):
    response = client.post("/watchlist/seed-defaults")

    assert response.status_code == 200
    payload = response.json()
    assert payload["status"] == "watchlist_seeded"
    assert payload["created"] >= 17
    assert "AAPL" in payload["tickers"]
