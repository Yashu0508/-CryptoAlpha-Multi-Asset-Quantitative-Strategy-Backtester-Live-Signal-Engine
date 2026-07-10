"""Standalone exponential moving-average crossover strategy."""

import pandas as pd

from app.indicators.ema import ema
from app.strategies.base import BaseStrategy, SignalAction, StrategySignal


class EMACrossoverStrategy(BaseStrategy):
    """Trade fresh crossings between fast and slow exponential moving averages."""

    name = "ema_crossover"

    def __init__(self, fast_period: int = 12, slow_period: int = 26) -> None:
        """Configure fast and slow EMA periods."""

        if fast_period <= 0 or slow_period <= 0 or fast_period >= slow_period:
            raise ValueError("EMA periods must be positive and fast_period smaller than slow_period")
        self.fast_period = fast_period
        self.slow_period = slow_period

    def generate_signal(self, ohlcv: pd.DataFrame) -> StrategySignal:
        """Return BUY or SELL only when the latest bar creates an EMA crossover."""

        self.validate_input(ohlcv)
        fast = ema(ohlcv, self.fast_period)["ema"]
        slow = ema(ohlcv, self.slow_period)["ema"]
        if len(ohlcv) < 2 or pd.isna(fast.iloc[-1]) or pd.isna(slow.iloc[-1]) or pd.isna(fast.iloc[-2]) or pd.isna(slow.iloc[-2]):
            return self.hold("Insufficient bars for EMA crossover evaluation")
        spread = abs(float(fast.iloc[-1] - slow.iloc[-1])) / max(abs(float(slow.iloc[-1])), 1e-12)
        confidence = self.bounded_confidence(spread * 20)
        if fast.iloc[-2] <= slow.iloc[-2] and fast.iloc[-1] > slow.iloc[-1]:
            return StrategySignal(SignalAction.BUY, confidence, "Fast EMA crossed above slow EMA")
        if fast.iloc[-2] >= slow.iloc[-2] and fast.iloc[-1] < slow.iloc[-1]:
            return StrategySignal(SignalAction.SELL, confidence, "Fast EMA crossed below slow EMA")
        return self.hold("No fresh EMA crossover")
