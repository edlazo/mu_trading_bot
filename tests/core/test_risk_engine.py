import pytest

from app.core.opportunity_engine import calculate_preliminary_score
from app.core.risk_engine import calculate_risk_reward, classify_preliminary_risk, classify_risk, get_entry_price
from app.schemas.alert import OpportunitySource, RiskLevel
from app.schemas.tradingview import TradingViewSignal


def signal(**overrides) -> TradingViewSignal:
    data = {
        "ticker": "AAPL",
        "source": OpportunitySource.MIXED,
        "reason": "test",
        "close": 100,
        "target": 120,
        "stop_loss": 90,
    }
    data.update(overrides)
    return TradingViewSignal(**data)


def test_healthy_rsi_adds_score():
    assert calculate_preliminary_score(signal(rsi=61)) > calculate_preliminary_score(signal())


def test_overbought_rsi_penalizes_score():
    assert calculate_preliminary_score(signal(rsi=76)) < calculate_preliminary_score(signal())


def test_buyer_ppo_adds_score():
    scored = calculate_preliminary_score(signal(ppo=1.2, ppo_signal=1.0, ppo_hist=0.2, ppo_hist_prev=0.1))
    base = calculate_preliminary_score(signal())
    assert scored - base == 17


def test_buyer_koncorde_adds_score():
    scored = calculate_preliminary_score(signal(koncorde_azul=1, koncorde_marron=2, koncorde_media=1))
    base = calculate_preliminary_score(signal())
    assert scored - base == 15


def test_risk_reward_above_two_adds_score():
    scored = calculate_preliminary_score(signal(target=130, stop_loss=90))
    missing_rr = calculate_preliminary_score(signal(target=None, stop_loss=None))
    assert scored > missing_rr


def test_risk_reward_below_one_point_five_penalizes_score():
    scored = calculate_preliminary_score(signal(target=105, stop_loss=90))
    base = calculate_preliminary_score(signal(target=120, stop_loss=90))
    assert scored < base


def test_risk_classification_bajo():
    assert classify_risk(80) == RiskLevel.BAJO


def test_risk_classification_medio():
    assert classify_risk(65) == RiskLevel.MEDIO


def test_risk_classification_alto():
    assert classify_risk(45) == RiskLevel.ALTO


def test_risk_classification_extremo():
    assert classify_risk(44) == RiskLevel.EXTREMO


def test_entry_price_uses_resistance_when_available():
    assert get_entry_price(signal(resistance=198.5, sma30=190)) == 198.5


def test_entry_price_uses_sma30_when_resistance_missing():
    assert get_entry_price(signal(resistance=None, sma30=190)) == 190


def test_risk_reward_is_calculated_from_entry_price():
    risk_reward = calculate_risk_reward(entry_price=198.5, target=205, stop_loss=188.4)

    assert risk_reward == pytest.approx(0.64, abs=0.01)


def test_preliminary_risk_cannot_be_low_or_medium_when_risk_reward_is_below_one_point_five():
    risk = classify_preliminary_risk(score=95, risk_reward=1.44)

    assert risk == RiskLevel.ALTO


def test_preliminary_risk_is_extreme_when_risk_reward_is_invalid():
    risk = classify_preliminary_risk(score=95, risk_reward=None)

    assert risk == RiskLevel.EXTREMO