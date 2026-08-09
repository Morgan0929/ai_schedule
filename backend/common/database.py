"""Shared async SQLAlchemy engine and session factory."""

import sys
from pathlib import Path

if sys.platform == "win32":
    import asyncio

    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy.ext.asyncio import AsyncSession, async_sessionmaker, create_async_engine
from sqlalchemy.orm import DeclarativeBase

from common.config import BACKEND_DIR, settings


if settings.USE_SQLITE:
    DB_URL = f"sqlite+aiosqlite:///{(BACKEND_DIR / 'dev.db').as_posix()}"
    ENGINE_KWARGS = {"echo": False}
else:
    DB_URL = settings.database_url
    ENGINE_KWARGS = {
        "echo": False,
        "pool_size": 20,
        "max_overflow": 10,
        "pool_pre_ping": True,
    }

engine = create_async_engine(DB_URL, **ENGINE_KWARGS)

async_session_factory = async_sessionmaker(
    engine,
    class_=AsyncSession,
    expire_on_commit=False,
)


class Base(DeclarativeBase):
    pass


async def get_db():
    """FastAPI dependency that provides one transaction-scoped session."""
    async with async_session_factory() as session:
        try:
            yield session
            await session.commit()
        except Exception:
            await session.rollback()
            raise
        finally:
            await session.close()


async def init_db():
    """Create ORM tables for local development."""
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
