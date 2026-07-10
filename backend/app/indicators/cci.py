"""Commodity channel index indicator."""

import numpy as np
import pandas as pd

from app.indicators._utils import result_frame, validate_ohlcv, validate_period


def cci(ohlcv: pd.DataFrame, period: int = 20, constant: float = 0.015) -> pd.DataFrame:
    """Return commodity channel index values from the typical price."""

    validate_ohlcv(ohlcv)
    validate_period(period)
    if constant <= 0:
        raise ValueError("constant must be greater than zero")
    typical_price = (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3
    average = typical_price.rolling(period, min_periods=period).mean()
    deviation = typical_price.rolling(period, min_periods=period).apply(lambda window: np.abs(window - window.mean()).mean(), raw=True)
    return result_frame(ohlcv.index, cci=(typical_price - average) / (constant * deviation.replace(0, np.nan)))
