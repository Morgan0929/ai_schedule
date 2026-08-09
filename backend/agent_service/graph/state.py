"""
Agent 全局状态 — LangGraph 节点间数据流

Node I/O Schema 见 schemas.py (Pydantic 结构化输出模型)
"""
from typing import TypedDict, Annotated, Any
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict, total=False):
    """Agent 全局状态 — total=False 允许节点返回部分更新"""

    # 消息流 (LangGraph 标准)
    messages: Annotated[list[BaseMessage], add_messages]

    # 用户输入
    user_input: str
    user_id: int
    session_id: str

    # Planner 输出
    intent: str
    sub_tasks: list[dict[str, Any]]

    # Tools 输出
    calendar_events: list[dict[str, Any]]
    external_data: dict[str, Any]
    tasks_created: list[int]
    tasks_updated: list[int]
    actions_taken: list[str]

    # Conflict 输出
    conflicts_found: list[dict[str, Any]]
    conflict_count: int

    # Coordinator 输出
    suggestions: list[dict[str, Any]]
    recommended_plan: str

    # Reply 输出
    final_reply: str
    _structured_info: str
    _intent: str

    # Validator
    needs_confirmation: bool
    _confirm_message: str
    _issues: list[str]
    _confidence: float
    _source: str
    _validated: bool
    _skip_validator: bool
    _skip_planner: bool

    # Conflict Context (多轮)
    pending_action: dict
    execution_context: dict
    active_flow: str
    pending_tasks: list[dict]
    _pending_event: dict
    schedule_found: bool
    query_date_label: str
    need_info: list[str]
    _soft_warning: str
    _flow_paused: bool
    _paused_pending: dict

    # Middleware
    tool_calls_count: int
    _tool_history: list[str]
    _compressed_messages: bool

    # 错误
    error: str | None
