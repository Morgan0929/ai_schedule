"""
时间线服务 — 数据库实体模型 (SQLAlchemy ORM)
"""
from datetime import date, datetime
from sqlalchemy import String, Integer, BigInteger, Boolean, Date, ForeignKey, Text
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from common.database import Base


class TaskModel(Base):
    """任务/行程表"""
    __tablename__ = "task"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    title: Mapped[str] = mapped_column(String(256), nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    start_time: Mapped[datetime] = mapped_column(nullable=False, index=True)
    end_time: Mapped[datetime] = mapped_column(nullable=False, index=True)
    priority: Mapped[str] = mapped_column(String(16), default="MEDIUM")
    status: Mapped[str] = mapped_column(String(32), default="PENDING")
    location: Mapped[str | None] = mapped_column(String(512), nullable=True)
    category: Mapped[str] = mapped_column(String(32), default="PERSONAL")
    tags: Mapped[dict] = mapped_column(JSONB, default=list)
    metadata: Mapped[dict] = mapped_column(JSONB, default=dict)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class TimelineModel(Base):
    """时间线表"""
    __tablename__ = "timeline"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    date: Mapped[date] = mapped_column(Date, nullable=False)
    events: Mapped[dict] = mapped_column(JSONB, default=list)
    generated_by: Mapped[str] = mapped_column(String(16), default="MANUAL")
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
    updated_at: Mapped[datetime] = mapped_column(server_default=func.now(), onupdate=func.now())


class ConflictModel(Base):
    """冲突表"""
    __tablename__ = "conflict"

    id: Mapped[int] = mapped_column(BigInteger, primary_key=True, autoincrement=True)
    user_id: Mapped[int] = mapped_column(BigInteger, nullable=False, index=True)
    task_a_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    task_b_id: Mapped[int] = mapped_column(BigInteger, nullable=False)
    overlap_start: Mapped[datetime | None] = mapped_column(nullable=True)
    overlap_end: Mapped[datetime | None] = mapped_column(nullable=True)
    severity: Mapped[str] = mapped_column(String(16), default="WARNING")
    resolution: Mapped[dict | None] = mapped_column(JSONB, nullable=True)
    resolved: Mapped[bool] = mapped_column(Boolean, default=False)
    resolved_by: Mapped[str | None] = mapped_column(String(16), nullable=True)
    created_at: Mapped[datetime] = mapped_column(server_default=func.now())
