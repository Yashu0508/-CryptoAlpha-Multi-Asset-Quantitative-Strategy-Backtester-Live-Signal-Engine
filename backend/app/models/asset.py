"""Tradable asset persistence model."""

import uuid

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin


class Asset(TimestampMixin, Base):
    """An exchange-listed trading pair or instrument."""

    __tablename__ = "assets"
    __table_args__ = (UniqueConstraint("exchange", "symbol", name="uq_assets_exchange_symbol"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    exchange: Mapped[str] = mapped_column(String(64), nullable=False)
    symbol: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    base_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    quote_currency: Mapped[str] = mapped_column(String(16), nullable=False)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    ohlcv_records: Mapped[list["OHLCV"]] = relationship(back_populates="asset")
    trades: Mapped[list["Trade"]] = relationship(back_populates="asset")
    holdings: Mapped[list["PortfolioHolding"]] = relationship(back_populates="asset")
