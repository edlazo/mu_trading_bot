from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "Mu Trading Bot"
    environment: str = "local"
    database_url: str = "sqlite:///./mu_trading_bot.db"
    discord_webhook_url: str | None = None
    tradingview_webhook_secret: str = "change-me"
    enable_scheduler: bool = False
    scheduler_interval_seconds: int = 300

    model_config = SettingsConfigDict(env_file=".env", env_file_encoding="utf-8")


@lru_cache
def get_settings() -> Settings:
    return Settings()