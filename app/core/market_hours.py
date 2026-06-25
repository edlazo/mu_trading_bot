from dataclasses import dataclass
from datetime import datetime, time, timedelta
from zoneinfo import ZoneInfo

USA_MARKET_TIMEZONE = ZoneInfo("America/New_York")


@dataclass(frozen=True)
class MarketHoursConfig:
    market: str
    timezone: ZoneInfo
    market_open_time: time
    market_close_time: time
    pre_close_minutes: int

    @property
    def confirmation_time(self) -> time:
        close_dt = datetime.combine(datetime.today(), self.market_close_time, tzinfo=self.timezone)
        return (close_dt - timedelta(minutes=self.pre_close_minutes)).time()


USA_MARKET_HOURS = MarketHoursConfig(
    market="USA",
    timezone=USA_MARKET_TIMEZONE,
    market_open_time=time(hour=9, minute=30),
    market_close_time=time(hour=16, minute=0),
    pre_close_minutes=30,
)


def get_confirmation_time(config: MarketHoursConfig = USA_MARKET_HOURS) -> time:
    return config.confirmation_time


def is_weekday_market_day(current_datetime: datetime) -> bool:
    # TODO: include official USA market holidays and half-days.
    return current_datetime.weekday() < 5


def is_confirmation_time(
    current_datetime: datetime,
    config: MarketHoursConfig = USA_MARKET_HOURS,
    tolerance_seconds: int = 60,
) -> bool:
    current_market_datetime = current_datetime.astimezone(config.timezone)
    confirmation_datetime = datetime.combine(
        current_market_datetime.date(),
        config.confirmation_time,
        tzinfo=config.timezone,
    )
    delta_seconds = (current_market_datetime - confirmation_datetime).total_seconds()
    return 0 <= delta_seconds < tolerance_seconds


def is_market_open(
    current_datetime: datetime,
    config: MarketHoursConfig = USA_MARKET_HOURS,
) -> bool:
    current_market_datetime = current_datetime.astimezone(config.timezone)
    if not is_weekday_market_day(current_market_datetime):
        return False
    current_time = current_market_datetime.time()
    return config.market_open_time <= current_time < config.market_close_time


def get_market_session_status(
    current_datetime: datetime,
    config: MarketHoursConfig = USA_MARKET_HOURS,
) -> str:
    current_market_datetime = current_datetime.astimezone(config.timezone)
    if not is_weekday_market_day(current_market_datetime):
        return "weekend"

    current_time = current_market_datetime.time()
    if current_time < config.market_open_time:
        return "pre_market"
    if config.market_open_time <= current_time < config.market_close_time:
        return "open"
    if current_time >= config.market_close_time:
        return "post_market"
    return "closed"
