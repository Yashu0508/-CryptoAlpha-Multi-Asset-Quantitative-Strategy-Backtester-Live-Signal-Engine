"""TimescaleDB-compatible market candle persistence model."""

from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin


class OHLCV(TimestampMixin, Base):
    """A normalized OHLCV candle, keyed by asset, timestamp, and interval."""

    __tablename__ = "ohlcv"
    __table_args__ = (
        Index("ix_ohlcv_asset_interval_timestamp", "asset_id", "interval", "timestamp"),
    )

    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("assets.id", ondelete="CASCADE"), primary_key=True
    )
    timestamp: Mapped[datetime] = mapped_column(DateTime(timezone=True), primary_key=True)
    interval: Mapped[str] = mapped_column(String(12), primary_key=True)
    open: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    high: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    low: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    close: Mapped[Decimal] = mapped_column(Numeric(24, 12), nullable=False)
    volume: Mapped[Decimal] = mapped_column(Numeric(32, 12), nullable=False)

    asset: Mapped["Asset"] = relationship(back_populates="ohlcv_records")
