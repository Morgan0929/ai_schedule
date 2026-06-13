"""
冲突模型
"""
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class SeverityEnum(str, Enum):
    CRITICAL = "CRITICAL"
    WARNING = "WARNING"
    INFO = "INFO"


class ConflictDTO(BaseModel):
    """冲突响应"""
    id: int
    user_id: int
    task_a_id: int
    task_b_id: int
    task_a_title: str | None = None
    task_b_title: str | None = None
    overlap_start: datetime | None = None
    overlap_end: datetime | None = None
    severity: SeverityEnum = SeverityEnum.WARNING
    resolution: dict[str, Any] | None = None
    resolved: bool = False
    resolved_by: str | None = None
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ConflictResolveDTO(BaseModel):
    """AI 冲突解决请求"""
    conflict_id: int
    user_choice: str | None = Field(None, description="用户选择的方案，如 'A' 'B' 'C'，为空则 AI 自动选择最佳方案")
    user_feedback: str | None = Field(None, description="用户对方案的补充意见（自然语言）")
