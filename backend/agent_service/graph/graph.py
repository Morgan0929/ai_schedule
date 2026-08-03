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
from agent_service.graph.validator import validator_node
from agent_service.graph.tools import execute_tool
from agent_service.utils.coordinator import coordinator_node
from agent_service.llm.deepseek_client import chat_completion, is_llm_available
from agent_service.llm.mock_agent import mock_chat


# ============ 各节点实现 ============

async def tools_executor_node(state: AgentState) -> dict[str, Any]:
    """
    工具执行节点 — 含 Middleware: Tool Call Limit + Tool Retry
    """
    from agent_service.middleware.limits import ToolCallLimiter, MAX_TOOL_CALLS
    from agent_service.middleware.retry import with_retry

    sub_tasks = state.get("sub_tasks", [])
    user_id = state.get("user_id", 0)
    call_count = state.get("tool_calls_count", 0)

    if not sub_tasks:
        return {"calendar_events": [], "external_data": {}, "tasks_created": [], "error": None}

    limiter = ToolCallLimiter()
    limiter.count = call_count  # 恢复当前计数

    calendar_events = []
    external_data = {}
    tasks_created = []
    actions_taken = []

    for task in sub_tasks:
        # === Middleware: Tool Call Limit ===
        if not limiter.allow():
            actions_taken.append(
                f"[LIMIT] 已达最大工具调用次数({MAX_TOOL_CALLS})，跳过后面的操作"
            )
            break

        action = task.get("action", "")
        params = task.get("params", {})

        # === Middleware: Tool Retry (with_retry 包装) ===
        @with_retry(max_attempts=2, base_delay=1.0)
        async def _call_with_retry():
            return await execute_tool(action, params, user_id)

        result = await _call_with_retry()
        limiter.record(action)

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
        "tool_calls_count": limiter.count,
        "_tool_history": limiter.history,
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
    """回复生成节点"""
    # Confidence Gate: 需要确认时直接返回
    if state.get("_needs_confirmation"):
        msg = state.get("_confirm_message", "你是想安排一项日程，还是查询已有安排？")
        return {"final_reply": msg}

    intent = state.get("intent", "CHAT")
    user_input = state.get("user_input", "")
    actions = state.get("actions_taken", [])
    tasks_created = state.get("tasks_created", [])
    conflicts = state.get("conflicts_found", [])
    calendar_events = state.get("calendar_events", [])
    suggestions = state.get("suggestions", [])
    external_data = state.get("external_data", {})

    # 构建结构化摘要
    summary_parts = []
    if actions:
        summary_parts.append("已执行操作:\n" + "\n".join(f"  • {a}" for a in actions))
    # 天气数据
    weather = external_data.get("weather", {})
    if weather and weather.get("source") in ("mcp", "realtime"):
        temp = weather.get("temp_c", "")
        desc = weather.get("desc", "") or weather.get("weather_desc", "")
        hum = weather.get("humidity", "")
        city = weather.get("city", "")
        summary_parts.append(f"天气: {city} {temp}°C {desc} 湿度{hum}%")
    if calendar_events:
        lines = [f"日程 ({len(calendar_events)}个):"]
        for ev in calendar_events[:10]:
            title = ev.get("title", "?")
            st = ev.get("start_time", "")[:16]
            lines.append(f"  - {st} {title}")
        summary_parts.append("\n".join(lines))
    if conflicts:
        summary_parts.append(f"⚠️ 发现 {len(conflicts)} 个时间冲突")
        for c in conflicts:
            summary_parts.append(f"  • {c.get('reason', '')}")
    if suggestions:
        summary_parts.append("💡 建议方案:")
        for s in suggestions:
            tag = "⭐推荐" if s.get("is_recommended") else "   "
            summary_parts.append(f"  [{s.get('plan_id', '?')}] {tag} {s.get('title', '')}")

    # 保存结构化信息到 state 供 streaming reply 使用
    state["_structured_info"] = "\n\n".join(summary_parts) if summary_parts else ""
    state["_intent"] = intent

    structured_info = state["_structured_info"]
    if is_llm_available() and structured_info:
        from agent_service.llm.prompts import reply_prompt
        prompt_value = reply_prompt.invoke({
            "structured_info": structured_info,
            "intent": intent,
            "user_input": state.get("user_input", ""),
        })
        msgs = prompt_value.to_messages()
        final_reply = await chat_completion([
            {"role": "system" if msgs[0].type == "system" else msgs[0].type, "content": msgs[0].content},
            {"role": "user", "content": msgs[1].content},
        ], temperature=0.7, max_tokens=1024)
    elif structured_info:
        final_reply = f"{structured_info}"
    elif intent.lower() == "chat" and is_llm_available():
        # 无关事务 → 用林的 System Prompt 生成拒绝回复
        from agent_service.llm.prompts import LIN_SYSTEM_PROMPT, reply_prompt
        reject_prompt = reply_prompt.invoke({
            "structured_info": "用户提出了与个人事务管理无关的请求。请礼貌地拒绝，并说明你的职责范围。",
            "intent": "CHAT",
            "user_input": user_input,
        })
        msgs = reject_prompt.to_messages()
        final_reply = await chat_completion([
            {"role": "system", "content": msgs[0].content},
            {"role": "user", "content": msgs[1].content},
        ], temperature=0.7, max_tokens=512)
    else:
        final_reply = await mock_chat(user_input)

    # === Middleware: Todo Extraction (跳过拒绝/chat场景) ===
    if intent.lower() != "chat":
        from agent_service.middleware.todo_extractor import TodoExtractor
        todos = await TodoExtractor.extract(user_input)
    else:
        todos = []
    if todos:
        # 追加待办提示
        todo_text = "\n\n📋 自动识别到的待办:\n" + "\n".join(
            f"  • {t['task']}" + (f" (截止: {t['deadline']})" if t.get('deadline') else "")
            for t in todos[:5]
        )
        final_reply = (final_reply or "") + todo_text

    return {"final_reply": final_reply, "error": None}


