"""Ichimoku Cloud indicator."""

import pandas as pd

from app.indicators._utils import result_frame, validate_ohlcv, validate_period


def ichimoku_cloud(
    ohlcv: pd.DataFrame,
    conversion_period: int = 9,
    base_period: int = 26,
    span_b_period: int = 52,
    displacement: int = 26,
) -> pd.DataFrame:
    """Return conversion, base, leading spans, and lagging span for Ichimoku Cloud."""

    validate_ohlcv(ohlcv)
    for name, value in {
        "conversion_period": conversion_period,
        "base_period": base_period,
        "span_b_period": span_b_period,
        "displacement": displacement,
    }.items():
        validate_period(value, name)

    def midpoint(period: int) -> pd.Series:
        return (ohlcv["high"].rolling(period, min_periods=period).max() + ohlcv["low"].rolling(period, min_periods=period).min()) / 2

    conversion = midpoint(conversion_period)
    base = midpoint(base_period)
    span_a = ((conversion + base) / 2).shift(displacement)
    span_b = midpoint(span_b_period).shift(displacement)
    return result_frame(
        ohlcv.index,
        ichimoku_conversion=conversion,
        ichimoku_base=base,
        ichimoku_span_a=span_a,
        ichimoku_span_b=span_b,
        ichimoku_lagging=ohlcv["close"].shift(-displacement),
    )
