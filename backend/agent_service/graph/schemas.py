"""
Node Input/Output Schema — Pydantic 结构化输出

每个 Node 的输出都是 Pydantic 模型，不是 raw JSON string。
LangChain: llm.with_structured_output(Schema) → 类型安全
"""
from typing import Literal, Any
from pydantic import BaseModel, Field


# ============================================================
# Node 1 — Planner 输出
# ============================================================

from enum import Enum

class Intent(str, Enum):
    """统一意图 — CREATE_TODO 用于无具体时间的待办"""
    CREATE_EVENT = "create_event"
    CREATE_TODO = "create_todo"
    UPDATE_EVENT = "update_event"
    DELETE_EVENT = "delete_event"
    QUERY_SCHEDULE = "query_schedule"
    QUERY_WEATHER = "query_weather"
    CHAT = "chat"
    UNKNOWN = "unknown"


def normalize_intent(raw: str) -> Intent:
    """统一意图名映射"""
    mapping = {
        # 旧名 → 新名
        "create_task": Intent.CREATE_EVENT,
        "create_reminder": Intent.CREATE_EVENT,
        "delete_task": Intent.DELETE_EVENT,
        "update_task": Intent.UPDATE_EVENT,
        # 查询
        "query_calendar": Intent.QUERY_SCHEDULE,
        "query_event": Intent.QUERY_SCHEDULE,
        # 标准名
        "create_event": Intent.CREATE_EVENT,
        "create_todo": Intent.CREATE_TODO,
        "update_event": Intent.UPDATE_EVENT,
        "delete_event": Intent.DELETE_EVENT,
        "query_schedule": Intent.QUERY_SCHEDULE,
        "query_weather": Intent.QUERY_WEATHER,
        # 其他
        "arrange_trip": Intent.CREATE_EVENT,
        "conflict_negotiation": Intent.CREATE_EVENT,
        "casual_chat": Intent.CHAT,
        "chat": Intent.CHAT,
    }
    lower = raw.lower().strip()
    if lower in mapping:
        return mapping[lower]
    try:
        return Intent(lower)
    except ValueError:
        return Intent.UNKNOWN


def planner_output_normalizer(raw: dict) -> dict:
    """自动修复 LLM 输出的常见错误: intent命名/字段缺失/参数名"""
    out = dict(raw)

    # intent 统一
    if "intent" in out:
        out["intent"] = normalize_intent(str(out["intent"])).value

    # entities: start→start_time, end→end_time
    entities = out.get("entities", {})
    if isinstance(entities, dict):
        if "start" in entities and "start_time" not in entities:
            entities["start_time"] = entities.pop("start")
        if "end" in entities and "end_time" not in entities:
            entities["end_time"] = entities.pop("end")

    # tool 映射
    tool_map = {
        "create_task": "create_task", "create_event": "create_task",
        "calendar_query": "check_calendar", "query_calendar": "check_calendar",
        "query_schedule": "check_calendar", "weather_query": "query_weather",
    }
    if out.get("tool"):
        out["tool"] = tool_map.get(out["tool"], out["tool"])

    # default confidence
    if "confidence" not in out or not out["confidence"]:
        out["confidence"] = 0.85

    return out


class PlannerOutput(BaseModel):
    """Planner Node: 意图识别结果"""
    intent: Intent = Field(default=Intent.UNKNOWN, description="用户意图")
    tool: str | None = Field(default=None)
    entities: dict[str, Any] = Field(default_factory=dict)
    confidence: float = Field(default=0.0, ge=0.0, le=1.0)
    source: str = Field(default="mock")
    reason: str = Field(default="")
    need_confirmation: bool = Field(default=False)


# schema 信息只在 planner 首次调用时打印 (避免模块导入时无条件输出)


# ============================================================
# Node 2 — Vision 输出
# ============================================================

class VisionOutput(BaseModel):
    """Document Analyzer: 文档图片分析结果"""
    document_type: Literal[
        "homework", "schedule", "ticket", "notice", "unknown"
    ] = Field(description="文档类型")

    extracted_data: dict[str, Any] = Field(default_factory=dict, description="提取的结构化数据")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="识别置信度")


# ============================================================
# Node 3 — Conflict 输出
# ============================================================

class ConflictOutput(BaseModel):
    """Coordinator: 冲突检测与协调"""
    has_conflict: bool = Field(default=False, description="是否存在时间冲突")
    conflicts: list[str] = Field(default_factory=list, description="冲突描述列表")
    solutions: list[str] = Field(default_factory=list, description="解决方案列表")


# ============================================================
# Node 4 — Reply 输出 (林的最终回复)
# ============================================================

class ReplyOutput(BaseModel):
    """Reply Node: 林的自然语言回复"""
    message: str = Field(description="林的自然语言回复内容")
    action_taken: list[str] = Field(default_factory=list, description="已执行的操作摘要")
    reminder_needed: bool = Field(default=False, description="是否需要设置提醒")
    follow_up_question: str | None = Field(default=None, description="需要进一步确认的问题")