# ============ 路由函数 ============

def _needs_confirmation(state: AgentState) -> Literal["reply", "tools_executor"]:
    """Validator → Reply (需确认) 或 Tools Executor (通过)"""
    if state.get("_needs_confirmation"):
        print("[DIAG-2] Validator: NEEDS CONFIRMATION → reply")
        return "reply"
    # === DIAG: 2. Validator 通过后的 state ===
    import json
    print("[DIAG-2] Validator PASSED, sub_tasks:", json.dumps(
        state.get("sub_tasks", []), ensure_ascii=False, default=str)[:500])
    return "tools_executor"


def should_use_tools(state: AgentState) -> Literal["tools_executor", "reply"]:
    """判断是否需要执行工具"""
    sub_tasks = state.get("sub_tasks", [])
    # === DIAG: 3. Router 输入 ===
    import json
    print("[DIAG-3] Router input:", json.dumps({
        "intent": state.get("intent"), "sub_tasks": sub_tasks,
    }, ensure_ascii=False, default=str)[:300])
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
    workflow.add_node("validator", validator_node)
    workflow.add_node("tools_executor", tools_executor_node)
    workflow.add_node("conflict_check", conflict_check_node)
    workflow.add_node("coordinator", coordinator_node)
    workflow.add_node("reply", reply_node)

    # 设置入口
    workflow.set_entry_point("planner")

    # Planner → Validator
    workflow.add_edge("planner", "validator")

    # Validator → Tools (确认通过) 或 Reply (需要确认/有问题)
    workflow.add_conditional_edges(
        "validator",
        _needs_confirmation,
        {"reply": "reply", "tools_executor": "tools_executor"},
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


# ============ Streaming Reply ============

async def stream_reply(state: AgentState):
    """
    流式生成林的回复 — async generator, 逐 token yield

    用法:
        async for token in stream_reply(state):
            yield f"data: {token}\n\n"  # SSE 格式
    """
    structured_info = state.get("_structured_info", "")
    intent = state.get("_intent", state.get("intent", "CHAT"))
    user_input = state.get("user_input", "")

    if structured_info:
        from agent_service.llm.prompts import reply_prompt
        from agent_service.llm.deepseek_client import astream_chat, is_llm_available

        if is_llm_available():
            prompt_value = reply_prompt.invoke({
                "structured_info": structured_info,
                "intent": intent,
                "user_input": user_input,
            })
            msgs = prompt_value.to_messages()
            messages = [
                {"role": "system", "content": msgs[0].content},
                {"role": "user", "content": msgs[1].content},
            ]
            async for token in astream_chat(messages, temperature=0.7, max_tokens=1024):
                yield token
            return

        # Fallback: mock 逐字输出
        for char in structured_info:
            yield char
            import asyncio
            await asyncio.sleep(0.02)
    else:
        from agent_service.llm.mock_agent import mock_chat
        text = await mock_chat(user_input)
        for char in text:
            yield char
            import asyncio
            await asyncio.sleep(0.02)


# 全局编译好的图实例（懒加载）
_agent_graph = None


def get_agent_graph():
    global _agent_graph
    if _agent_graph is None:
        _agent_graph = build_agent_graph()
    return _agent_graph
