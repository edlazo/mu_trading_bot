from sqlalchemy import func
from sqlalchemy.orm import Session

from app.models.alert import Alert
from app.models.backtest import BacktestResult
from app.models.decision import Decision
from app.schemas.alert import AlertStatus
from app.schemas.maintenance import MaintenanceCleanupResponse, MaintenanceTestDataSummary

TEST_TICKER_PREFIX = "TEST_"


def _is_test_ticker(column) -> object:
    return func.upper(column).like(f"{TEST_TICKER_PREFIX}%")


def get_test_data_summary(db: Session) -> MaintenanceTestDataSummary:
    test_alerts = db.query(Alert).filter(_is_test_ticker(Alert.ticker)).count()
    archived_test_alerts = (
        db.query(Alert)
        .filter(_is_test_ticker(Alert.ticker), Alert.status == AlertStatus.ARCHIVED.value)
        .count()
    )
    active_test_alerts = (
        db.query(Alert)
        .filter(_is_test_ticker(Alert.ticker), Alert.status != AlertStatus.ARCHIVED.value)
        .count()
    )

    return MaintenanceTestDataSummary(
        test_alerts=test_alerts,
        test_decisions=db.query(Decision).filter(_is_test_ticker(Decision.ticker)).count(),
        test_backtests=db.query(BacktestResult).filter(_is_test_ticker(BacktestResult.ticker)).count(),
        archived_test_alerts=archived_test_alerts,
        active_test_alerts=active_test_alerts,
    )


def cleanup_test_data(db: Session, dry_run: bool = True) -> MaintenanceCleanupResponse:
    alerts_to_archive = (
        db.query(Alert)
        .filter(_is_test_ticker(Alert.ticker), Alert.status != AlertStatus.ARCHIVED.value)
        .all()
    )
    backtests_to_delete = db.query(BacktestResult).filter(_is_test_ticker(BacktestResult.ticker)).all()

    if dry_run:
        return MaintenanceCleanupResponse(
            dry_run=True,
            would_archive_test_alerts=len(alerts_to_archive),
            would_delete_test_backtests=len(backtests_to_delete),
            archived_test_alerts=0,
            deleted_test_backtests=0,
        )

    for alert in alerts_to_archive:
        alert.status = AlertStatus.ARCHIVED.value

    for result in backtests_to_delete:
        db.delete(result)

    db.commit()

    return MaintenanceCleanupResponse(
        dry_run=False,
        would_archive_test_alerts=0,
        would_delete_test_backtests=0,
        archived_test_alerts=len(alerts_to_archive),
        deleted_test_backtests=len(backtests_to_delete),
    )