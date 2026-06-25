from app.models.alert import Alert
from app.models.backtest import BacktestResult
from app.models.decision import Decision
from app.schemas.alert import AlertStatus


def _alert(ticker: str, status: AlertStatus = AlertStatus.EN_OBSERVACION) -> Alert:
    return Alert(
        ticker=ticker,
        market="USA",
        timeframe="1D",
        source="mixed",
        reason="test",
        close=100,
        preliminary_score=70,
        preliminary_risk="MEDIO",
        status=status.value,
    )


def _decision(ticker: str, alert_id: int = 1) -> Decision:
    return Decision(
        alert_id=alert_id,
        ticker=ticker,
        final_score=80,
        final_risk="BAJO",
        decision="COMPRAMOS",
        reason="test",
    )


def _backtest(ticker: str, decision_id: int = 1, alert_id: int = 1) -> BacktestResult:
    return BacktestResult(
        decision_id=decision_id,
        alert_id=alert_id,
        ticker=ticker,
        result="ERROR",
        days_checked=0,
        reason="test",
    )


def test_maintenance_test_data_summary_returns_200(client):
    response = client.get("/maintenance/test-data/summary")

    assert response.status_code == 200


def test_maintenance_test_data_summary_detects_test_records(client, db_session):
    db_session.add(_alert("TEST_ALERT"))
    db_session.add(_alert("TEST_ARCHIVED", AlertStatus.ARCHIVED))
    db_session.add(_decision("TEST_DECISION"))
    db_session.add(_backtest("TEST_BACKTEST"))
    db_session.commit()

    response = client.get("/maintenance/test-data/summary")

    assert response.status_code == 200
    assert response.json() == {
        "test_alerts": 2,
        "test_decisions": 1,
        "test_backtests": 1,
        "archived_test_alerts": 1,
        "active_test_alerts": 1,
    }


def test_maintenance_cleanup_dry_run_does_not_modify_database(client, db_session):
    db_session.add(_alert("TEST_ALERT"))
    db_session.add(_backtest("TEST_BACKTEST"))
    db_session.add(_decision("TEST_DECISION"))
    db_session.commit()

    response = client.post("/maintenance/cleanup-test-data?dry_run=true")

    assert response.status_code == 200
    assert response.json() == {
        "dry_run": True,
        "would_archive_test_alerts": 1,
        "would_delete_test_backtests": 1,
        "archived_test_alerts": 0,
        "deleted_test_backtests": 0,
    }
    assert db_session.query(Alert).filter(Alert.ticker == "TEST_ALERT").one().status != AlertStatus.ARCHIVED.value
    assert db_session.query(BacktestResult).filter(BacktestResult.ticker == "TEST_BACKTEST").count() == 1


def test_maintenance_cleanup_executes_when_dry_run_false(client, db_session):
    db_session.add(_alert("TEST_ALERT"))
    db_session.add(_backtest("TEST_BACKTEST"))
    db_session.add(_decision("TEST_DECISION"))
    db_session.commit()

    response = client.post("/maintenance/cleanup-test-data?dry_run=false")

    assert response.status_code == 200
    assert response.json() == {
        "dry_run": False,
        "would_archive_test_alerts": 0,
        "would_delete_test_backtests": 0,
        "archived_test_alerts": 1,
        "deleted_test_backtests": 1,
    }
    assert db_session.query(Alert).filter(Alert.ticker == "TEST_ALERT").one().status == AlertStatus.ARCHIVED.value
    assert db_session.query(BacktestResult).filter(BacktestResult.ticker == "TEST_BACKTEST").count() == 0
    assert db_session.query(Decision).filter(Decision.ticker == "TEST_DECISION").count() == 1


def test_maintenance_endpoint_appears_under_maintenance_tag(client):
    schema = client.get("/openapi.json").json()

    assert schema["paths"]["/maintenance/test-data/summary"]["get"]["tags"] == ["Maintenance"]
    assert schema["paths"]["/maintenance/cleanup-test-data"]["post"]["tags"] == ["Maintenance"]
    assert any(tag["name"] == "Maintenance" for tag in schema["tags"])