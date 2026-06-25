from fastapi.testclient import TestClient

import app.services.scheduler_service as scheduler_service
from app.config import get_settings
from app.main import app

def test_dashboard_summary_returns_200(client):
    response = client.get("/dashboard/summary")

    assert response.status_code == 200


def test_dashboard_summary_contains_main_sections(client):
    payload = client.get("/dashboard/summary").json()

    assert set(payload) == {"scanner", "decisions", "backtesting", "scheduler"}


def test_dashboard_scanner_summary_contains_expected_fields(client):
    scanner = client.get("/dashboard/summary").json()["scanner"]

    assert {"watchlist_enabled_count", "active_alerts", "watchlist_alerts", "archived_alerts"}.issubset(scanner)


def test_dashboard_decisions_summary_contains_expected_fields(client):
    decisions = client.get("/dashboard/summary").json()["decisions"]

    assert {"total", "compramos", "no_compramos", "by_risk"}.issubset(decisions)
    assert isinstance(decisions["by_risk"], dict)


def test_dashboard_backtesting_summary_contains_expected_fields(client):
    backtesting = client.get("/dashboard/summary").json()["backtesting"]

    assert {
        "total",
        "target_hit",
        "stop_hit",
        "no_result",
        "ambiguous",
        "error",
        "win_rate",
        "average_pnl_percent",
    }.issubset(backtesting)


def test_dashboard_scheduler_summary_contains_expected_fields(client):
    scheduler = client.get("/dashboard/summary").json()["scheduler"]

    assert {"enabled", "interval_seconds", "is_running", "last_run_at", "last_result"}.issubset(scheduler)


def test_dashboard_endpoint_appears_under_dashboard_tag(client):
    schema = client.get("/openapi.json").json()
    operation = schema["paths"]["/dashboard/summary"]["get"]

    assert operation["tags"] == ["Dashboard"]
    assert operation["summary"] == "Get dashboard summary"
    assert any(tag["name"] == "Dashboard" for tag in schema["tags"])

def test_dashboard_reflects_running_scheduler_when_enabled(monkeypatch):
    scheduler_service.is_running = False
    monkeypatch.setenv("ENABLE_SCHEDULER", "true")
    monkeypatch.setenv("SCHEDULER_INTERVAL_SECONDS", "1200")
    get_settings.cache_clear()

    try:
        with TestClient(app) as test_client:
            scheduler = test_client.get("/dashboard/summary").json()["scheduler"]
            assert scheduler["enabled"] is True
            assert scheduler["interval_seconds"] == 1200
            assert scheduler["is_running"] is True
    finally:
        get_settings.cache_clear()
        scheduler_service.is_running = False