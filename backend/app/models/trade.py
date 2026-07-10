"""Executed trade persistence model."""

from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin


class Trade(TimestampMixin, Base):
    """An execution record imported from or sent to a trading venue."""

    __tablename__ = "trades"
    __table_args__ = (
        Index("ix_trades_asset_executed_at", "asset_id", "executed_at"),
        Index("ix_trades_portfolio_executed_at", "portfolio_key", "executed_at"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    asset_id: Mapped[uuid.UUID] = mapped_column(Uuid, ForeignKey("assets.id"), nullable=False)
    portfolio_key: Mapped[str] = mapped_column(String(128), nullable=False)
    side: Mapped[str] = mapped_column(String(8), nullable=False)
    quantity: Mapped[Decimal] = mapped_column(Numeric(32, 12), nullable=False)
    price: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    fee: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False, default=Decimal("0"))
    executed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)
    external_order_id: Mapped[str | None] = mapped_column(String(128), unique=True)

    asset: Mapped["Asset"] = relationship(back_populates="trades")
