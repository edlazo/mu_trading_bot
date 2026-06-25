from app.schemas.alert import RiskLevel
from app.schemas.tradingview import TradingViewSignal


def get_entry_price(signal: TradingViewSignal) -> float:
    if signal.resistance is not None and signal.close < signal.resistance:
        return signal.resistance
    if signal.sma30 is not None and signal.close < signal.sma30:
        return signal.sma30
    return signal.close


def classify_risk(score: int) -> RiskLevel:
    if score >= 80:
        return RiskLevel.BAJO
    if score >= 65:
        return RiskLevel.MEDIO
    if score >= 45:
        return RiskLevel.ALTO
    return RiskLevel.EXTREMO


def classify_preliminary_risk(score: int, risk_reward: float | None) -> RiskLevel:
    risk = classify_risk(score)
    if risk_reward is None or risk_reward < 1.0:
        return RiskLevel.EXTREMO
    if risk_reward < 1.5 and risk in {RiskLevel.BAJO, RiskLevel.MEDIO}:
        return RiskLevel.ALTO
    return risk


def calculate_risk_reward(entry_price: float, target: float | None, stop_loss: float | None) -> float | None:
    if target is None or stop_loss is None:
        return None
    risk = entry_price - stop_loss
    reward = target - entry_price
    if risk <= 0 or reward <= 0:
        return None
    return reward / risk