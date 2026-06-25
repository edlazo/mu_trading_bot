import numpy as np
import pandas as pd
import pytest

from app.core.indicators import ema, ppo, rsi, sma


def test_sma_works():
    series = pd.Series([1, 2, 3, 4, 5], dtype=float)

    result = sma(series, 3)

    assert np.isnan(result.iloc[1])
    assert result.iloc[-1] == pytest.approx(4.0)


def test_ema_works():
    series = pd.Series([1, 2, 3, 4, 5], dtype=float)

    result = ema(series, 3)

    assert result.notna().any()
    assert result.iloc[-1] > result.iloc[-2]


def test_rsi_returns_reasonable_values():
    series = pd.Series(range(1, 40), dtype=float)

    result = rsi(series, 14).dropna()

    assert not result.empty
    assert result.iloc[-1] > 0
    assert result.iloc[-1] <= 100


def test_ppo_returns_line_signal_and_hist():
    series = pd.Series(range(1, 80), dtype=float)

    ppo_line, signal_line, hist = ppo(series)

    assert len(ppo_line) == len(series)
    assert len(signal_line) == len(series)
    assert len(hist) == len(series)
    assert hist.dropna().notna().any()