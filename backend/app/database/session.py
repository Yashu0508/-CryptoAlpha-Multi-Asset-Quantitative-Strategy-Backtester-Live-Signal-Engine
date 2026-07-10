"""Asynchronous SQLAlchemy session lifecycle."""

from collections.abc import AsyncGenerator

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine

from app.config.settings import get_settings

settings = get_settings()
engine = create_async_engine(settings.database_url, pool_pre_ping=True)
SessionLocal = async_sessionmaker(engine, class_=AsyncSession, expire_on_commit=False)


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Yield a request-scoped database session."""

    async with SessionLocal() as session:
        yield session


async def dispose_engine() -> None:
    """Close database connection pools during application shutdown."""

    await engine.dispose()
