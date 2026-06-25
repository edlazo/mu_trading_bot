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
    created: list[dict] | None = None
    message: str | None = None
