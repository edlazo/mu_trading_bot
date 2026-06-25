from app.models.alert import Alert
from app.models.backtest import BacktestResult
from app.models.decision import Decision
from app.schemas.alert import AlertStatus
from app.services.maintenance_service import cleanup_test_data, get_test_data_summary


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


def test_get_test_data_summary_counts_test_records(db_session):
    db_session.add(_alert("TEST_ALERT"))
    db_session.add(_alert("TEST_ARCHIVED", AlertStatus.ARCHIVED))
    db_session.add(_alert("AAPL"))
    db_session.add(_decision("TEST_DECISION"))
    db_session.add(_decision("MSFT"))
    db_session.add(_backtest("TEST_BACKTEST"))
    db_session.add(_backtest("NVDA"))
    db_session.commit()

    summary = get_test_data_summary(db_session)

    assert summary.test_alerts == 2
    assert summary.test_decisions == 1
    assert summary.test_backtests == 1
    assert summary.archived_test_alerts == 1
    assert summary.active_test_alerts == 1


def test_cleanup_test_data_dry_run_does_not_modify_database(db_session):
    db_session.add(_alert("TEST_ALERT"))
    db_session.add(_backtest("TEST_BACKTEST"))
    db_session.add(_decision("TEST_DECISION"))
    db_session.commit()

    response = cleanup_test_data(db_session, dry_run=True)

    assert response.dry_run is True
    assert response.would_archive_test_alerts == 1
    assert response.would_delete_test_backtests == 1
    assert response.archived_test_alerts == 0
    assert response.deleted_test_backtests == 0
    assert db_session.query(Alert).filter(Alert.ticker == "TEST_ALERT").one().status != AlertStatus.ARCHIVED.value
    assert db_session.query(BacktestResult).filter(BacktestResult.ticker == "TEST_BACKTEST").count() == 1
    assert db_session.query(Decision).filter(Decision.ticker == "TEST_DECISION").count() == 1


def test_cleanup_test_data_archives_alerts_and_deletes_backtests_only(db_session):
    db_session.add(_alert("TEST_ALERT"))
    db_session.add(_alert("AAPL"))
    db_session.add(_backtest("TEST_BACKTEST"))
    db_session.add(_backtest("MSFT"))
    db_session.add(_decision("TEST_DECISION"))
    db_session.commit()

    response = cleanup_test_data(db_session, dry_run=False)

    assert response.dry_run is False
    assert response.archived_test_alerts == 1
    assert response.deleted_test_backtests == 1
    assert db_session.query(Alert).filter(Alert.ticker == "TEST_ALERT").one().status == AlertStatus.ARCHIVED.value
    assert db_session.query(Alert).filter(Alert.ticker == "AAPL").one().status != AlertStatus.ARCHIVED.value
    assert db_session.query(BacktestResult).filter(BacktestResult.ticker == "TEST_BACKTEST").count() == 0
    assert db_session.query(BacktestResult).filter(BacktestResult.ticker == "MSFT").count() == 1
    assert db_session.query(Decision).filter(Decision.ticker == "TEST_DECISION").count() == 1