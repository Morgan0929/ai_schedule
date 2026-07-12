"""
SQLAlchemy 异步数据库配置

支持 PostgreSQL（生产）和 SQLite（开发无 Docker 时）
通过环境变量 USE_SQLITE=true 切换
"""
import sys
if sys.platform == 'win32':
    import asyncio
    asyncio.set_event_loop_policy(asyncio.WindowsSelectorEventLoopPolicy())

from sqlalchemy.ext.asyncio import AsyncSession, create_async_engine, async_sessionmaker
from sqlalchemy.orm import DeclarativeBase
from common.config import settings

# 根据配置选择数据库
if settings.USE_SQLITE:
    # SQLite 开发模式 — 无需 Docker
    DB_URL = "sqlite+aiosqlite:///./dev.db"
    ENGINE_KWARGS = {"echo": settings.ENV == "dev"}
else:
    # PostgreSQL 生产模式
    DB_URL = settings.database_url
    ENGINE_KWARGS = {
        "echo": settings.ENV == "dev",
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
    """SQLAlchemy 声明式基类 — 所有 ORM 模型继承此类"""
    pass


async def get_db():
    """
    获取数据库会话（FastAPI 依赖注入用）

    用法：
        @app.get("/tasks")
        async def list_tasks(db: AsyncSession = Depends(get_db)):
            ...
    """
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
    """
    初始化数据库表（开发环境使用）

    遍历所有继承 Base 的 ORM 模型，自动建表。
    生产环境请使用 Alembic 迁移。
    """
    async with engine.begin() as conn:
        await conn.run_sync(Base.metadata.create_all)
