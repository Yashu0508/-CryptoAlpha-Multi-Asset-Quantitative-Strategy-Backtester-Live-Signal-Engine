"""Relative strength index indicator."""

import numpy as np
import pandas as pd

from app.indicators._utils import result_frame, validate_ohlcv, validate_period


def rsi(ohlcv: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Return Wilder-smoothed RSI values for the close series."""

    validate_ohlcv(ohlcv)
    validate_period(period)
    delta = ohlcv["close"].diff()
    gains = delta.clip(lower=0)
    losses = -delta.clip(upper=0)
    average_gain = gains.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    average_loss = losses.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    relative_strength = average_gain / average_loss.replace(0, np.nan)
    values = 100 - (100 / (1 + relative_strength))
    values = values.where(average_loss != 0, 100.0).where(average_gain != 0, 0.0)
    return result_frame(ohlcv.index, rsi=values)
