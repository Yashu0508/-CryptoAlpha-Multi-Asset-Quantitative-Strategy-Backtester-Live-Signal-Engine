"""On-balance volume indicator."""

import numpy as np
import pandas as pd

from app.indicators._utils import result_frame, validate_ohlcv


def obv(ohlcv: pd.DataFrame) -> pd.DataFrame:
    """Return cumulative on-balance volume based on close-to-close direction."""

    validate_ohlcv(ohlcv)
    direction = np.sign(ohlcv["close"].diff()).fillna(0)
    return result_frame(ohlcv.index, obv=(direction * ohlcv["volume"]).cumsum())
