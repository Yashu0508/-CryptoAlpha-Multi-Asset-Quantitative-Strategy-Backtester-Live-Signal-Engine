"""Create the initial CryptoAlpha market-data schema.

Revision ID: 20260710_0001
Revises:
Create Date: 2026-07-10
"""

from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "20260710_0001"
down_revision = None
branch_labels = None
depends_on = None


def timestamps() -> list[sa.Column[object]]:
    """Return standard audit columns shared by mutable application entities."""

    return [
        sa.Column("created_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), server_default=sa.text("now()"), nullable=False),
    ]


def upgrade() -> None:
    """Create normalized trading tables and TimescaleDB optimization when available."""

    op.create_table(
        "assets",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("exchange", sa.String(length=64), nullable=False),
        sa.Column("symbol", sa.String(length=64), nullable=False),
        sa.Column("base_currency", sa.String(length=16), nullable=False),
        sa.Column("quote_currency", sa.String(length=16), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("exchange", "symbol", name="uq_assets_exchange_symbol"),
    )
    op.create_index("ix_assets_symbol", "assets", ["symbol"])

    op.create_table(
        "strategies",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("name", sa.String(length=128), nullable=False),
        sa.Column("version", sa.String(length=64), nullable=False),
        sa.Column("description", sa.String(length=1000)),
        sa.Column("configuration", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("is_active", sa.Boolean(), server_default=sa.text("true"), nullable=False),
        *timestamps(),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("name", "version", name="uq_strategies_name_version"),
    )
    op.create_index("ix_strategies_name", "strategies", ["name"])

    op.create_table(
        "ohlcv",
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("timestamp", sa.DateTime(timezone=True), nullable=False),
        sa.Column("interval", sa.String(length=12), nullable=False),
        sa.Column("open", sa.Numeric(24, 12), nullable=False),
        sa.Column("high", sa.Numeric(24, 12), nullable=False),
        sa.Column("low", sa.Numeric(24, 12), nullable=False),
        sa.Column("close", sa.Numeric(24, 12), nullable=False),
        sa.Column("volume", sa.Numeric(32, 12), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("asset_id", "timestamp", "interval"),
    )
    op.create_index("ix_ohlcv_asset_interval_timestamp", "ohlcv", ["asset_id", "interval", "timestamp"])

    op.create_table(
        "trades",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_key", sa.String(length=128), nullable=False),
        sa.Column("side", sa.String(length=8), nullable=False),
        sa.Column("quantity", sa.Numeric(32, 12), nullable=False),
        sa.Column("price", sa.Numeric(24, 12), nullable=False),
        sa.Column("fee", sa.Numeric(24, 12), nullable=False),
        sa.Column("executed_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("external_order_id", sa.String(length=128)),
        *timestamps(),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("external_order_id"),
    )
    op.create_index("ix_trades_asset_executed_at", "trades", ["asset_id", "executed_at"])
    op.create_index("ix_trades_portfolio_executed_at", "trades", ["portfolio_key", "executed_at"])
    op.create_index("ix_trades_executed_at", "trades", ["executed_at"])

    op.create_table(
        "signals",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("asset_id", sa.Uuid()),
        sa.Column("action", sa.String(length=16), nullable=False),
        sa.Column("confidence", sa.Numeric(6, 5)),
        sa.Column("generated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("payload", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"]),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"], ondelete="CASCADE"),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_signals_strategy_generated_at", "signals", ["strategy_id", "generated_at"])
    op.create_index("ix_signals_generated_at", "signals", ["generated_at"])

    op.create_table(
        "backtests",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("strategy_id", sa.Uuid(), nullable=False),
        sa.Column("status", sa.String(length=32), nullable=False),
        sa.Column("started_at", sa.DateTime(timezone=True)),
        sa.Column("completed_at", sa.DateTime(timezone=True)),
        sa.Column("parameters", postgresql.JSONB(astext_type=sa.Text()), nullable=False),
        sa.Column("metrics", postgresql.JSONB(astext_type=sa.Text())),
        sa.Column("initial_capital", sa.Numeric(24, 12), nullable=False),
        sa.Column("final_equity", sa.Numeric(24, 12)),
        *timestamps(),
        sa.ForeignKeyConstraint(["strategy_id"], ["strategies.id"]),
        sa.PrimaryKeyConstraint("id"),
    )
    op.create_index("ix_backtests_strategy_started_at", "backtests", ["strategy_id", "started_at"])

    op.create_table(
        "portfolio_holdings",
        sa.Column("id", sa.Uuid(), nullable=False),
        sa.Column("portfolio_key", sa.String(length=128), nullable=False),
        sa.Column("asset_id", sa.Uuid(), nullable=False),
        sa.Column("quantity", sa.Numeric(32, 12), nullable=False),
        sa.Column("average_entry_price", sa.Numeric(24, 12)),
        sa.Column("last_mark_price", sa.Numeric(24, 12)),
        sa.Column("as_of", sa.DateTime(timezone=True), nullable=False),
        *timestamps(),
        sa.ForeignKeyConstraint(["asset_id"], ["assets.id"], ondelete="RESTRICT"),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("portfolio_key", "asset_id", name="uq_portfolio_holdings_portfolio_asset"),
    )
    op.create_index("ix_portfolio_holdings_portfolio_key", "portfolio_holdings", ["portfolio_key"])
    op.create_index("ix_portfolio_holdings_as_of", "portfolio_holdings", ["as_of"])

    # The schema remains valid on PostgreSQL. On TimescaleDB, promote candles to a hypertable.
    op.execute(
        """
        DO $$
        BEGIN
            IF EXISTS (SELECT 1 FROM pg_available_extensions WHERE name = 'timescaledb') THEN
                CREATE EXTENSION IF NOT EXISTS timescaledb;
                PERFORM create_hypertable('ohlcv', 'timestamp', if_not_exists => TRUE);
            END IF;
        END
        $$;
        """
    )


def downgrade() -> None:
    """Drop application tables in dependency order; extensions are intentionally retained."""

    op.drop_table("portfolio_holdings")
    op.drop_table("backtests")
    op.drop_table("signals")
    op.drop_table("trades")
    op.drop_table("ohlcv")
    op.drop_table("strategies")
    op.drop_table("assets")
