from pydantic import BaseModel, ConfigDict, Field

from app.schemas.alert import OpportunitySource


class TradingViewSignal(BaseModel):
    ticker: str = Field(min_length=1)
    market: str = "USA"
    timeframe: str = "1D"
    source: OpportunitySource
    reason: str
    close: float = Field(gt=0)
    sma30: float | None = None
    asl21: float | None = None
    ema150: float | None = None
    ema200: float | None = None
    rsi: float | None = None
    rsi_ma: float | None = None
    koncorde_azul: float | None = None
    koncorde_azul_prev: float | None = None
    koncorde_marron: float | None = None
    koncorde_marron_prev: float | None = None
    koncorde_media: float | None = None
    ppo: float | None = None
    ppo_signal: float | None = None
    ppo_hist: float | None = None
    ppo_hist_prev: float | None = None
    volume_ok: bool | None = None
    support: float | None = None
    resistance: float | None = None
    target: float | None = None
    stop_loss: float | None = None
    weekly_context: str | None = None
    monthly_context: str | None = None
    fundamental_context: str | None = None
    notes: str | None = None

    model_config = ConfigDict(str_strip_whitespace=True)