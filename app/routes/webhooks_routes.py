from fastapi import APIRouter, Depends
from sqlalchemy.orm import Session

from app.database.session import get_db
from app.integrations.discord import send_discord_message
from app.integrations.tradingview import validate_tradingview_secret
from app.schemas.alert import AlertResponse
from app.schemas.tradingview import TradingViewSignal
from app.services.alert_service import create_alert

router = APIRouter(prefix="/webhooks", tags=["Webhooks"])


@router.post("/test-discord", summary="Test Discord webhook")
async def test_discord_webhook() -> dict[str, str]:
    embed = {
        "title": "Mu Trading Bot - Test Discord",
        "description": "Webhook de Discord configurado correctamente.",
        "color": 0x3498DB,
    }
    await send_discord_message(content=None, embeds=[embed])
    return {"status": "discord_test_sent"}


@router.post("/tradingview", response_model=AlertResponse, summary="Receive TradingView signal")
async def tradingview_webhook(
    signal: TradingViewSignal,
    _: None = Depends(validate_tradingview_secret),
    db: Session = Depends(get_db),
) -> AlertResponse:
    _alert, score, risk = await create_alert(db, signal)
    return AlertResponse(status="alert_sent", ticker=signal.ticker, score=score, risk=risk)