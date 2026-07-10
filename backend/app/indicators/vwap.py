"""Volume-weighted average price indicator."""

import numpy as np
import pandas as pd

from app.indicators._utils import result_frame, validate_ohlcv


def vwap(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Return cumulative VWAP values calculated from the typical price and volume."""

    validate_ohlcv(ohlcv)
    typical_price = (ohlcv["high"] + ohlcv["low"] + ohlcv["close"]) / 3
    cumulative_volume = ohlcv["volume"].cumsum().replace(0, np.nan)
    return result_frame(ohlcv.index, vwap=(typical_price * ohlcv["volume"]).cumsum() / cumulative_volume)
