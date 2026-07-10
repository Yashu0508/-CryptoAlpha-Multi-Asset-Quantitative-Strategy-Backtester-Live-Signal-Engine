"""Standalone close-price momentum strategy."""

import pandas as pd

from app.strategies.base import BaseStrategy, SignalAction, StrategySignal


class MomentumStrategy(BaseStrategy):
    """Trade sustained close-price returns beyond a configurable percentage threshold."""

    name = "momentum"

    def __init__(self, period: int = 14, threshold: float = 0.03) -> None:
        """Configure the momentum observation period and directional threshold."""

        if period <= 0 or threshold <= 0:
            raise ValueError("period and threshold must be greater than zero")
        self.period = period
        self.threshold = threshold

    def generate_signal(self, ohlcv: pd.DataFrame) -> StrategySignal:
        """Recommend BUY or SELL when period return clears the configured threshold."""

        self.validate_input(ohlcv)
        if len(ohlcv) <= self.period:
            return self.hold("Insufficient bars for momentum evaluation")
        momentum = float(ohlcv["close"].iloc[-1] / ohlcv["close"].iloc[-self.period - 1] - 1)
        confidence = self.bounded_confidence(abs(momentum) / (self.threshold * 3))
        if momentum >= self.threshold:
            return StrategySignal(SignalAction.BUY, confidence, f"{self.period}-bar momentum is {momentum:.2%}")
        if momentum <= -self.threshold:
            return StrategySignal(SignalAction.SELL, confidence, f"{self.period}-bar momentum is {momentum:.2%}")
        return self.hold(f"{self.period}-bar momentum {momentum:.2%} is within threshold")
