from pydantic import BaseModel


class SP500TickerListResponse(BaseModel):
    source: str
    count: int
    tickers: list[str]


class SP500ImportResponse(BaseModel):
    source: str
    fetched: int
    created: int
    updated: int
    skipped: int
    enabled: bool


class SP500SyncResponse(BaseModel):
    source: str
    fetched: int
    created: int
    updated: int
    disabled_removed: int
    enabled: bool