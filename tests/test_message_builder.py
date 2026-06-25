from app.core.message_builder import build_alert_message
from app.schemas.alert import OpportunitySource, RiskLevel
from app.schemas.tradingview import TradingViewSignal


def test_build_alert_message_contains_core_fields():
    signal = TradingViewSignal(
        ticker="AAPL",
        source=OpportunitySource.MIXED,
        reason="Precio recupera zona tecnica.",
        close=100,
        target=120,
        stop_loss=90,
    )

    message = build_alert_message(signal, score=72, risk=RiskLevel.MEDIO)

    assert "$AAPL" in message
    assert "MEDIO" in message
    assert "ENTRADA" in message
    assert "OBJ" in message
    assert "SL" in message
