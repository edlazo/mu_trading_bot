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