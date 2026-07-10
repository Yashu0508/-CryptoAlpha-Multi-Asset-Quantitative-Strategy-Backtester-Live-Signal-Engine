"""Average true range indicator."""

import pandas as pd

from app.indicators._utils import result_frame, validate_ohlcv, validate_period


def atr(ohlcv: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Return Wilder-smoothed average true range values."""

    validate_ohlcv(ohlcv)
    validate_period(period)
    previous_close = ohlcv["close"].shift(1)
    true_range = pd.concat(
        [ohlcv["high"] - ohlcv["low"], (ohlcv["high"] - previous_close).abs(), (ohlcv["low"] - previous_close).abs()],
        axis=1,
    ).max(axis=1)
    return result_frame(ohlcv.index, atr=true_range.ewm(alpha=1 / period, adjust=False, min_periods=period).mean())
