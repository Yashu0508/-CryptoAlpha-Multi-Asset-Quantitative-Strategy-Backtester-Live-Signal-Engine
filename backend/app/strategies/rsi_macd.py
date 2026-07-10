"""Standalone RSI and MACD confluence strategy."""

import pandas as pd

from app.indicators.macd import macd
from app.indicators.rsi import rsi
from app.strategies.base import BaseStrategy, SignalAction, StrategySignal


class RSIMACDStrategy(BaseStrategy):
    """Trade when RSI extremes align with MACD directional confirmation."""

    name = "rsi_macd"

    def __init__(
        self,
        rsi_period: int = 14,
        oversold: float = 30.0,
        overbought: float = 70.0,
        fast_period: int = 12,
        slow_period: int = 26,
        signal_period: int = 9,
    ) -> None:
        """Configure RSI bounds and MACD periods used for confluence."""

        if (
            rsi_period <= 0
            or fast_period <= 0
            or slow_period <= 0
            or signal_period <= 0
            or fast_period >= slow_period
            or not 0 < oversold < overbought < 100
        ):
            raise ValueError("RSI bounds and MACD periods must be valid")
        self.rsi_period, self.oversold, self.overbought = rsi_period, oversold, overbought
        self.fast_period, self.slow_period, self.signal_period = fast_period, slow_period, signal_period

    def generate_signal(self, ohlcv: pd.DataFrame) -> StrategySignal:
        """Return BUY/SELL only when RSI extremes and MACD direction agree."""

        self.validate_input(ohlcv)
        rsi_value = rsi(ohlcv, self.rsi_period)["rsi"].iloc[-1]
        macd_values = macd(ohlcv, self.fast_period, self.slow_period, self.signal_period).iloc[-1]
        if pd.isna(rsi_value) or macd_values.isna().any():
            return self.hold("Insufficient bars for RSI/MACD confluence evaluation")
        momentum = abs(float(macd_values.macd_histogram)) / max(abs(float(ohlcv["close"].iloc[-1])), 1e-12)
        if rsi_value <= self.oversold and macd_values.macd > macd_values.macd_signal:
            confidence = self.bounded_confidence((self.oversold - float(rsi_value)) / self.oversold + momentum * 50)
            return StrategySignal(SignalAction.BUY, confidence, "Oversold RSI confirmed by bullish MACD")
        if rsi_value >= self.overbought and macd_values.macd < macd_values.macd_signal:
            confidence = self.bounded_confidence((float(rsi_value) - self.overbought) / (100 - self.overbought) + momentum * 50)
            return StrategySignal(SignalAction.SELL, confidence, "Overbought RSI confirmed by bearish MACD")
        return self.hold("RSI and MACD do not provide directional confluence")
