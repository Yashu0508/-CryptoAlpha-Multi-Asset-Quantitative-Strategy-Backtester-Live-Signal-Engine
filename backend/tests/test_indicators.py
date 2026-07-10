"""Unit tests for the DataFrame-based technical indicator engine."""

import numpy as np
import pandas as pd
import pytest

from app.indicators import (
    adx,
    atr,
    bollinger_bands,
    cci,
    ema,
    ichimoku_cloud,
    macd,
    obv,
    rsi,
    sma,
    stochastic_oscillator,
    vwap,
)


@pytest.fixture
def ohlcv_frame() -> pd.DataFrame:
    """Provide enough varied bars to warm up every default indicator."""

    index = pd.date_range("2025-01-01", periods=120, freq="h", tz="UTC")
    close = pd.Series(np.linspace(100, 160, 120) + np.sin(np.arange(120)), index=index)
    return pd.DataFrame(
        {
            "open": close - 0.4,
            "high": close + 1.5,
            "low": close - 1.5,
            "close": close,
            "volume": np.arange(1, 121, dtype=float) * 100,
        },
        index=index,
    )


@pytest.mark.parametrize(
    ("indicator", "columns"),
    [
        (sma, {"sma"}),
        (ema, {"ema"}),
        (rsi, {"rsi"}),
        (macd, {"macd", "macd_signal", "macd_histogram"}),
        (atr, {"atr"}),
        (vwap, {"vwap"}),
        (bollinger_bands, {"bb_middle", "bb_upper", "bb_lower"}),
        (adx, {"adx", "plus_di", "minus_di"}),
        (obv, {"obv"}),
        (cci, {"cci"}),
        (stochastic_oscillator, {"stochastic_k", "stochastic_d"}),
        (ichimoku_cloud, {"ichimoku_conversion", "ichimoku_base", "ichimoku_span_a", "ichimoku_span_b", "ichimoku_lagging"}),
    ],
)
def test_indicator_returns_indexed_dataframe(ohlcv_frame: pd.DataFrame, indicator: object, columns: set[str]) -> None:
    """Every public indicator returns an indicator-only frame aligned to input data."""

    result = indicator(ohlcv_frame)  # type: ignore[operator]

    assert isinstance(result, pd.DataFrame)
    assert result.index.equals(ohlcv_frame.index)
    assert set(result.columns) == columns
    assert result.notna().any().all()


def test_sma_matches_expected_rolling_average(ohlcv_frame: pd.DataFrame) -> None:
    """SMA follows pandas' simple rolling-mean definition."""

    result = sma(ohlcv_frame, period=3)

    assert result["sma"].iloc[2] == pytest.approx(ohlcv_frame["close"].iloc[:3].mean())


def test_obv_tracks_price_direction(ohlcv_frame: pd.DataFrame) -> None:
    """OBV accumulates volume when the closing price increases."""

    result = obv(ohlcv_frame)

    assert result["obv"].iloc[0] == 0
    assert result["obv"].iloc[1] == ohlcv_frame["volume"].iloc[1]


def test_indicator_rejects_missing_ohlcv_columns(ohlcv_frame: pd.DataFrame) -> None:
    """All indicators enforce the shared OHLCV input contract."""

    with pytest.raises(ValueError, match="missing required columns"):
        rsi(ohlcv_frame.drop(columns="volume"))


def test_indicator_rejects_invalid_period(ohlcv_frame: pd.DataFrame) -> None:
    """Indicators reject invalid lookback values before calculating."""

    with pytest.raises(ValueError, match="period"):
        ema(ohlcv_frame, period=0)
