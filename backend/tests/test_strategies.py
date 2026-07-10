"""Unit tests for independent strategy contracts and signal output shape."""

import numpy as np
import pandas as pd
import pytest

from app.strategies import (
    BreakoutStrategy,
    EMACrossoverStrategy,
    MeanReversionStrategy,
    MomentumStrategy,
    RSIMACDStrategy,
    SignalAction,
    StrategySignal,
)


@pytest.fixture
def ohlcv_frame() -> pd.DataFrame:
    """Create a sufficiently long, non-flat OHLCV test series."""

    index = pd.date_range("2025-01-01", periods=100, freq="h", tz="UTC")
    close = pd.Series(np.linspace(100, 130, 100) + np.sin(np.arange(100)), index=index)
    return pd.DataFrame({"open": close - 0.5, "high": close + 1, "low": close - 1, "close": close, "volume": 1_000.0}, index=index)


@pytest.mark.parametrize(
    "strategy",
    [MomentumStrategy(), MeanReversionStrategy(), BreakoutStrategy(), EMACrossoverStrategy(), RSIMACDStrategy()],
)
def test_strategy_returns_normalized_signal(ohlcv_frame: pd.DataFrame, strategy: object) -> None:
    """Every strategy returns the common typed recommendation contract."""

    signal = strategy.generate_signal(ohlcv_frame)  # type: ignore[union-attr]

    assert isinstance(signal, StrategySignal)
    assert signal.action in {SignalAction.BUY, SignalAction.SELL, SignalAction.HOLD}
    assert 0.0 <= signal.confidence <= 1.0
    assert signal.reason


def test_momentum_emits_buy_for_strong_rally(ohlcv_frame: pd.DataFrame) -> None:
    """Momentum identifies a large positive period return."""

    signal = MomentumStrategy(period=5, threshold=0.005).generate_signal(ohlcv_frame)

    assert signal.action is SignalAction.BUY


def test_breakout_emits_buy_above_prior_resistance(ohlcv_frame: pd.DataFrame) -> None:
    """Breakout compares the latest close against only completed bars."""

    ohlcv_frame.loc[ohlcv_frame.index[-1], ["close", "high"]] = [1_000.0, 1_001.0]
    signal = BreakoutStrategy(lookback=20).generate_signal(ohlcv_frame)

    assert signal.action is SignalAction.BUY


def test_strategy_holds_when_history_is_insufficient(ohlcv_frame: pd.DataFrame) -> None:
    """Strategies do not create a trade signal from incomplete indicator history."""

    signal = EMACrossoverStrategy().generate_signal(ohlcv_frame.iloc[:10])

    assert signal.action is SignalAction.HOLD
