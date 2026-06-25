from datetime import datetime

from pydantic import BaseModel, ConfigDict, Field, field_validator


class WatchlistTickerCreate(BaseModel):
    ticker: str = Field(min_length=1)
    market: str = "USA"
    notes: str | None = None

    @field_validator("ticker", "market")
    @classmethod
    def normalize_symbol_fields(cls, value: str) -> str:
        value = value.strip().upper()
        if not value:
            raise ValueError("must not be empty")
        return value


class WatchlistTickerUpdate(BaseModel):
    enabled: bool | None = None
    notes: str | None = None


class WatchlistTickerResponse(BaseModel):
    id: int
    ticker: str
    market: str
    enabled: bool
    notes: str | None
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)
