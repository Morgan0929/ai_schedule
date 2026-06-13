"""
爬虫服务数据模型
"""
from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any


class CrawlDataDTO(BaseModel):
    """爬虫数据"""
    id: int
    user_id: int | None = None
    source: str
    source_url: str | None = None
    raw_data: dict[str, Any] = {}
    extracted_info: dict[str, Any] | None = None
    crawled_at: datetime | None = None

    model_config = {"from_attributes": True}


class CrawlTaskRequest(BaseModel):
    """爬取任务请求"""
    source: str = Field(..., description="数据源类型：weather/flight/news/calendar")
    url: str | None = Field(None, description="目标 URL")
    params: dict[str, Any] = Field(default_factory=dict, description="额外参数")
