"""Backtest run persistence model."""

from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin


class Backtest(TimestampMixin, Base):
    """A reproducible historical strategy simulation run."""

    __tablename__ = "backtests"
    __table_args__ = (Index("ix_backtests_strategy_started_at", "strategy_id", "started_at"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    strategy_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("strategies.id"), nullable=False)
    status: Mapped[str] = mapped_column(String(32), nullable=False, default="pending")
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True))
    parameters: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    metrics: Mapped[dict[str, object] | None] = mapped_column(JSONB)
    initial_capital: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    final_equity: Mapped[Decimal | None] = mapped_column(Numeric(24, 12))

    strategy: Mapped["Strategy"] = relationship(back_populates="backtests")
