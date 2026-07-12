"""
LangGraph 状态图 — Agent 完整工作流

节点流程:
    START → planner → tools_executor → conflict_check → coordinator → reply → END

条件分支:
    - 无子任务 → 跳过 tools_executor
    - 无冲突 → 跳过 coordinator
"""
import json
from typing import Any, Literal
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage

from agent_service.graph.state import AgentState
from agent_service.graph.planner import planner_node
from agent_service.graph.tools import execute_tool
from agent_service.utils.coordinator import coordinator_node
from agent_service.llm.deepseek_client import chat_completion, is_llm_available
from agent_service.llm.mock_agent import mock_chat


# ============ 各节点实现 ============

async def tools_executor_node(state: AgentState) -> dict[str, Any]:
    """
    工具执行节点：遍历 planner 输出的 sub_tasks，逐一执行
    """
    sub_tasks = state.get("sub_tasks", [])
    user_id = state.get("user_id", 0)

    if not sub_tasks:
        return {"calendar_events": [], "external_data": {}, "tasks_created": [], "error": None}

    calendar_events = []
    external_data = {}
    tasks_created = []
    actions_taken = []

    for task in sub_tasks:
        action = task.get("action", "")
        params = task.get("params", {})

        result = await execute_tool(action, params, user_id)

        if result.get("success"):
            tool_result = result.get("result", {})

            if action in ("query_calendar", "check_calendar"):
                if isinstance(tool_result, list):
                    calendar_events.extend(tool_result)
            elif action == "create_task":
                if isinstance(tool_result, dict) and tool_result.get("id"):
                    tasks_created.append(tool_result["id"])
                    actions_taken.append(f"创建任务「{tool_result.get('title', '')}」")
            elif action in ("update_task", "update_task_tool"):
                actions_taken.append(f"更新任务 #{params.get('task_id', '')}")
            elif action == "delete_task":
                actions_taken.append(f"删除任务 #{params.get('task_id', '')}")
            elif action == "query_weather":
                external_data["weather"] = tool_result

    return {
        "calendar_events": calendar_events,
        "external_data": external_data,
        "tasks_created": tasks_created,
        "actions_taken": actions_taken,
        "error": None,
    }


async def conflict_check_node(state: AgentState) -> dict[str, Any]:
    """
    冲突检测节点：检查新创建任务与已有任务是否冲突
    """
    from timeline_service.utils.conflict_detector import ConflictDetector, DetectedConflict
    from timeline_service.repository.task_repo import TaskRepository
    from common.database import async_session_factory

    user_id = state.get("user_id", 0)
    calendar_events = state.get("calendar_events", [])

    if not calendar_events:
        return {"conflicts_found": [], "conflict_count": 0, "error": None}

    async with async_session_factory() as db:
        repo = TaskRepository(db)
        from datetime import datetime, timedelta
        now = datetime.now()
        tasks = await repo.find_by_user_time_range(user_id, now - timedelta(days=1), now + timedelta(days=30))

    if len(tasks) < 2:
        return {"conflicts_found": [], "conflict_count": 0, "error": None}

    detector = ConflictDetector()
    report = detector.detect(list(tasks))

    conflicts = []
    for c in report.conflicts:
        conflicts.append({
            "task_a": c.task_a_title,
            "task_b": c.task_b_title,
            "severity": c.severity.value if hasattr(c.severity, 'value') else c.severity,
            "reason": c.reason,
        })

    return {"conflicts_found": conflicts, "conflict_count": len(conflicts), "error": None}


