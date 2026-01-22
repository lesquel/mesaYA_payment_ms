"""Database connection management using async SQLAlchemy."""

from typing import AsyncGenerator

from sqlalchemy.ext.asyncio import (
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from mesaYA_payment_ms.shared.core.settings import get_settings


class Base(DeclarativeBase):
    """Base class for all ORM models."""

    pass


# Global engine and session factory
_engine = None
_async_session_factory = None


async def init_db() -> None:
    """Initialize database connection."""
    global _engine, _async_session_factory

    settings = get_settings()

    _engine = create_async_engine(
        settings.database_url,
        echo=settings.debug,
        pool_pre_ping=True,
        pool_size=5,
        max_overflow=10,
    )

    _async_session_factory = async_sessionmaker(
        bind=_engine,
        class_=AsyncSession,
        expire_on_commit=False,
        autoflush=False,
    )

    print(f"✅ Database connection initialized: {settings.database_url.split('@')[-1]}")


async def close_db() -> None:
    """Close database connection."""
    global _engine

    if _engine:
        await _engine.dispose()
        print("👋 Database connection closed")


async def get_db_session() -> AsyncGenerator[AsyncSession, None]:
    """Get async database session."""
    global _async_session_factory

    if _async_session_factory is None:
        await init_db()

    async with _async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise


# Type alias for dependency injection
DatabaseSession = AsyncSession
