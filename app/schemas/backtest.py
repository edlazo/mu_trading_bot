from datetime import datetime
from enum import StrEnum

from pydantic import BaseModel, ConfigDict


class BacktestOutcome(StrEnum):
    TARGET_HIT = "TARGET_HIT"
    STOP_HIT = "STOP_HIT"
    NO_RESULT = "NO_RESULT"
    ERROR = "ERROR"


class BacktestResultResponse(BaseModel):
    id: int
    decision_id: int
    alert_id: int
    ticker: str
    entry_price: float | None
    target: float | None
    stop_loss: float | None
    risk_reward: float | None
    result: BacktestOutcome
    days_checked: int
    exit_price: float | None
    exit_date: datetime | None
    pnl_percent: float | None
    reason: str
    created_at: datetime

    model_config = ConfigDict(from_attributes=True)


class BacktestRunResponse(BaseModel):
    status: str
    requested: int
    created: int
    skipped: int
    results: list[BacktestResultResponse]
