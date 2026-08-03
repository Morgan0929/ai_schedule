"""
Agent 会话模型
"""
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field


class AgentSuggestion(BaseModel):
    """Agent 建议方案"""
    plan_id: str = Field(..., description="方案标识 A/B/C")
    title: str = Field(..., description="方案标题")
    description: str = Field(..., description="具体方案描述")
    impact: str = Field(default="", description="影响分析")
    is_recommended: bool = Field(default=False, description="是否为推荐方案")


class AgentChatRequest(BaseModel):
    """Agent 对话请求"""
    message: str = Field(..., min_length=1, description="用户自然语言输入")
    session_id: str | None = Field(None, description="会话 ID，不传则新建会话")
    user_id: int | None = Field(None, description="用户 ID")
    history: list[dict[str, str]] = Field(default_factory=list, description="对话历史 [{\"role\":\"user/assistant\",\"content\":\"...\"}]")
    context: dict[str, Any] = Field(default_factory=dict, description="额外上下文")


class AgentChatResponse(BaseModel):
    """Agent 对话响应"""
    reply: str = Field(..., description="AI 回复")
    session_id: str = Field(..., description="会话 ID")
    conflicts: list["ConflictDTO"] = Field(default_factory=list, description="检测到的冲突列表")
    suggestions: list[AgentSuggestion] = Field(default_factory=list, description="建议方案")
    tasks_created: list[int] = Field(default_factory=list, description="新创建的任务 ID 列表")
    tasks_updated: list[int] = Field(default_factory=list, description="已更新的任务 ID 列表")
    actions_taken: list[str] = Field(default_factory=list, description="Agent 执行的操作摘要")


# 解决循环引用
from common.schemas.conflict import ConflictDTO  # noqa: E402
AgentChatResponse.model_rebuild()
