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

class PlannerOutput(BaseModel):
    """Planner Node: 意图识别结果 (with confidence + source)"""
    intent: Literal[
        "create_task", "CREATE_TASK",
        "delete_task", "DELETE_TASK",
        "update_task", "UPDATE_TASK",
        "query_schedule", "QUERY_SCHEDULE", "QUERY_CALENDAR",
        "query_weather", "QUERY_WEATHER",
        "arrange_trip", "ARRANGE_TRIP",
        "image_analysis", "IMAGE_ANALYSIS",
        "detect_conflict", "DETECT_CONFLICT",
        "chat", "CHAT",
        "unknown", "UNKNOWN",
    ] = Field(description="用户意图类型")

    tool: str | None = Field(default=None, description="工具名称")
    entities: dict[str, Any] = Field(default_factory=dict, description="提取的实体")
    confidence: float = Field(default=0.0, ge=0.0, le=1.0, description="置信度")
    source: str = Field(default="mock", description="识别来源: llm / mock")
    reason: str = Field(default="", description="为什么判定为该意图")
    need_confirmation: bool = Field(default=False, description="是否需要用户确认")


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
