"""Bollinger Bands indicator."""

import pandas as pd

from app.indicators._utils import result_frame, validate_ohlcv, validate_period


def bollinger_bands(ohlcv: pd.DataFrame, period: int = 20, standard_deviations: float = 2.0) -> pd.DataFrame:
    """Return middle, upper, and lower Bollinger Bands for closing prices."""

    validate_ohlcv(ohlcv)
    validate_period(period)
    if standard_deviations <= 0:
        raise ValueError("standard_deviations must be greater than zero")
    middle = ohlcv["close"].rolling(period, min_periods=period).mean()
    deviation = ohlcv["close"].rolling(period, min_periods=period).std(ddof=0)
    return result_frame(ohlcv.index, bb_middle=middle, bb_upper=middle + standard_deviations * deviation, bb_lower=middle - standard_deviations * deviation)
