from app.core.risk_engine import calculate_risk_reward, get_entry_price
from app.schemas.alert import OpportunitySource
from app.schemas.tradingview import TradingViewSignal


SOURCE_POINTS = {
    OpportunitySource.CHART: 6,
    OpportunitySource.INDICATORS: 6,
    OpportunitySource.FUNDAMENTALS: 6,
    OpportunitySource.MIXED: 18,
}


def calculate_preliminary_score(signal: TradingViewSignal) -> int:
    score = SOURCE_POINTS.get(signal.source, 0)

    if signal.sma30 is not None and signal.close > signal.sma30:
        score += 10
    if signal.asl21 is not None and signal.close > signal.asl21:
        score += 7
    if signal.ema150 is not None and signal.ema200 is not None:
        ema_avg = (signal.ema150 + signal.ema200) / 2
        if signal.close > ema_avg:
            score += 8

    if signal.rsi is not None:
        if 50 <= signal.rsi <= 68:
            score += 15
        elif 68 < signal.rsi <= 72:
            score += 8
        elif signal.rsi > 75:
            score -= 15
        elif signal.rsi < 45:
            score -= 10

    if signal.koncorde_azul is not None and signal.koncorde_azul > 0:
        score += 8
    if (
        signal.koncorde_marron is not None
        and signal.koncorde_media is not None
        and signal.koncorde_marron > signal.koncorde_media
    ):
        score += 7

    if signal.ppo is not None and signal.ppo_signal is not None and signal.ppo > signal.ppo_signal:
        score += 7
    if signal.ppo_hist is not None and signal.ppo_hist > 0:
        score += 5
    if (
        signal.ppo_hist is not None
        and signal.ppo_hist_prev is not None
        and signal.ppo_hist > signal.ppo_hist_prev
    ):
        score += 5

    if signal.volume_ok is True:
        score += 5
    elif signal.volume_ok is False:
        score -= 5

    entry_price = get_entry_price(signal)
    risk_reward = calculate_risk_reward(entry_price, signal.target, signal.stop_loss)
    if risk_reward is None:
        score -= 10
    elif risk_reward >= 2:
        score += 15
    elif risk_reward >= 1.5:
        score += 8
    else:
        score -= 15

    if signal.stop_loss is not None and signal.stop_loss >= entry_price:
        score -= 20

    return max(0, min(100, score))