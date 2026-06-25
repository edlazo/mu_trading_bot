from datetime import datetime

from pydantic import BaseModel


class DashboardScannerSummary(BaseModel):
    watchlist_enabled_count: int
    active_alerts: int
    watchlist_alerts: int
    archived_alerts: int


class DashboardDecisionSummary(BaseModel):
    total: int
    compramos: int
    no_compramos: int
    by_risk: dict[str, int]


class DashboardBacktestSummary(BaseModel):
    total: int
    target_hit: int
    stop_hit: int
    no_result: int
    ambiguous: int
    error: int
    win_rate: float
    average_pnl_percent: float


class DashboardSchedulerSummary(BaseModel):
    enabled: bool
    interval_seconds: int
    is_running: bool
    last_run_at: datetime | None
    last_result: dict | None


class DashboardSummaryResponse(BaseModel):
    scanner: DashboardScannerSummary
    decisions: DashboardDecisionSummary
    backtesting: DashboardBacktestSummary
    scheduler: DashboardSchedulerSummary