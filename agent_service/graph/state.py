"""
Agent 状态定义

LangGraph 的状态图使用此状态对象在节点间传递数据
"""
from typing import TypedDict, Annotated, Any
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    Agent 全局状态

    在 LangGraph 的每个节点间流转，
    每个节点可读取/修改此状态
    """
    # 消息历史（自动追加）
    messages: Annotated[list[BaseMessage], add_messages]

    # 用户输入
    user_input: str
    user_id: int
    session_id: str

    # Planner 输出
    intent: str                     # 用户意图类型
    sub_tasks: list[dict[str, Any]]  # 拆解后的子任务

    # Tools 输出
    calendar_events: list[dict[str, Any]]   # 查询到的日历事件
    external_data: dict[str, Any]           # 外部数据（天气/航班等）

    # Conflict 输出
    conflicts_found: list[dict[str, Any]]   # 检测到的冲突
    conflict_count: int

    # Coordinator 输出
    suggestions: list[dict[str, Any]]       # AI 建议方案
    recommended_plan: str                   # 推荐方案 ID

    # 最终输出
    final_reply: str                # 最终回复给用户的内容
    actions_taken: list[str]        # 执行的操作摘要
    tasks_created: list[int]        # 新创建的任务 ID
    tasks_updated: list[int]        # 已更新的任务 ID

    # 错误
    error: str | None
