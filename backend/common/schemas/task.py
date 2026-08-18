"""
任务/行程模型
"""
from datetime import datetime
from enum import Enum
from typing import Any
from pydantic import BaseModel, Field


class PriorityEnum(str, Enum):
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"


class TaskStatusEnum(str, Enum):
    PENDING = "PENDING"
    IN_PROGRESS = "IN_PROGRESS"
    COMPLETED = "COMPLETED"
    CANCELLED = "CANCELLED"


class TaskAttachmentDTO(BaseModel):
    """任务附件元数据。"""
    id: str
    task_id: int
    file_name: str
    original_name: str
    content_type: str
    file_size: int
    file_url: str
    created_at: datetime | None = None


class TaskCategoryEnum(str, Enum):
    MEETING = "MEETING"
    TRIP = "TRIP"
    PERSONAL = "PERSONAL"
    WORK = "WORK"


class TaskDTO(BaseModel):
    """任务响应"""
    id: int
    user_id: int
    title: str
    description: str | None = None
    start_time: datetime
    end_time: datetime
    priority: PriorityEnum = PriorityEnum.MEDIUM
    status: TaskStatusEnum = TaskStatusEnum.PENDING
    location: str | None = None
    category: TaskCategoryEnum = TaskCategoryEnum.PERSONAL
    tags: list[str] = Field(default_factory=list)
    extra_data: dict[str, Any] = Field(default_factory=dict)
    created_at: datetime | None = None
    updated_at: datetime | None = None
    attachments: list[TaskAttachmentDTO] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class TaskCreateDTO(BaseModel):
    """创建任务请求"""
    title: str = Field(..., min_length=1, max_length=256)
    description: str | None = None
    start_time: datetime
    end_time: datetime
    priority: PriorityEnum = PriorityEnum.MEDIUM
    location: str | None = None
    category: TaskCategoryEnum = TaskCategoryEnum.PERSONAL
    tags: list[str] = Field(default_factory=list)

    def validate_time_range(self) -> bool:
        """验证时间范围合法性"""
        return self.end_time > self.start_time


class TaskUpdateDTO(BaseModel):
    """更新任务请求"""
    title: str | None = Field(None, min_length=1, max_length=256)
    description: str | None = None
    start_time: datetime | None = None
    end_time: datetime | None = None
    priority: PriorityEnum | None = None
    status: TaskStatusEnum | None = None
    location: str | None = None
    category: TaskCategoryEnum | None = None
    tags: list[str] | None = None
