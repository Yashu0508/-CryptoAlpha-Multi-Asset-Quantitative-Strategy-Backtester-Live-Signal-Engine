"""Simple moving average indicator."""

import pandas as pd

from app.indicators._utils import result_frame, validate_ohlcv, validate_period


def sma(ohlcv: pd.DataFrame, period: int = 20) -> pd.DataFrame:
    """Return a DataFrame containing the rolling simple moving average of close."""

    validate_ohlcv(ohlcv)
    validate_period(period)
    return result_frame(ohlcv.index, sma=ohlcv["close"].rolling(period, min_periods=period).mean())
