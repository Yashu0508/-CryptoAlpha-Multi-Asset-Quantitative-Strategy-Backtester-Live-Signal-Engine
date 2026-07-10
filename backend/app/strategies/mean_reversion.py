"""Standalone Bollinger Band mean-reversion strategy."""

import pandas as pd

from app.indicators.bollinger_bands import bollinger_bands
from app.strategies.base import BaseStrategy, SignalAction, StrategySignal


class MeanReversionStrategy(BaseStrategy):
    """Trade closes outside Bollinger Bands back toward their rolling mean."""

    name = "mean_reversion"

    def __init__(self, period: int = 20, standard_deviations: float = 2.0) -> None:
        """Configure the Bollinger Band lookback and width."""

        if period <= 0 or standard_deviations <= 0:
            raise ValueError("period and standard_deviations must be greater than zero")
        self.period = period
        self.standard_deviations = standard_deviations

    def generate_signal(self, ohlcv: pd.DataFrame) -> StrategySignal:
        """Return a reversion recommendation when close breaches a band."""

        self.validate_input(ohlcv)
        bands = bollinger_bands(ohlcv, self.period, self.standard_deviations).iloc[-1]
        if bands.isna().any():
            return self.hold("Insufficient bars for Bollinger Band evaluation")
        close = float(ohlcv["close"].iloc[-1])
        width = float(bands.bb_upper - bands.bb_lower)
        if close < bands.bb_lower:
            return StrategySignal(SignalAction.BUY, self.bounded_confidence((float(bands.bb_lower) - close) / width), "Close is below the lower Bollinger Band")
        if close > bands.bb_upper:
            return StrategySignal(SignalAction.SELL, self.bounded_confidence((close - float(bands.bb_upper)) / width), "Close is above the upper Bollinger Band")
        return self.hold("Close remains within Bollinger Bands")
