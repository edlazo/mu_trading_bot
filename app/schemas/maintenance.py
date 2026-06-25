from pydantic import BaseModel


class MaintenanceTestDataSummary(BaseModel):
    test_alerts: int
    test_decisions: int
    test_backtests: int
    archived_test_alerts: int
    active_test_alerts: int


class MaintenanceCleanupResponse(BaseModel):
    dry_run: bool
    would_archive_test_alerts: int
    would_delete_test_backtests: int
    archived_test_alerts: int
    deleted_test_backtests: int