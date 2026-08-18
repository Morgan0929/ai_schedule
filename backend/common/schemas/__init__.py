"""
Pydantic 模型 — 公共模型导出
"""
from common.schemas.response import Result, PageResult
from common.schemas.user import UserDTO, UserCreateDTO, UserLoginDTO, LoginResultDTO
from common.schemas.task import TaskDTO, TaskCreateDTO, TaskUpdateDTO, TaskAttachmentDTO
from common.schemas.timeline import TimelineDTO, TimelineEvent, TimelineGenerateDTO
from common.schemas.conflict import ConflictDTO, ConflictResolveDTO
from common.schemas.agent import AgentChatRequest, AgentChatResponse, AgentSuggestion
from common.schemas.schedule import ScheduleDTO, ScheduleCreateDTO, ScheduleUpdateDTO, ScheduleAttachmentDTO

__all__ = [
    # Response
    "Result",
    "PageResult",
    # User
    "UserDTO",
    "UserCreateDTO",
    "UserLoginDTO",
    "LoginResultDTO",
    # Task
    "TaskDTO",
    "TaskCreateDTO",
    "TaskUpdateDTO",
    "TaskAttachmentDTO",
    # Timeline
    "TimelineDTO",
    "TimelineEvent",
    "TimelineGenerateDTO",
    # Conflict
    "ConflictDTO",
    "ConflictResolveDTO",
    # Agent
    "AgentChatRequest",
    "AgentChatResponse",
    "AgentSuggestion",
    # Schedule
    "ScheduleDTO",
    "ScheduleCreateDTO",
    "ScheduleUpdateDTO",
    "ScheduleAttachmentDTO",
]
