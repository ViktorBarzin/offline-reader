"""Async SQLAlchemy plumbing.

SQLite (aiosqlite) is the production store (ADR-0004: metadata on the PVC, not
shared Postgres); the DSN is overridable so a Postgres (asyncpg) target also
works. For SQLite the app creates the schema in-process at startup
(``Base.metadata.create_all``) — there is no migration tool.
"""

from sqlalchemy.ext.asyncio import (
    AsyncEngine,
    AsyncSession,
    async_sessionmaker,
    create_async_engine,
)
from sqlalchemy.orm import DeclarativeBase

from offline_reader_api.config import get_settings


class Base(DeclarativeBase):
    """Declarative base for all offline-reader tables."""


def create_engine(dsn: str | None = None) -> AsyncEngine:
    """Engine for the configured DSN (override for tests)."""
    return create_async_engine(dsn or get_settings().db_dsn)


def create_session_factory(engine: AsyncEngine) -> async_sessionmaker[AsyncSession]:
    """Session factory bound to *engine* (``expire_on_commit=False`` — objects
    stay usable after commit, e.g. when serialised into a response)."""
    return async_sessionmaker(engine, expire_on_commit=False)
