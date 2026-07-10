"""Average directional index indicator."""

import numpy as np
import pandas as pd

from app.indicators._utils import result_frame, validate_ohlcv, validate_period


def adx(ohlcv: pd.DataFrame, period: int = 14) -> pd.DataFrame:
    """Return ADX plus positive and negative directional indicators."""

    validate_ohlcv(ohlcv)
    validate_period(period)
    up_move = ohlcv["high"].diff()
    down_move = -ohlcv["low"].diff()
    plus_dm = up_move.where((up_move > down_move) & (up_move > 0), 0.0)
    minus_dm = down_move.where((down_move > up_move) & (down_move > 0), 0.0)
    previous_close = ohlcv["close"].shift()
    true_range = pd.concat(
        [ohlcv["high"] - ohlcv["low"], (ohlcv["high"] - previous_close).abs(), (ohlcv["low"] - previous_close).abs()], axis=1
    ).max(axis=1)
    smooth = lambda series: series.ewm(alpha=1 / period, adjust=False, min_periods=period).mean()
    atr_value = smooth(true_range).replace(0, np.nan)
    plus_di = 100 * smooth(plus_dm) / atr_value
    minus_di = 100 * smooth(minus_dm) / atr_value
    dx = 100 * (plus_di - minus_di).abs() / (plus_di + minus_di).replace(0, np.nan)
    return result_frame(ohlcv.index, adx=smooth(dx), plus_di=plus_di, minus_di=minus_di)
