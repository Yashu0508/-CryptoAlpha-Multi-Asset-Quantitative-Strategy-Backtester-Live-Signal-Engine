"""Stochastic oscillator indicator."""

import numpy as np
import pandas as pd

from app.indicators._utils import result_frame, validate_ohlcv, validate_period


def stochastic_oscillator(ohlcv: pd.DataFrame, k_period: int = 14, d_period: int = 3) -> pd.DataFrame:
    """Return stochastic %K and smoothed %D values."""

    validate_ohlcv(ohlcv)
    validate_period(k_period, "k_period")
    validate_period(d_period, "d_period")
    lowest_low = ohlcv["low"].rolling(k_period, min_periods=k_period).min()
    highest_high = ohlcv["high"].rolling(k_period, min_periods=k_period).max()
    percent_k = 100 * (ohlcv["close"] - lowest_low) / (highest_high - lowest_low).replace(0, np.nan)
    return result_frame(ohlcv.index, stochastic_k=percent_k, stochastic_d=percent_k.rolling(d_period, min_periods=d_period).mean())