async def reply_node(state: AgentState) -> dict[str, Any]:
    """
    回复生成节点：汇总所有信息，生成最终回复
    """
    intent = state.get("intent", "CHAT")
    actions = state.get("actions_taken", [])
    tasks_created = state.get("tasks_created", [])
    conflicts = state.get("conflicts_found", [])
    calendar_events = state.get("calendar_events", [])
    suggestions = state.get("suggestions", [])

    # 构建结构化摘要
    summary_parts = []
    if actions:
        summary_parts.append("📋 已执行操作:\n" + "\n".join(f"  • {a}" for a in actions))
    if calendar_events:
        summary_parts.append(f"📅 查询到 {len(calendar_events)} 个相关日程")
    if conflicts:
        summary_parts.append(f"⚠️ 发现 {len(conflicts)} 个时间冲突")
        for c in conflicts:
            summary_parts.append(f"  • {c.get('reason', '')}")
    if suggestions:
        summary_parts.append("💡 建议方案:")
        for s in suggestions:
            tag = "⭐推荐" if s.get("is_recommended") else "   "
            summary_parts.append(f"  [{s.get('plan_id', '?')}] {tag} {s.get('title', '')}")

    structured_info = "\n\n".join(summary_parts) if summary_parts else ""

    # 使用 LLM 或 mock 生成自然语言回复（林的 persona）
    if is_llm_available() and structured_info:
        final_reply = await chat_completion([
            {"role": "system", "content": (
                "你是林，用户的个人事务秘书。性格随性开朗，像一个熟悉用户习惯的私人助理。\n"
                "基于以下结构化信息，用林的口吻生成友好的中文回复。\n"
                "保持简洁温暖，像朋友一样说话，但保持专业秘书的分寸。\n\n"
                f"{structured_info}\n\n用户意图: {intent}"
            )},
            {"role": "user", "content": state.get("user_input", "")},
        ], temperature=0.7, max_tokens=1024)
    elif structured_info:
        final_reply = f"{structured_info}"
    else:
        final_reply = await mock_chat(state.get("user_input", ""))

    return {"final_reply": final_reply, "error": None}


# ============ 路由函数 ============

def should_use_tools(state: AgentState) -> Literal["tools_executor", "reply"]:
    """判断是否需要执行工具"""
    sub_tasks = state.get("sub_tasks", [])
    if sub_tasks:
        return "tools_executor"
    return "reply"


def should_check_conflicts(state: AgentState) -> Literal["conflict_check", "coordinator"]:
    """判断是否需要冲突检测"""
    tasks_created = state.get("tasks_created", [])
    if tasks_created:
        return "conflict_check"
    return "coordinator"


def has_conflicts(state: AgentState) -> Literal["coordinator", "reply"]:
    """判断是否有冲突需要协调"""
    conflicts = state.get("conflicts_found", [])
    if conflicts:
        return "coordinator"
    return "reply"


# ============ 构建状态图 ============

def build_agent_graph() -> StateGraph:
    """构建并编译 Agent 状态图"""
    workflow = StateGraph(AgentState)

    # 添加节点
    workflow.add_node("planner", planner_node)
    workflow.add_node("tools_executor", tools_executor_node)
    workflow.add_node("conflict_check", conflict_check_node)
    workflow.add_node("coordinator", coordinator_node)
    workflow.add_node("reply", reply_node)

    # 设置入口
    workflow.set_entry_point("planner")

    # Planner → Tools 或 Reply
    workflow.add_conditional_edges(
        "planner",
        should_use_tools,
        {"tools_executor": "tools_executor", "reply": "reply"},
    )

    # Tools → Conflict Check 或 Coordinator
    workflow.add_conditional_edges(
        "tools_executor",
        should_check_conflicts,
        {"conflict_check": "conflict_check", "coordinator": "coordinator"},
    )

    # Conflict Check → Coordinator 或 Reply
    workflow.add_conditional_edges(
        "conflict_check",
        has_conflicts,
        {"coordinator": "coordinator", "reply": "reply"},
    )

    # Coordinator → Reply
    workflow.add_edge("coordinator", "reply")

    # Reply → END
    workflow.add_edge("reply", END)

    return workflow.compile()


# 全局编译好的图实例（懒加载）
_agent_graph = None


def get_agent_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
    return _agent_graph
