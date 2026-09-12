"""
Database session management.

The database is optional. Quantimental's core product — live signals from
market data — needs no persistence at all; Postgres backs the news archive and
the batch sentiment pipeline. So engines are created lazily and only when
DATABASE_URL is set, and callers use `database_available()` to decide whether
to query or degrade.
"""

from __future__ import annotations

import logging
from typing import AsyncIterator, Optional

from sqlalchemy import create_engine
from sqlalchemy.engine import Engine
from sqlalchemy.ext.asyncio import AsyncEngine, AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import sessionmaker

from app.core.config import get_settings

logger = logging.getLogger(__name__)

settings = get_settings()

_sync_engine: Optional[Engine] = None
_async_engine: Optional[AsyncEngine] = None
_session_factory: Optional[sessionmaker] = None
_async_session_factory: Optional[async_sessionmaker] = None


def database_available() -> bool:
    """True when a database is configured. Check before touching a session."""
    return settings.database_configured


def get_sync_engine() -> Engine:
    """Lazily create the synchronous engine (used by Alembic and scripts)."""
    global _sync_engine
    if _sync_engine is None:
        url = settings.sync_database_url
        if not url:
            raise RuntimeError(
                "DATABASE_URL is not set. Start Postgres with `docker compose up -d` "
                "and set DATABASE_URL in your .env to use database-backed features."
            )
        _sync_engine = create_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
    return _sync_engine


def get_async_engine() -> AsyncEngine:
    """Lazily create the async engine (used by API routes)."""
    global _async_engine
    if _async_engine is None:
        url = settings.async_database_url
        if not url:
            raise RuntimeError(
                "DATABASE_URL is not set. Start Postgres with `docker compose up -d` "
                "and set DATABASE_URL in your .env to use database-backed features."
            )
        _async_engine = create_async_engine(url, pool_pre_ping=True, pool_size=5, max_overflow=10)
    return _async_engine


def get_session_factory() -> sessionmaker:
    """Session factory for synchronous callers."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(bind=get_sync_engine(), autocommit=False, autoflush=False)
    return _session_factory


def get_async_session_factory() -> async_sessionmaker:
    """Session factory for async callers."""
    global _async_session_factory
    if _async_session_factory is None:
        _async_session_factory = async_sessionmaker(
            get_async_engine(), class_=AsyncSession, expire_on_commit=False
        )
    return _async_session_factory


async def get_async_session() -> AsyncIterator[AsyncSession]:
    """FastAPI dependency yielding an async session."""
    factory = get_async_session_factory()
    async with factory() as session:
        yield session


def get_db():
    """FastAPI dependency yielding a synchronous session."""
    session = get_session_factory()()
    try:
        yield session
    finally:
        session.close()


async def dispose_engines() -> None:
    """Close pooled connections. Called on application shutdown."""
    global _sync_engine, _async_engine
    if _async_engine is not None:
        await _async_engine.dispose()
        _async_engine = None
    if _sync_engine is not None:
        _sync_engine.dispose()
        _sync_engine = None


async def check_connection() -> bool:
    """Ping the database. Returns False instead of raising, for health checks."""
    if not database_available():
        return False
    try:
        from sqlalchemy import text

        async with get_async_session_factory()() as session:
            await session.execute(text("SELECT 1"))
        return True
    except Exception as exc:
        logger.warning("Database health check failed: %s", exc)
        return False


def async_session() -> AsyncSession:
    """
    Open a new async session.

    Convenience wrapper so callers can write ``async with async_session() as s:``
    without reaching for the factory each time.
    """
    return get_async_session_factory()()
