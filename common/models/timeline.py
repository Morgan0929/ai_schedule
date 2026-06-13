"""
时间线模型
"""
from datetime import date as date_type, datetime as datetime_type
from enum import Enum
from pydantic import BaseModel, Field


class GeneratedByEnum(str, Enum):
    AI = "AI"
    MANUAL = "MANUAL"


class TimelineEvent(BaseModel):
    """时间线中的单个事件"""
    time: str = Field(..., description="时间，如 '09:00'")
    duration: int = Field(..., ge=0, description="持续时长（分钟）")
    event: str = Field(..., description="事件名称")
    task_id: int | None = Field(None, description="关联的任务 ID")
    category: str = "PERSONAL"
    location: str | None = None
    priority: str = "MEDIUM"


class TimelineDTO(BaseModel):
    """时间线响应"""
    id: int
    user_id: int
    date: date_type
    events: list[TimelineEvent] = []
    generated_by: GeneratedByEnum = GeneratedByEnum.MANUAL
    created_at: datetime_type | None = None
    updated_at: datetime_type | None = None

    model_config = {"from_attributes": True}


class TimelineGenerateDTO(BaseModel):
    """AI 生成时间线请求"""
    date: date_type = Field(..., description="目标日期")
    user_preferences: str | None = Field(None, description="用户偏好（自然语言）")
    include_existing: bool = Field(default=True, description="是否包含已有任务")
