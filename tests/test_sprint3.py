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
from tests.test_webhook import EXAMPLE_SIGNAL

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


def test_usa_market_hours_confirmation_time_is_1530_new_york():
    assert USA_MARKET_HOURS.market_close_time == time(hour=16, minute=0)
    assert USA_MARKET_HOURS.pre_close_minutes == 30
    assert get_confirmation_time(USA_MARKET_HOURS) == time(hour=15, minute=30)
    assert str(USA_MARKET_HOURS.timezone) == "America/New_York"


def test_market_open_returns_true_monday_1000_new_york():
    current_datetime = datetime(2026, 6, 22, 10, 0, tzinfo=NEW_YORK)

    assert is_market_open(current_datetime) is True


def test_market_open_returns_false_monday_1700_new_york():
    current_datetime = datetime(2026, 6, 22, 17, 0, tzinfo=NEW_YORK)

    assert is_market_open(current_datetime) is False


def test_market_session_status_returns_post_market_after_close():
    current_datetime = datetime(2026, 6, 22, 17, 0, tzinfo=NEW_YORK)

    assert get_market_session_status(current_datetime) == "post_market"


def test_weekday_market_day_returns_false_for_weekend():
    saturday = datetime(2026, 6, 27, 12, 0, tzinfo=NEW_YORK)
    sunday = datetime(2026, 6, 28, 12, 0, tzinfo=NEW_YORK)

    assert is_weekday_market_day(saturday) is False
    assert is_weekday_market_day(sunday) is False


@pytest.mark.parametrize("day", [22, 23, 24, 25, 26])
def test_weekday_market_day_returns_true_for_monday_to_friday(day):
    current_datetime = datetime(2026, 6, day, 12, 0, tzinfo=NEW_YORK)

    assert is_weekday_market_day(current_datetime) is True


@pytest.mark.parametrize(
    ("hour", "minute", "second", "expected"),
    [
        (15, 29, 59, False),
        (15, 30, 0, True),
        (15, 30, 30, True),
        (15, 31, 0, False),
    ],
)
def test_confirmation_time_uses_forward_only_tolerance_window(hour, minute, second, expected):
    current_datetime = datetime(2026, 6, 23, hour, minute, second, tzinfo=NEW_YORK)

    assert is_confirmation_time(current_datetime, tolerance_seconds=60) is expected


@pytest.mark.asyncio
async def test_scheduler_calls_confirmation_runner():
    called = False

    async def fake_confirmation_runner(db):
        nonlocal called
        called = True
        assert db == "db-session"
        return []

    decisions = await run_scheduled_pre_close_confirmation("db-session", fake_confirmation_runner)

    assert called is True
    assert decisions == []


@pytest.mark.asyncio
async def test_scheduler_does_not_execute_twice_on_same_market_day():
    scheduler_service.last_confirmation_date = None
    calls = 0

    class FakeSession:
        def close(self):
            pass

    def db_session_factory():
        return FakeSession()

    async def fake_confirmation_runner(db):
        nonlocal calls
        calls += 1
        return []

    current_datetime = datetime(2026, 6, 23, 15, 30, 30, tzinfo=NEW_YORK)

    async def fake_watchlist_scanner(db):
        return []

    first_run = await run_scheduler_check(db_session_factory, current_datetime, fake_confirmation_runner, fake_watchlist_scanner)
    second_run = await run_scheduler_check(db_session_factory, current_datetime, fake_confirmation_runner, fake_watchlist_scanner)

    assert first_run is True
    assert second_run is True
    assert calls == 1

    scheduler_service.last_confirmation_date = None


def test_scheduler_is_disabled_by_default_in_settings():
    get_settings.cache_clear()
    settings = get_settings()

    assert settings.enable_scheduler is False


def test_scheduler_does_not_start_automatically_when_disabled():
    get_settings.cache_clear()
    with TestClient(app) as test_client:
        assert test_client.app.state.scheduler_enabled is False
        assert not hasattr(test_client.app.state, "scheduler_task")


def test_market_data_service_returns_valid_signal_from_alert():
    signal = get_updated_signal_for_alert(_alert_from_example())

    assert isinstance(signal, TradingViewSignal)
    assert signal.ticker == "AAPL"
    assert signal.close == EXAMPLE_SIGNAL["close"]
    assert signal.target == EXAMPLE_SIGNAL["target"]


def test_bulk_pre_close_confirmation_still_works_with_updated_data_flow(client):
    create_response = client.post(
        "/webhooks/tradingview",
        json={**EXAMPLE_SIGNAL, "target": 212.0},
        headers={"X-Webhook-Secret": "test-secret"},
    )
    assert create_response.status_code == 200

    response = client.post("/confirmations/pre-close")

    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "pre_close_confirmation_completed"
    assert len(body["decisions"]) == 1
    assert body["decisions"][0]["ticker"] == "AAPL"