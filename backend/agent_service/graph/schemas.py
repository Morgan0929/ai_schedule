"""
Node Input/Output Schema

每个 Node 的职责边界:
  Node = 流程控制 (我该调用谁? 数据该往哪走?)
  Prompt = 思考 (ChatPromptTemplate, 只负责一个任务)
  Tool = 执行 (操作数据库/API)

数据流向:
  AgentState.messages ──┬──► Planner ──► intent, sub_tasks
                        ├──► Tools ────► tasks_created, actions_taken
                        ├──► Conflict ─► conflicts_found, conflict_count
                        ├──► Coordinator ─► suggestions, recommended_plan
                        └──► Reply ────► final_reply
"""
from typing import TypedDict, Annotated, Any, Literal
from langgraph.graph.message import add_messages
from langchain_core.messages import BaseMessage


class AgentState(TypedDict):
    """
    林的主状态 — 所有 Node 共享

    messages:       LangGraph 标准消息流 (System → Human → AI → Tool → AI ...)
    user_input:     用户最新输入
    user_id:        用户 ID
    session_id:     会话 ID

    === Planner 输出 ===
    intent:         意图类型 (CREATE_TASK / QUERY_CALENDAR / ...)
    sub_tasks:      拆解后的子任务列表

    === Tools 输出 ===
    calendar_events: 查询到的日程
    external_data:   外部数据 (天气等)
    tasks_created:   新创建的任务 ID 列表
    tasks_updated:   更新的任务 ID 列表
    actions_taken:   已执行的操作摘要

    === Conflict 输出 ===
    conflicts_found: 检测到的冲突列表
    conflict_count:  冲突数量

    === Coordinator 输出 ===
    suggestions:     AI 建议方案
    recommended_plan: 推荐方案 ID

    === Reply 输出 ===
    final_reply:     最终回复给用户的内容

    === 错误 ===
    error:           错误信息 (null = 正常)
    """
    messages: Annotated[list[BaseMessage], add_messages]
    user_input: str
    user_id: int
    session_id: str

    intent: str
    sub_tasks: list[dict[str, Any]]

    calendar_events: list[dict[str, Any]]
    external_data: dict[str, Any]
    tasks_created: list[int]
    tasks_updated: list[int]
    actions_taken: list[str]

    conflicts_found: list[dict[str, Any]]
    conflict_count: int

    suggestions: list[dict[str, Any]]
    recommended_plan: str

    final_reply: str
    error: str | None


# ============ Node 边界定义 ============

# Planner:
#   IN:  user_input, messages (上下文)
#   OUT: intent, sub_tasks

# Tools Executor:
#   IN:  sub_tasks, user_id
#   OUT: calendar_events, external_data, tasks_created, actions_taken

# Conflict Check:
#   IN:  user_id, tasks_created
#   OUT: conflicts_found, conflict_count

# Coordinator:
#   IN:  conflicts_found, user_input
#   OUT: suggestions, recommended_plan

# Reply:
#   IN:  intent, actions_taken, conflicts_found, suggestions, user_input
#   OUT: final_reply
