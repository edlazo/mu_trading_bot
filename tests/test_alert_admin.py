from datetime import UTC, datetime

import pytest

import app.services.scanner_service as scanner_service
from app.models.alert import Alert
from app.schemas.alert import AlertStatus, OpportunitySource
from app.schemas.tradingview import TradingViewSignal
from app.services.scanner_service import ScannerTickerResult, scan_watchlist
from tests.test_webhook import EXAMPLE_SIGNAL


def _create_operational_alert(client, reason: str | None = None) -> int:
    payload = {**EXAMPLE_SIGNAL}
    if reason is not None:
        payload["reason"] = reason
    response = client.post(
        "/webhooks/tradingview",
        json=payload,
        headers={"X-Webhook-Secret": "test-secret"},
    )
    assert response.status_code == 200
    return client.get("/alerts/active").json()[0]["id"]


def _db_alert(ticker: str = "AAPL", status: AlertStatus = AlertStatus.WATCHLIST, reason: str = "scanner") -> Alert:
    return Alert(
        ticker=ticker,
        market="USA",
        timeframe="1D",
        source="mixed",
        reason=reason,
        close=100,
        preliminary_score=70,
        preliminary_risk="MEDIO",
        status=status.value,
    )


def _signal(ticker: str = "AAPL") -> TradingViewSignal:
    return TradingViewSignal(
        ticker=ticker,
        source=OpportunitySource.MIXED,
        reason="scanner",
        close=100,
        target=120,
        stop_loss=90,
    )


def test_archive_single_alert(client):
    alert_id = _create_operational_alert(client)

    response = client.patch(f"/alerts/{alert_id}/archive")

    assert response.status_code == 200
    assert response.json()["status"] == AlertStatus.ARCHIVED.value
    assert client.get("/alerts/active").json() == []


def test_archive_missing_alert_returns_404(client):
    response = client.patch("/alerts/999/archive")

    assert response.status_code == 404


def test_archive_watchlist_archives_all_watchlist(client, db_session):
    db_session.add(_db_alert("AAPL", AlertStatus.WATCHLIST))
    db_session.add(_db_alert("MSFT", AlertStatus.WATCHLIST))
    db_session.add(_db_alert("NVDA", AlertStatus.EN_OBSERVACION))
    db_session.commit()

    response = client.post("/alerts/archive-watchlist")

    assert response.status_code == 200
    assert response.json() == {"status": "archived", "archived_count": 2}
    assert client.get("/alerts/watchlist").json() == []
    assert len(client.get("/alerts/archived").json()) == 2


def test_archive_test_alerts_archives_matching_reasons(client, db_session):
    db_session.add(_db_alert("AAPL", AlertStatus.EN_OBSERVACION, "Alerta forzada para test del scanner."))
    db_session.add(_db_alert("MSFT", AlertStatus.WATCHLIST, "prueba manual"))
    db_session.add(_db_alert("NVDA", AlertStatus.EN_OBSERVACION, "setup real"))
    db_session.commit()

    response = client.post("/alerts/archive-test-alerts")

    assert response.status_code == 200
    assert response.json() == {"status": "archived", "archived_count": 2}
    archived = client.get("/alerts/archived").json()
    assert {item["ticker"] for item in archived} == {"AAPL", "MSFT"}


def test_archived_endpoint_returns_archived_alerts(client, db_session):
    db_session.add(_db_alert("AAPL", AlertStatus.ARCHIVED))
    db_session.commit()

    response = client.get("/alerts/archived")

    assert response.status_code == 200
    assert response.json()[0]["status"] == AlertStatus.ARCHIVED.value


def test_watchlist_does_not_return_archived(client, db_session):
    db_session.add(_db_alert("AAPL", AlertStatus.WATCHLIST))
    db_session.add(_db_alert("MSFT", AlertStatus.ARCHIVED))
    db_session.commit()

    response = client.get("/alerts/watchlist")

    assert response.status_code == 200
    assert [item["ticker"] for item in response.json()] == ["AAPL"]


def test_active_does_not_return_watchlist_or_archived(client, db_session):
    db_session.add(_db_alert("AAPL", AlertStatus.EN_OBSERVACION))
    db_session.add(_db_alert("MSFT", AlertStatus.WATCHLIST))
    db_session.add(_db_alert("NVDA", AlertStatus.ARCHIVED))
    db_session.commit()

    response = client.get("/alerts/active")

    assert response.status_code == 200
    assert [item["ticker"] for item in response.json()] == ["AAPL"]


@pytest.mark.asyncio
async def test_after_hours_scanner_does_not_duplicate_watchlist_same_day(db_session, monkeypatch):
    existing = _db_alert("AAPL", AlertStatus.WATCHLIST)
    existing.created_at = datetime.now(UTC)
    db_session.add(existing)
    db_session.commit()
    calls = 0

    def fake_scan_ticker(ticker, force_alert=False):
        nonlocal calls
        calls += 1
        return ScannerTickerResult(ticker=ticker, signal=_signal(ticker), status="alert_created", reason="scanner")

    monkeypatch.setattr(scanner_service, "scan_ticker", fake_scan_ticker)

    result = await scan_watchlist(
        db_session,
        ["AAPL"],
        alert_status=AlertStatus.WATCHLIST,
        watchlist=True,
    )

    assert result.created_alerts == []
    assert result.skipped[0].status == "duplicate_watchlist"
    assert result.skipped[0].reason == "Ya existe una watchlist para este ticker hoy"
    assert calls == 0


def test_alert_admin_routes_are_registered_in_openapi(client):
    paths = client.get("/openapi.json").json()["paths"]

    assert "patch" in paths["/alerts/{alert_id}/archive"]
    assert "post" in paths["/alerts/archive-watchlist"]
    assert "post" in paths["/alerts/archive-test-alerts"]
    assert "get" in paths["/alerts/archived"]
