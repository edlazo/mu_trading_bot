from datetime import UTC, datetime

from sqlalchemy import Boolean, DateTime, Float, Integer, String
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.meta import Base
from app.schemas.alert import AlertStatus


class Alert(Base):
    __tablename__ = "alerts"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, index=True)
    ticker: Mapped[str] = mapped_column(String, index=True)
    market: Mapped[str] = mapped_column(String, default="USA")
    timeframe: Mapped[str] = mapped_column(String, default="1D")
    source: Mapped[str] = mapped_column(String)
    reason: Mapped[str] = mapped_column(String)
    close: Mapped[float] = mapped_column(Float)
    sma30: Mapped[float | None] = mapped_column(Float, nullable=True)
    asl21: Mapped[float | None] = mapped_column(Float, nullable=True)
    ema150: Mapped[float | None] = mapped_column(Float, nullable=True)
    ema200: Mapped[float | None] = mapped_column(Float, nullable=True)
    rsi: Mapped[float | None] = mapped_column(Float, nullable=True)
    rsi_ma: Mapped[float | None] = mapped_column(Float, nullable=True)
    koncorde_azul: Mapped[float | None] = mapped_column(Float, nullable=True)
    koncorde_azul_prev: Mapped[float | None] = mapped_column(Float, nullable=True)
    koncorde_marron: Mapped[float | None] = mapped_column(Float, nullable=True)
    koncorde_marron_prev: Mapped[float | None] = mapped_column(Float, nullable=True)
    koncorde_media: Mapped[float | None] = mapped_column(Float, nullable=True)
    ppo: Mapped[float | None] = mapped_column(Float, nullable=True)
    ppo_signal: Mapped[float | None] = mapped_column(Float, nullable=True)
    ppo_hist: Mapped[float | None] = mapped_column(Float, nullable=True)
    ppo_hist_prev: Mapped[float | None] = mapped_column(Float, nullable=True)
    volume_ok: Mapped[bool | None] = mapped_column(Boolean, nullable=True)
    support: Mapped[float | None] = mapped_column(Float, nullable=True)
    resistance: Mapped[float | None] = mapped_column(Float, nullable=True)
    target: Mapped[float | None] = mapped_column(Float, nullable=True)
    stop_loss: Mapped[float | None] = mapped_column(Float, nullable=True)
    entry_price: Mapped[float | None] = mapped_column(Float, nullable=True)
    risk_reward: Mapped[float | None] = mapped_column(Float, nullable=True)
    preliminary_score: Mapped[int] = mapped_column(Integer)
    preliminary_risk: Mapped[str] = mapped_column(String)
    status: Mapped[str] = mapped_column(String, default=AlertStatus.EN_OBSERVACION.value)
    notes: Mapped[str | None] = mapped_column(String, nullable=True)
    weekly_context: Mapped[str | None] = mapped_column(String, nullable=True)
    monthly_context: Mapped[str | None] = mapped_column(String, nullable=True)
    fundamental_context: Mapped[str | None] = mapped_column(String, nullable=True)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=lambda: datetime.now(UTC), onupdate=lambda: datetime.now(UTC))

    decisions = relationship("Decision", back_populates="alert")
