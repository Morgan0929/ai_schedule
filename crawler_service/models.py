"""
爬虫服务 — Pydantic DTO + SQLAlchemy ORM 模型
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field
from sqlalchemy import String, Integer, Text, JSON, BigInteger
from sqlalchemy.orm import Mapped, mapped_column
from sqlalchemy.sql import func
from common.database import Base


# ============ SQLAlchemy ORM ============

class CrawlDataModel(Base):
    """爬虫数据存储表"""
    __tablename__ = "crawl_data"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
    user_id: Mapped[int | None] = mapped_column(Integer, nullable=True)
    source: Mapped[str] = mapped_column(String(64), nullable=False, index=True)
    source_url: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_data: Mapped[dict] = mapped_column(JSON, default=dict)
    extracted_info: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    status: Mapped[str] = mapped_column(String(32), default="SUCCESS")  # SUCCESS / FAILED / PENDING
    error_message: Mapped[str | None] = mapped_column(Text, nullable=True)
    crawled_at: Mapped[datetime] = mapped_column(server_default=func.now())

    def __repr__(self) -> str:
        return f"<CrawlData(id={self.id}, source={self.source}, status={self.status})>"


# ============ Pydantic DTO ============

class CrawlDataDTO(BaseModel):
    """爬虫数据响应"""
    id: int
    user_id: int | None = None
    source: str
    source_url: str | None = None
    raw_data: dict[str, Any] = {}
    extracted_info: dict[str, Any] | None = None
    status: str = "SUCCESS"
    crawled_at: datetime | None = None

    model_config = {"from_attributes": True}


class CrawlTriggerRequest(BaseModel):
    """爬取触发请求"""
    source: str = Field(..., description="数据源类型：weather / news / flight")
    params: dict[str, Any] = Field(default_factory=dict, description="爬虫参数")
    user_id: int | None = Field(None, description="关联用户 ID")


class CrawlTriggerResponse(BaseModel):
    """爬取触发响应"""
    task_id: int
    source: str
    status: str
    result: dict[str, Any] | None = None
