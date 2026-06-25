from datetime import UTC, datetime, time
from zoneinfo import ZoneInfo

import pytest
from fastapi.testclient import TestClient

import app.services.scheduler_service as scheduler_service
from app.config import get_settings
from app.core.market_hours import (
    USA_MARKET_HOURS,
    get_confirmation_time,
    get_market_session_status,
    is_confirmation_time,
    is_market_open,
    is_weekday_market_day,
)
from app.main import app
from app.models.alert import Alert
from app.schemas.tradingview import TradingViewSignal
from app.services.market_data_service import get_updated_signal_for_alert
from app.services.scheduler_service import run_scheduled_pre_close_confirmation, run_scheduler_check
from tests.routes.test_webhook_routes import EXAMPLE_SIGNAL

NEW_YORK = ZoneInfo("America/New_York")


def _alert_from_example() -> Alert:
    return Alert(
        ticker=EXAMPLE_SIGNAL["ticker"],
        market=EXAMPLE_SIGNAL["market"],
        timeframe=EXAMPLE_SIGNAL["timeframe"],
        source=EXAMPLE_SIGNAL["source"],
        reason=EXAMPLE_SIGNAL["reason"],
        close=EXAMPLE_SIGNAL["close"],
        sma30=EXAMPLE_SIGNAL["sma30"],
        asl21=EXAMPLE_SIGNAL["asl21"],
        ema150=EXAMPLE_SIGNAL["ema150"],
        ema200=EXAMPLE_SIGNAL["ema200"],
        rsi=EXAMPLE_SIGNAL["rsi"],
        rsi_ma=EXAMPLE_SIGNAL["rsi_ma"],
        koncorde_azul=EXAMPLE_SIGNAL["koncorde_azul"],
        koncorde_azul_prev=EXAMPLE_SIGNAL["koncorde_azul_prev"],
        koncorde_marron=EXAMPLE_SIGNAL["koncorde_marron"],
        koncorde_marron_prev=EXAMPLE_SIGNAL["koncorde_marron_prev"],
        koncorde_media=EXAMPLE_SIGNAL["koncorde_media"],
        ppo=EXAMPLE_SIGNAL["ppo"],
        ppo_signal=EXAMPLE_SIGNAL["ppo_signal"],
        ppo_hist=EXAMPLE_SIGNAL["ppo_hist"],
        ppo_hist_prev=EXAMPLE_SIGNAL["ppo_hist_prev"],
        volume_ok=EXAMPLE_SIGNAL["volume_ok"],
        support=EXAMPLE_SIGNAL["support"],
        resistance=EXAMPLE_SIGNAL["resistance"],
        target=EXAMPLE_SIGNAL["target"],
        stop_loss=EXAMPLE_SIGNAL["stop_loss"],
        weekly_context=EXAMPLE_SIGNAL["weekly_context"],
        monthly_context=EXAMPLE_SIGNAL["monthly_context"],
        fundamental_context=EXAMPLE_SIGNAL["fundamental_context"],
        notes=EXAMPLE_SIGNAL["notes"],
        preliminary_score=80,
        preliminary_risk="BAJO 🟢",
        status="EN_OBSERVACION",
    )



def test_market_data_service_returns_valid_signal_from_alert():
    signal = get_updated_signal_for_alert(_alert_from_example())

    assert isinstance(signal, TradingViewSignal)
    assert signal.ticker == "AAPL"
    assert signal.close == EXAMPLE_SIGNAL["close"]
    assert signal.target == EXAMPLE_SIGNAL["target"]


