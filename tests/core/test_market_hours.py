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
    is_pre_close_window,
    is_weekday_market_day,
)
from app.main import app
from app.models.alert import Alert
from app.schemas.tradingview import TradingViewSignal
from app.services.market_data_service import get_updated_signal_for_alert
from app.services.scheduler_service import run_scheduled_pre_close_confirmation, run_scheduler_check
from tests.routes.test_webhook_routes import EXAMPLE_SIGNAL

NEW_YORK = ZoneInfo("America/New_York")


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




@pytest.mark.parametrize(
    ("hour", "minute", "expected"),
    [
        (15, 24, False),
        (15, 25, True),
        (15, 40, True),
        (15, 55, True),
        (15, 56, False),
    ],
)
def test_pre_close_window_uses_wide_new_york_window(hour, minute, expected):
    current_datetime = datetime(2026, 6, 23, hour, minute, tzinfo=NEW_YORK)

    assert is_pre_close_window(current_datetime) is expected


def test_pre_close_window_converts_from_utc_to_new_york():
    current_datetime = datetime(2026, 6, 23, 19, 40, tzinfo=ZoneInfo("UTC"))

    assert is_pre_close_window(current_datetime) is True
