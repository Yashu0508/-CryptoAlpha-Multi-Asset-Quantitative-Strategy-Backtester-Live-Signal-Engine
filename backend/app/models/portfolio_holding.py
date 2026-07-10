"""Current portfolio holding persistence model."""

from datetime import datetime
from decimal import Decimal
import uuid

from sqlalchemy import DateTime, ForeignKey, Index, Numeric, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin


class PortfolioHolding(TimestampMixin, Base):
    """The current position for one asset in a named portfolio."""

    __tablename__ = "portfolio_holdings"
    __table_args__ = (
        UniqueConstraint("portfolio_key", "asset_id", name="uq_portfolio_holdings_portfolio_asset"),
        Index("ix_portfolio_holdings_portfolio_key", "portfolio_key"),
    )

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    portfolio_key: Mapped[str] = mapped_column(String(128), nullable=False)
    asset_id: Mapped[uuid.UUID] = mapped_column(
        Uuid, ForeignKey("assets.id", ondelete="RESTRICT"), nullable=False
    )
    quantity: Mapped[Decimal] = mapped_column(Numeric(32, 12), nullable=False)
    average_entry_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 12))
    last_mark_price: Mapped[Decimal | None] = mapped_column(Numeric(24, 12))
    as_of: Mapped[datetime] = mapped_column(DateTime(timezone=True), nullable=False, index=True)

    asset: Mapped["Asset"] = relationship(back_populates="holdings")
