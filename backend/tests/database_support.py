"""Disposable PostgreSQL schemas for integration tests; SQLite for quick offline runs."""

import os
import re
import uuid

from sqlalchemy import text
from sqlalchemy.ext.asyncio import create_async_engine
from sqlalchemy.pool import NullPool


async def create_test_database(sqlite_path):
    url = os.environ.get("SCHEDULE_TEST_DATABASE_URL")
    if not url:
        return create_async_engine(f"sqlite+aiosqlite:///{sqlite_path}"), None
    if not url.startswith("postgresql+asyncpg://"):
        raise ValueError("SCHEDULE_TEST_DATABASE_URL must use postgresql+asyncpg")
    schema = f"schedule_test_{uuid.uuid4().hex}"
    admin = create_async_engine(url, poolclass=NullPool)
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'CREATE SCHEMA "{schema}"'))
    finally:
        await admin.dispose()
    engine = create_async_engine(url, poolclass=NullPool, connect_args={
        "server_settings": {"search_path": schema},
    })
    return engine, (url, schema)


async def close_test_database(engine, cleanup):
    await engine.dispose()
    if cleanup is None:
        return
    url, schema = cleanup
    if not re.fullmatch(r"schedule_test_[0-9a-f]{32}", schema):
        raise ValueError("Refusing to drop a non-test schema")
    admin = create_async_engine(url, poolclass=NullPool)
    try:
        async with admin.begin() as conn:
            await conn.execute(text(f'DROP SCHEMA "{schema}" CASCADE'))
    finally:
        await admin.dispose()
