"""Moving average convergence divergence indicator."""

import pandas as pd

from app.indicators._utils import result_frame, validate_ohlcv, validate_period


def macd(ohlcv: pd.DataFrame, fast_period: int = 12, slow_period: int = 26, signal_period: int = 9) -> pd.DataFrame:
    """Return MACD line, signal line, and histogram based on closing prices."""

    validate_ohlcv(ohlcv)
    validate_period(fast_period, "fast_period")
    validate_period(slow_period, "slow_period")
    validate_period(signal_period, "signal_period")
    if fast_period >= slow_period:
        raise ValueError("fast_period must be smaller than slow_period")
    fast = ohlcv["close"].ewm(span=fast_period, adjust=False, min_periods=fast_period).mean()
    slow = ohlcv["close"].ewm(span=slow_period, adjust=False, min_periods=slow_period).mean()
    line = fast - slow
    signal = line.ewm(span=signal_period, adjust=False, min_periods=signal_period).mean()
    return result_frame(ohlcv.index, macd=line, macd_signal=signal, macd_histogram=line - signal)
