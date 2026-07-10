"""Standalone rolling price-channel breakout strategy."""

import pandas as pd

from app.strategies.base import BaseStrategy, SignalAction, StrategySignal


class BreakoutStrategy(BaseStrategy):
    """Trade closes that break above prior resistance or below prior support."""

    name = "breakout"

    def __init__(self, lookback: int = 20) -> None:
        """Configure the number of completed bars defining the price channel."""

        if lookback <= 0:
            raise ValueError("lookback must be greater than zero")
        self.lookback = lookback

    def generate_signal(self, ohlcv: pd.DataFrame) -> StrategySignal:
        """Return a breakout recommendation against the prior completed channel."""

        self.validate_input(ohlcv)
        if len(ohlcv) <= self.lookback:
            return self.hold("Insufficient bars for breakout evaluation")
        history = ohlcv.iloc[-self.lookback - 1 : -1]
        resistance, support, close = float(history["high"].max()), float(history["low"].min()), float(ohlcv["close"].iloc[-1])
        channel_width = max(resistance - support, 1e-12)
        if close > resistance:
            return StrategySignal(SignalAction.BUY, self.bounded_confidence((close - resistance) / channel_width), "Close broke above prior channel resistance")
        if close < support:
            return StrategySignal(SignalAction.SELL, self.bounded_confidence((support - close) / channel_width), "Close broke below prior channel support")
        return self.hold("Close remains inside the prior price channel")
