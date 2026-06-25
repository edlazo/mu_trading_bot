import numpy as np
import pandas as pd


def sma(series: pd.Series, length: int) -> pd.Series:
    return series.rolling(window=length, min_periods=length).mean()


def ema(series: pd.Series, length: int) -> pd.Series:
    return series.ewm(span=length, adjust=False, min_periods=length).mean()


def wma(series: pd.Series, length: int) -> pd.Series:
    weights = np.arange(1, length + 1)
    return series.rolling(window=length, min_periods=length).apply(
        lambda values: float(np.dot(values, weights) / weights.sum()),
        raw=True,
    )


def asl(series: pd.Series, length: int) -> pd.Series:
    return (ema(series, length - 1) + wma(series, length)) / 2


def rsi(series: pd.Series, length: int = 14) -> pd.Series:
    delta = series.diff()
    gain = delta.clip(lower=0)
    loss = -delta.clip(upper=0)
    avg_gain = gain.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    avg_loss = loss.ewm(alpha=1 / length, adjust=False, min_periods=length).mean()
    rs = avg_gain / avg_loss.replace(0, np.nan)
    result = 100 - (100 / (1 + rs))
    return result.mask((avg_loss == 0) & (avg_gain > 0), 100)


def ppo(close: pd.Series, fast: int = 12, slow: int = 26, signal: int = 9) -> tuple[pd.Series, pd.Series, pd.Series]:
    fast_ema = ema(close, fast)
    slow_ema = ema(close, slow)
    ppo_line = ((fast_ema - slow_ema) / slow_ema) * 100
    signal_line = ema(ppo_line, signal)
    hist = ppo_line - signal_line
    return ppo_line, signal_line, hist