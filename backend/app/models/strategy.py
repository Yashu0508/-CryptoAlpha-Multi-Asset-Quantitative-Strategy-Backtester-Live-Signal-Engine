"""Versioned strategy configuration persistence model."""

import uuid

from sqlalchemy import Boolean, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column, relationship
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.types import Uuid

from app.models.base import Base, TimestampMixin


class Strategy(TimestampMixin, Base):
    """A named, versioned strategy definition and its serializable configuration."""

    __tablename__ = "strategies"
    __table_args__ = (UniqueConstraint("name", "version", name="uq_strategies_name_version"),)

    id: Mapped[uuid.UUID] = mapped_column(Uuid, primary_key=True, default=uuid.uuid4)
    name: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    version: Mapped[str] = mapped_column(String(64), nullable=False, default="1")
    description: Mapped[str | None] = mapped_column(String(1000))
    configuration: Mapped[dict[str, object]] = mapped_column(JSONB, nullable=False, default=dict)
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True, server_default="true")

    signals: Mapped[list["Signal"]] = relationship(back_populates="strategy")
    backtests: Mapped[list["Backtest"]] = relationship(back_populates="strategy")
