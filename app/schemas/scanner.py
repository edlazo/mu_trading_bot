from pydantic import BaseModel, Field


class ScannerRequest(BaseModel):
    tickers: list[str] = Field(min_length=1)


class ScannerResponse(BaseModel):
    status: str
    session_status: str | None = None
    scanned: int
    created_alerts: int
    created_active_alerts: int | None = None
    created_watchlist: int | None = None
    created_tickers: list[str]
    skipped: list[dict]
    total_enabled: int | None = None
    limit: int | None = None
    offset: int | None = None
    next_offset: int | None = None
    has_more: bool | None = None
    created: list[dict] | None = None
    message: str | None = None
