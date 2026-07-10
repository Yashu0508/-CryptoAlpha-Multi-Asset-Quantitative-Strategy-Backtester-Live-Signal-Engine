"""Shared validation and numerical helpers for DataFrame-based indicators."""

from collections.abc import Iterable

import pandas as pd

REQUIRED_OHLCV_COLUMNS = frozenset({"open", "high", "low", "close", "volume"})


def validate_ohlcv(frame: pd.DataFrame, required: Iterable[str] = ()) -> None:
    """Validate a non-empty OHLCV frame and the columns needed by an indicator."""

    if not isinstance(frame, pd.DataFrame):
        raise TypeError("OHLCV data must be provided as a pandas DataFrame")
    needed = REQUIRED_OHLCV_COLUMNS.union(required)
    missing = needed.difference(frame.columns)
    if missing:
        raise ValueError(f"OHLCV data is missing required columns: {', '.join(sorted(missing))}")
    if frame.empty:
        raise ValueError("OHLCV data must not be empty")


def validate_period(period: int, name: str = "period") -> None:
    """Validate a positive indicator lookback period."""

    if period <= 0:
        raise ValueError(f"{name} must be greater than zero")


def result_frame(index: pd.Index, **columns: pd.Series) -> pd.DataFrame:
    """Build an indicator-only DataFrame preserving the source index."""

    return pd.DataFrame(columns, index=index)
