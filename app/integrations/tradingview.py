from fastapi import Header, HTTPException, Query, status

from app.config import get_settings


def validate_tradingview_secret(
    x_webhook_secret: str | None = Header(default=None),
    secret: str | None = Query(default=None),
) -> None:
    expected_secret = get_settings().tradingview_webhook_secret
    if x_webhook_secret == expected_secret or secret == expected_secret:
        return
    raise HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid webhook secret",
    )