"""课表相关 Pydantic 模型"""
from datetime import datetime, time
from pydantic import BaseModel, Field


class ScheduleAttachmentDTO(BaseModel):
    id: int
    schedule_id: int
    user_id: int
    file_name: str
    original_name: str
    content_type: str
    file_size: int
    file_url: str
    created_at: datetime | None = None

    model_config = {"from_attributes": True}


class ScheduleDTO(BaseModel):
    id: int
    user_id: int
    source: str
    course_name: str
    teacher: str | None = None
    location: str | None = None
    week_day: int
    start_week: int = 1
    end_week: int = 16
    start_time: time | None = None
    end_time: time | None = None
    start_section: int | None = None
    end_section: int | None = None
    semester: str
    raw_data: str | None = None
    is_active: bool = True
    created_at: datetime | None = None
    updated_at: datetime | None = None
    attachments: list[ScheduleAttachmentDTO] = Field(default_factory=list)

    model_config = {"from_attributes": True}


class ScheduleCreateDTO(BaseModel):
    course_name: str = Field(..., min_length=1, max_length=256)
    teacher: str | None = Field(None, max_length=128)
    location: str | None = Field(None, max_length=256)
    week_day: int = Field(..., ge=1, le=7)
    start_week: int = Field(1, ge=1)
    end_week: int = Field(16, ge=1)
    start_time: time | None = None
    end_time: time | None = None
    start_section: int | None = None
    end_section: int | None = None
    semester: str | None = None
    source: str = Field(default="manual", max_length=64)
    raw_data: dict | None = None


class ScheduleUpdateDTO(BaseModel):
    course_name: str | None = Field(None, min_length=1, max_length=256)
    teacher: str | None = Field(None, max_length=128)
    location: str | None = Field(None, max_length=256)
    week_day: int | None = Field(None, ge=1, le=7)
    start_week: int | None = Field(None, ge=1)
    end_week: int | None = Field(None, ge=1)
    start_time: time | None = None
    end_time: time | None = None
    start_section: int | None = None
    end_section: int | None = None
    semester: str | None = None
    source: str | None = Field(None, max_length=64)
    raw_data: dict | None = None
