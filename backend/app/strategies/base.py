"""Common contract and value objects for independently executable strategies."""

from abc import ABC, abstractmethod
from dataclasses import dataclass
from enum import StrEnum

import pandas as pd

from app.indicators._utils import validate_ohlcv


class SignalAction(StrEnum):
    """Actions that a strategy may recommend."""

    BUY = "BUY"
    SELL = "SELL"
    HOLD = "HOLD"


@dataclass(frozen=True, slots=True)
class StrategySignal:
    """Provider-neutral recommendation emitted by a strategy evaluation."""

    action: SignalAction
    confidence: float
    reason: str

    def __post_init__(self) -> None:
        """Keep confidence scores on the closed interval from zero to one."""

        if not 0.0 <= self.confidence <= 1.0:
            raise ValueError("confidence must be between 0.0 and 1.0")


class BaseStrategy(ABC):
    """Base interface for stateless strategies evaluated from OHLCV DataFrames."""

    name: str

    @abstractmethod
    def generate_signal(self, ohlcv: pd.DataFrame) -> StrategySignal:
        """Evaluate the latest OHLCV bar and return one normalized recommendation."""

    @staticmethod
    def validate_input(ohlcv: pd.DataFrame) -> None:
        """Validate the shared OHLCV input contract before strategy calculations."""

        validate_ohlcv(ohlcv)

    @staticmethod
    def hold(reason: str) -> StrategySignal:
        """Return a conventional no-action recommendation."""

        return StrategySignal(action=SignalAction.HOLD, confidence=0.0, reason=reason)

    @staticmethod
    def bounded_confidence(value: float) -> float:
        """Clamp a derived signal-strength score to the public confidence range."""

        return max(0.0, min(float(value), 1.0))
