"""Exponential moving average indicator."""

import pandas as pd

from app.indicators._utils import result_frame, validate_ohlcv, validate_period


def ema(ohlcv: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Return a DataFrame containing the exponential moving average of close."""

    validate_ohlcv(ohlcv)
    validate_period(period)
    return result_frame(ohlcv.index, ema=ohlcv["close"].ewm(span=period, adjust=False, min_periods=period).mean())
