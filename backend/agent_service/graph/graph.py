"""
LangGraph 状态图 — Agent 完整工作流

新架构:
    START → check_pending_action
               ↓
        pending? → YES → conflict_resolver → tools_executor
                   ↓ NO
        event_detector (规则引擎优先, 日程类不浪费LLM)
                   ↓
        high_confidence? → YES → tools_executor (跳过planner)
                         ↓ NO
        planner → state_inspector → entity_normalizer → validator
                   ↓
        tools_executor | reply (via validator)

后段不变:
    tools_executor → conflict_check → coordinator → reply → END
"""
import asyncio
import json
from datetime import date
from typing import Any, Literal
from langgraph.graph import StateGraph, END
from langchain_core.messages import HumanMessage, AIMessage

from agent_service.graph.state import AgentState
from agent_service.graph.planner import planner_node
from agent_service.graph.event_detector import event_detector_node
from agent_service.graph.conflict_resolver import conflict_resolver_node
from agent_service.graph.state_inspector import state_inspector_node
from agent_service.graph.entity_normalizer import entity_normalizer_node
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
    import json
    sub_tasks = state.get("sub_tasks", [])
    print(f"[TOOLS] enter intent={state.get('intent')} n={len(sub_tasks)}")
    from agent_service.middleware.limits import ToolCallLimiter, MAX_TOOL_CALLS
    from agent_service.middleware.retry import with_retry

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
    conflicts_found = []

    for task in sub_tasks:
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
                elif isinstance(tool_result, dict) and tool_result.get("conflict_level") == "SOFT":
                    # SOFT冲突: 允许创建, 但显示临近日程
                    tasks_created.append(tool_result.get("id", 0))
                    near = tool_result.get("conflicts", [])
                    for n in near:
                        actions_taken.append(
                            f"提醒: {n.get('task_a','')}在{n.get('task_a_time','')}, "
                            f"与{n.get('task_b','')}相距不到30分钟"
                        )
                    actions_taken.append(f"创建任务「{tool_result.get('title', '')}」")
                elif isinstance(tool_result, dict) and tool_result.get("conflicts"):
                    conflicts_found.extend(tool_result["conflicts"])
            elif action in ("update_task", "update_task_tool"):
                # 从 tool_result 提取, fallback 到 params
                title = params.get('title', '')
                new_time = ''
                if isinstance(tool_result, dict):
                    title = tool_result.get('title', title)
                    new_time = tool_result.get('new_time', tool_result.get('start_time', ''))
                if not new_time:
                    new_time = params.get('new_time', '')
                # 从 tool_result 提取 id, fallback 用 params
                task_id = 0
                if isinstance(tool_result, dict):
                    task_id = tool_result.get("id", 0)
                if title and new_time:
                    actions_taken.append(f"已将「{title}」调整到 {new_time[:16]}")
                    if "updated_tasks" not in state:
                        state["updated_tasks"] = []
                    state["updated_tasks"].append({
                        "id": task_id, "title": title, "new_time": new_time,
                    })
                elif title:
                    actions_taken.append(f"已更新任务「{title}」")
                    if "updated_tasks" not in state:
                        state["updated_tasks"] = []
                    state["updated_tasks"].append({
                        "id": task_id, "title": title, "new_time": new_time,
                    })
                else:
                    actions_taken.append("已更新任务")
            elif action == "delete_task":
                title = tool_result.get("title", params.get("title", "")) if isinstance(tool_result, dict) else ""
                status = tool_result.get("status", "") if isinstance(tool_result, dict) else ""
                if status == "deleted":
                    actions_taken.append(f"已删除任务「{title or tool_result.get('task_id', '')}」")
                elif status == "ambiguous":
                    actions_taken.append(f"找到多个「{title or params.get('title', '')}」，请指定具体时间")
                else:
                    actions_taken.append(f"未找到任务「{title or params.get('title', '')}」")
            elif action == "reschedule_pending":
                if isinstance(tool_result, dict) and tool_result.get("ref_id"):
                    actions_taken.append(
                        f"已将「{tool_result.get('title', '')}」调整为 {tool_result.get('start_time', '')[:16]}")
            elif action == "commit_pending":
                if isinstance(tool_result, dict) and tool_result.get("id"):
                    tasks_created.append(tool_result["id"])
                    actions_taken.append(f"创建任务「{tool_result.get('title', '')}」")
                elif isinstance(tool_result, dict):
                    actions_taken.append(f"已处理「{tool_result.get('title', params.get('title', ''))}」")
            elif action == "create_pending":
                if isinstance(tool_result, dict):
                    if tool_result.get("id"):
                        # auto-commit 成功
                        tasks_created.append(tool_result["id"])
                        actions_taken.append(f"创建任务「{tool_result.get('title', '')}」")
                    elif tool_result.get("pending_task"):
                        # 有冲突, 保存 PendingTask
                        pending = tool_result["pending_task"]
                        if "pending_tasks" not in state:
                            state["pending_tasks"] = []
                        state["pending_tasks"].append(pending)
                        actions_taken.append(
                            f"待确认: 「{pending.get('title', '')}」"
                            f"与已有任务时间冲突, 请选择方案")
            elif action == "save_pending_todo":
                if isinstance(tool_result, dict) and tool_result.get("ref_id"):
                    actions_taken.append(f"待办「{tool_result.get('title', '')}」已记录")
                    if tool_result.get("committed"):
                        tasks_created.append(tool_result.get("id", 0))
                elif isinstance(tool_result, dict):
                    actions_taken.append(f"待办已记录: {tool_result.get('title', '?')}")
            elif action in ("create_todo", "create_todo_tool"):
                # LLM fallback / 明确有时间的 todo → 直接写 PG
                if isinstance(tool_result, dict) and tool_result.get("id"):
                    tasks_created.append(tool_result["id"])
                    actions_taken.append(f"待办「{tool_result.get('title', '')}」已创建")
            elif action == "list_todos":
                if isinstance(tool_result, list):
                    external_data["todos"] = tool_result
            elif action == "query_weather":
                external_data["weather"] = tool_result
                print(f"[TOOLS] WEATHER RESULT: {json.dumps(tool_result, ensure_ascii=False, default=str)[:300]}")

        # ── Fallback: update_task 工具失败时仍产出可消费的输出 ──
        if not result.get("success") and action in ("update_task", "update_task_tool"):
            title = params.get('title', '')
            new_time = params.get('new_time', '')
            if title and new_time:
                actions_taken.append(f"已将「{title}」调整到 {new_time[:16]}")
                if "updated_tasks" not in state:
                    state["updated_tasks"] = []
                state["updated_tasks"].append({
                    "id": 0, "title": title, "new_time": new_time,
                })
            elif title:
                actions_taken.append(f"已更新任务「{title}」")

    result = {
        "calendar_events": calendar_events,
        "schedule_found": bool(calendar_events),
        "external_data": external_data,
        "tasks_created": tasks_created,
        "tasks_updated": state.get("updated_tasks", []),
        "pending_tasks": state.get("pending_tasks", []),
        "_pending_event": state.get("_pending_event"),
        "actions_taken": actions_taken,
        "conflicts_found": conflicts_found,
        "conflict_count": len(conflicts_found),
        "tool_calls_count": limiter.count,
        "_tool_history": limiter.history,
        "error": None,
    }
    print(f"[TOOLS] done actions={len(actions_taken)} conflicts={len(conflicts_found)} created={len(tasks_created)}")
    return result


async def pending_conflict_detector_node(state: AgentState) -> dict[str, Any]:
    """
    Step 3: _pending_event vs calendar_events 时间重叠检测.

    自己检测冲突，不依赖 create_pending_tool。
    有冲突 → 创建 Redis PendingTask → conflicts_found → coordinator
    无冲突 → 创建 Redis PendingTask → commit_pending → reply
    """
    pending_event = state.get("_pending_event")
    if not pending_event or not pending_event.get("title"):
        return {}
    time_type = pending_event.get("type", "UNKNOWN")

    # 非 POINT → 不检测 / 仅提示
    if time_type != "POINT":
        if time_type == "RANGE":
            # 时段级: 创建 PendingTask + 软提示
            from agent_service.graph.pending_task import create_pending, save_pending, pending_task_ref
            pending = create_pending(pending_event["title"],
                                     pending_event.get("reference_date", "") + "T00:00:00")
            await save_pending(pending)
            ptasks = state.get("pending_tasks", [])
            ptasks.append(pending_task_ref(pending))
            return {
                "conflicts_found": [],
                "conflict_count": 0,
                "pending_tasks": ptasks,
                "_pending_event": None,
                "_soft_warning": f"「{pending_event['title']}」时间未确定，暂未检测冲突。",
                "error": None,
            }
        # day/week/month → 不检测
        return {"_pending_event": None, "error": None}

    user_id = state.get("user_id", 0)
    calendar_events = state.get("calendar_events", [])
    from agent_service.graph.pending_task import (
        create_pending, save_pending, commit_pending,
        db_task_ref, pending_task_ref,
    )
    from datetime import datetime

    # ── 创建 PendingTask (只管 Redis, 不管冲突) ──
    pending = create_pending(
        pending_event["title"],
        pending_event.get("start_time", ""),
        pending_event.get("end_time", ""),
    )

    # ── 检测时间重叠 ──
    try:
        p_start = datetime.fromisoformat(pending["start_time"])
        p_end = datetime.fromisoformat(pending.get("end_time", pending["start_time"]))
    except (ValueError, TypeError):
        p_start = datetime.now()
        p_end = p_start

    conflicts = []
    for ev in calendar_events:
        ev_start_str = ev.get("start_time", "")
        ev_end_str = ev.get("end_time", "")
        if not ev_start_str:
            continue
        try:
            ev_start = datetime.fromisoformat(ev_start_str)
            ev_end = datetime.fromisoformat(ev_end_str) if ev_end_str else ev_start
        except (ValueError, TypeError):
            continue
        # 重叠: pending.start < existing.end AND pending.end > existing.start
        if p_start < ev_end and p_end > ev_start:
            conflicts.append({
                "existing_task": db_task_ref(
                    ev.get("id", 0), ev.get("title", "?"),
                    ev_start_str[:16]),
                "pending_ref": pending["ref_id"],
                "pending_task": pending_task_ref(pending),
                "level": "HARD",
            })

    if conflicts:
        await save_pending(pending)
        ptasks = state.get("pending_tasks", [])
        ptasks.append(pending_task_ref(pending))
        return {
            "conflicts_found": conflicts,
            "conflict_count": len(conflicts),
            "pending_tasks": ptasks,
            "_pending_event": None,
            "error": None,
        }

    # ── 无冲突 → 直接写入数据库, 避免 Redis PendingTask 往返拖慢规则路径 ──
    try:
        from common.database import async_session_factory
        from timeline_service.models.task_model import TaskModel
        from timeline_service.repository.task_repo import TaskRepository

        async with async_session_factory() as db:
            task = await TaskRepository(db).create(TaskModel(
                user_id=user_id,
                title=pending["title"],
                start_time=datetime.fromisoformat(pending["start_time"]),
                end_time=datetime.fromisoformat(pending.get("end_time", pending["start_time"])),
                priority="MEDIUM",
                status="PENDING",
                location="",
                category="PERSONAL",
                tags=[],
                extra_data={},
            ))
            await db.commit()
        title = pending["title"]
        t = pending.get("start_time", "")[:16]
        return {
            "conflicts_found": [],
            "conflict_count": 0,
            "tasks_created": state.get("tasks_created", []) + [task.id],
            "actions_taken": state.get("actions_taken", []) + [
                f"已记录「{title}」\n时间：{t}"],
            "_pending_event": None,
            "error": None,
        }
    except Exception as exc:
        return {
            "conflicts_found": [],
            "conflict_count": 0,
            "_pending_event": None,
            "error": str(exc),
        }
    return {
        "conflicts_found": [],
        "conflict_count": 0,
        "_pending_event": None,
        "error": None,
    }


async def conflict_check_node(state: AgentState) -> dict[str, Any]:
    """
    冲突检测节点: 检查已有任务之间的冲突 (纯 DB 查询).
    _pending_event 的处理已移至 pending_conflict_detector.
    """
    from timeline_service.utils.conflict_detector import ConflictDetector, DetectedConflict
    from timeline_service.repository.task_repo import TaskRepository
    from common.database import async_session_factory

    user_id = state.get("user_id", 0)
    calendar_events = state.get("calendar_events", [])
    task_mutations = bool(state.get("tasks_created", [])) or bool(state.get("tasks_updated", []))

    existing_conflicts = state.get("conflicts_found", [])
    if not calendar_events and not existing_conflicts and not task_mutations:
        return {"conflicts_found": [], "conflict_count": 0, "error": None}

    async with async_session_factory() as db:
        repo = TaskRepository(db)
        from datetime import datetime, timedelta
        now = datetime.now()
        tasks = await repo.find_by_user_time_range(user_id, now - timedelta(days=1), now + timedelta(days=30))

    if len(tasks) < 2:
        return {"conflicts_found": existing_conflicts, "conflict_count": len(existing_conflicts), "error": None}

    detector = ConflictDetector()
    report = detector.detect(list(tasks))

    from agent_service.graph.pending_task import db_task_ref
    conflicts = []
    for c in report.conflicts:
        conflicts.append({
            "existing_task": db_task_ref(c.task_a_id, c.task_a_title,
                                         str(c.overlap_start)[:16] if c.overlap_start else ""),
            "new_task": db_task_ref(c.task_b_id, c.task_b_title,
                                    str(c.overlap_start)[:16] if c.overlap_start else ""),
            "severity": c.severity.value if hasattr(c.severity, 'value') else c.severity,
            "reason": c.reason,
        })

    return {"conflicts_found": conflicts, "conflict_count": len(conflicts), "error": None}


def _build_schedule_reply(calendar_events: list, pending_tasks: list,
                          query_date: str = "该时间") -> dict:
    """合并任务、课程和 pending 展示，保持秘书式简洁口吻。"""
    has_events = bool(calendar_events)
    has_pending = bool(pending_tasks)
    lines = []

    if has_events:
        lines.append(f"我帮你看了下，{query_date}一共有 {len(calendar_events)} 项安排：")
        event_dates = {
            str(ev.get('start_time', ''))[:10]
            for ev in calendar_events
            if ev.get('start_time')
        }
        show_date = len(event_dates) > 1
        for ev in calendar_events[:10]:
            time_str = _format_datetime(
                ev.get('start_time', ''), include_date=show_date,
            )
            title = ev.get('title', '?')
            if ev.get('source') == 'course':
                section = ev.get('section_label') or ''
                prefix = f"课程｜{section} " if section else "课程｜"
                title = f"{prefix}{title}"
            location = ev.get('location') or ''
            suffix = f"（{location}）" if location else ''
            lines.append(f"  {time_str} {title}{suffix}")
    else:
        lines.append(f"我帮你看了下，{query_date}暂时没有安排。")

    if has_pending:
        lines.append("")
        lines.append("另外，还有待确认的安排：")
        for pt in pending_tasks:
            time_str = _format_datetime(pt.get('start_time', pt.get('time', '')))
            lines.append(f"  {time_str} {pt.get('title', '?')}（未保存）")

    return {"final_reply": "\n".join(lines)}


def _extract_query_label(text: str, time_range: dict | None = None) -> str:
    """从用户原话提取查询标签, 避免回复层把所有空日程都说成明天。"""
    import re
    text = (text or "").strip()
    numeric_date = re.search(r'(?:月底)?(?:(\d{1,2})\s*月\s*)?(\d{1,2})\s*[号日]', text)
    if numeric_date:
        month = numeric_date.group(1)
        day = numeric_date.group(2)
        if '月底' in text and not month:
            return f"月底{int(day)}号"
        return f"{int(month)}月{int(day)}日" if month else f"{int(day)}号"
    ordered_patterns = [
        r"下周[一二三四五六日]", r"这周[一二三四五六日]", r"本周[一二三四五六日]",
        r"周[一二三四五六日]", r"星期[一二三四五六日]",
        r"今天", r"明天", r"后天", r"下周", r"这周", r"本周",
        r"下个月", r"月底", r"月末",
        r"上午", r"早上", r"早晨", r"中午", r"下午", r"傍晚", r"晚上",
    ]
    for pattern in ordered_patterns:
        m = re.search(pattern, text)
        if m:
            return m.group(0)

    start = (time_range or {}).get("start", "")
    if start:
        try:
            from datetime import datetime
            dt = datetime.fromisoformat(start)
            return f"{dt.month}月{dt.day}日"
        except Exception:
            pass
    return "该时间"


def _format_datetime(value: Any, include_date: bool = False) -> str:
    """把内部 ISO 时间转换成面向用户的中文短格式。"""
    raw = str(value or "")
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(raw.replace("Z", "+00:00"))
        time_text = f"{dt.hour:02d}:{dt.minute:02d}"
        return f"{dt.month}月{dt.day}日 {time_text}" if include_date else time_text
    except (TypeError, ValueError):
        return raw[:16] if raw else "时间待定"


def _format_date(value: Any) -> str:
    raw = str(value or "")[:10]
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(raw)
        return f"{dt.month}月{dt.day}日"
    except (TypeError, ValueError):
        return raw


def _weather_label(value: Any) -> str:
    """将天气服务常见英文描述统一成中文，未知值保留原文。"""
    text = str(value or "").strip()
    labels = {
        "partly cloudy": "局部多云",
        "mostly cloudy": "多云",
        "overcast": "阴",
        "sunny": "晴",
        "clear": "晴",
        "cloudy": "多云",
        "rain": "有雨",
        "light rain": "小雨",
        "moderate rain": "中雨",
        "heavy rain": "大雨",
        "thunderstorm": "雷雨",
        "snow": "有雪",
        "fog": "雾",
        "mist": "雾",
    }
    return labels.get(text.lower(), "天气状况待确认" if text else "天气状况待确认")


def _is_greeting(text: str) -> bool:
    """Recognize short greetings that should not be treated as out-of-scope requests."""
    normalized = (text or "").strip().lower().strip("，,。.！!？?～~ ")
    return normalized in {"你好", "您好", "嗨", "哈喽", "hello", "hi", "在吗"}


async def _load_llm_context(user_id: int) -> tuple[str, str]:
    """只在需要走 LLM 时加载画像和近期摘要。"""
    from agent_service.memory.profile import ProfileManager
    from agent_service.memory.summarizer import SummaryNode

    profile_task = ProfileManager.get_context_text(user_id)
    summary_task = SummaryNode.load_recent(user_id, days=7)
    profile_text, recent_summary = await asyncio.gather(profile_task, summary_task)
    return profile_text, recent_summary


async def reply_node(state: AgentState) -> dict[str, Any]:
    """
    回复生成节点

    优先级: 执行结果 > 创建 > 更新 > 冲突 > 查询 > 空/chat
    不根据 intent 判断, 根据实际 state 中的执行结果
    """
    print(f"[REPLY] intent={state.get('intent')} actions={len(state.get('actions_taken',[]))} conflicts={len(state.get('conflicts_found',[]))}")
    if state.get("final_reply"):
        return {"final_reply": state["final_reply"], "error": state.get("error")}

    external_data = state.get("external_data", {})
    weather = external_data.get("weather", {})
    if weather:
        print(f"[REPLY] weather={json.dumps(weather, ensure_ascii=False, default=str)[:200]}")
    else:
        print(f"[REPLY] no weather in external_data keys={list(external_data.keys()) if external_data else 'empty'}")

    # Confidence Gate
    if state.get("needs_confirmation"):
        return {"final_reply": state.get("_confirm_message", "你是想安排一项日程，还是查询已有安排？")}

    intent = state.get("intent", "")
    actions = state.get("actions_taken", [])
    tasks_created = state.get("tasks_created", [])
    conflicts = state.get("conflicts_found", [])
    suggestions = state.get("suggestions", [])
    calendar_events = state.get("calendar_events", [])
    pending_tasks = state.get("pending_tasks", [])
    exec_ctx = state.get("execution_context", {})
    user_input = state.get("user_input", "")
    external_data = state.get("external_data", {})

    # ═══ intent 分流 ═══
    if intent == "chat" and _is_greeting(user_input):
        return {"final_reply": "你好，我是林。日程、课程和提醒交给我就好。"}

    if intent == "create_todo":
        if actions:
            return {"final_reply": "好的，我已经处理好了：\n" + "\n".join(f"  • {a}" for a in actions)}
        # 从 sub_tasks params 取标题
        sub_tasks = state.get("sub_tasks", [])
        title = "待办"
        for st in sub_tasks:
            if st.get("action") in ("save_pending_todo", "create_todo"):
                title = st.get("params", {}).get("title", title)
                break
        return {"final_reply": f"好的，我已经记下待办「{title}」了。\n之后补充时间或详情时，直接告诉我就好。"}

    if intent == "query_weather":
        wr = external_data.get("weather", {})
        if wr and wr.get("weather"):
            w = wr["weather"]
            city = wr.get("city", "?")
            qd = _format_date(wr.get("query_date", ""))
            desc = _weather_label(w.get('desc', ''))
            return {"final_reply":
                f"我帮你看了下，{city} {qd} 的天气是：\n"
                f"  {w.get('temp_min','?')}~{w.get('temp_max','?')}°C  {desc}\n"
                f"  湿度 {w.get('humidity','?')}%"}
        return {"final_reply": "我暂时没有查到天气信息，稍后再帮你看。"}

    if intent in ("query_schedule", "query_calendar"):
        query_label = state.get("query_date_label") or _extract_query_label(user_input)
        return _build_schedule_reply(calendar_events, pending_tasks, query_label)

    if intent == "query_todos":
        todos = external_data.get("todos", [])
        if not todos:
            return {"final_reply": "我看了下，目前没有待办。"}
        lines = ["我看了下，当前待办有这些："]
        for todo in todos[:10]:
            note = todo.get("note") or ""
            suffix = f"（{note}）" if note else ""
            lines.append(f"  {todo.get('title', '?')}{suffix}")
        return {"final_reply": "\n".join(lines)}

    if intent == "create_event" and not actions and not tasks_created and not conflicts:
        return {"final_reply": "这项日程还没有成功记下，我再试一次。", "error": state.get("error")}

    # RANGE 事件 → 反问用户
    pending_event = state.get("_pending_event") or {}
    if pending_event.get("type") == "RANGE" and not actions:
        msg = f"好的，我先记下「{pending_event.get('title', '')}」了。\n具体时间确定后告诉我一声，我再帮你补上。"
        soft = state.get("_soft_warning", "")
        if soft:
            msg += f"\n\n💡 {soft}"
        return {"final_reply": msg}

    # A newly detected conflict must be resolved before reporting an earlier mutation as complete.
    if conflicts and suggestions:
        parts = ["我帮你看了一下，发现有时间冲突：", ""]
        for c in conflicts:
            ext = c.get("existing_task", {})
            new = c.get("pending_task", c.get("new_task", {}))
            ext_title = ext.get("title") or c.get("task_a", "?")
            ext_time = ext.get("time") or c.get("task_a_time", "")
            new_title = new.get("title") or c.get("task_b", "?")
            new_time = new.get("start_time", new.get("time", "")) or c.get("task_b_time", "")
            parts.append(f"已有：{ext_title} {_format_datetime(ext_time, include_date=True)}")
            parts.append(f"新的：{new_title} {_format_datetime(new_time, include_date=True)}")
            parts.append("")
        parts.append("你可以选一个处理方式：")
        for s in suggestions:
            parts.append(f"  [{s.get('plan_id','?')}] {s.get('title','')}")
        return {"final_reply": "\n".join(parts)}

    # ═══ 1. 有执行结果 (actions_taken) → 直接展示 ═══
    if actions:
        lines = []
        # 如果有 execution_context, 用林的口吻包装
        if exec_ctx and exec_ctx.get('reason') == 'conflict_resolution':
            lines.append("好的，调整已经完成：")
            for a in actions:
                lines.append(f"  ✅ {a}")
        else:
            for a in actions:
                lines.append(f"  • {a}")
        return {"final_reply": "\n".join(lines)}

    # ═══ 2. 有冲突+方案 (等待用户选择) ═══
    if conflicts and suggestions:
        parts = ["我帮你看了一下，发现有时间冲突：", ""]
        for c in conflicts:
            ext = c.get("existing_task", {})
            new = c.get("pending_task", c.get("new_task", {}))
            # 兼容旧格式
            ext_title = ext.get("title") or c.get("task_a", "?")
            ext_time = ext.get("time") or c.get("task_a_time", "")
            new_title = new.get("title") or c.get("task_b", "?")
            new_time = new.get("start_time", new.get("time", "")) or c.get("task_b_time", "")
            parts.append(f"已有：{ext_title} {_format_datetime(ext_time, include_date=True)}")
            parts.append(f"新的：{new_title} {_format_datetime(new_time, include_date=True)}")
            parts.append("")
        parts.append("你可以选一个处理方式：")
        for s in suggestions:
            parts.append(f"  [{s.get('plan_id','?')}] {s.get('title','')}")
        return {"final_reply": "\n".join(parts)}

    # ═══ 3. 查询结果 (已在 intent 分流处理, 此处兜底) ═══
    if calendar_events and not pending_tasks:
        lines = ["日程安排:"]
        for ev in calendar_events[:10]:
            lines.append(f"  {_format_datetime(ev.get('start_time',''), include_date=True)} {ev.get('title','?')}")
        return {"final_reply": "\n".join(lines)}

    # ═══ 4. 结构化摘要 (天气等) ═══
    summary_parts = []
    weather_result = external_data.get("weather", {})
    if weather_result and weather_result.get("weather"):
        w = weather_result["weather"]
        city = weather_result.get("city", "")
        qd = _format_date(weather_result.get("query_date", ""))
        parts = [f"天气: {city}"]
        if qd:
            parts[0] += f" ({qd})"
        parts[0] += f" {w.get('temp_min','')}~{w.get('temp_max','')}°C"
        if w.get("desc"):
            parts[0] += f" {_weather_label(w['desc'])}"
        if w.get("humidity"):
            parts[0] += f" 湿度{w['humidity']}%"
        summary_parts.append("".join(parts))
    elif weather_result and weather_result.get("error"):
        summary_parts.append(f"天气查询失败: {weather_result['error']}")
    if calendar_events and not summary_parts:
        lines = [f"日程 ({len(calendar_events)}个):"]
        for ev in calendar_events[:10]:
            lines.append(f"  - {_format_datetime(ev.get('start_time',''), include_date=True)} {ev.get('title','?')}")
        summary_parts.append("\n".join(lines))

    state["_structured_info"] = "\n\n".join(summary_parts) if summary_parts else ""
    state["_intent"] = intent

    structured_info = state["_structured_info"]
    if structured_info:
        # 已经是结构化结果时，优先用模板直出，避免再等一次 LLM。
        return {"final_reply": structured_info, "error": None}

    if is_llm_available() and structured_info:
        from agent_service.llm.prompts import reply_prompt
        prompt_value = reply_prompt.invoke({
            "structured_info": structured_info,
            "intent": intent,
            "user_input": user_input,
        })
        msgs = prompt_value.to_messages()
        final_reply = await chat_completion([
            {"role": "system" if msgs[0].type == "system" else msgs[0].type, "content": msgs[0].content},
            {"role": "user", "content": msgs[1].content},
        ], temperature=0.7, max_tokens=1024)
    elif is_llm_available():
        from agent_service.llm.prompts import reply_prompt
        profile_text, recent_summary = await _load_llm_context(state.get("user_id", 0))
        context_lines = ["用户提出了与个人事务管理无关的请求。请礼貌地拒绝。"]
        if profile_text:
            context_lines.append(profile_text)
        if recent_summary:
            context_lines.append(recent_summary)
        reject_prompt = reply_prompt.invoke({
            "structured_info": "\n\n".join(context_lines),
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

    if intent.lower() != "chat":
        from agent_service.middleware.todo_extractor import TodoExtractor
        todos = await TodoExtractor.extract(user_input)
        if todos:
            todo_text = "\n\n📋 自动识别到的待办:\n" + "\n".join(
                f"  • {t['task']}" + (f" (截止: {t['deadline']})" if t.get('deadline') else "")
                for t in todos[:5]
            )
            final_reply = (final_reply or "") + todo_text

    # ── 有未完成冲突时提醒 ──
    if state.get("_pending_conflict_warning"):
        ctx = state.get("_pending_conflict_context", {})
        pending_note = (
            f"\n\n💡 提示：你还有一个未完成的冲突调整"
            f"（{ctx.get('summary', '')}）。\n"
            f"回复「确认」继续处理冲突，或忽略此消息。"
        )
        final_reply = (final_reply or "") + pending_note

    return {"final_reply": final_reply, "error": None}


# ============ 路由函数 ============

def _classify_flow_relation(text: str) -> str:
    """
    规则判断输入与当前 flow 的关系 (不调 LLM).

    continue  — 确认/选择/修改时间/取消
    interrupt — 查询/天气/新事件 (不冲突的关键词)
    """
    kw_continue = [
        '确认', '确定', '好', '可以', '行', '是的', '对',
        'A', 'B', 'C', 'a', 'b', 'c',
        '换到', '改成', '调整到', '改到', '挪到', '推迟', '提前',
        '取消', '算了', '不用', '放弃',
        '方案', '第一个', '第二个', '第三个',
    ]
    kw_interrupt = [
        '查', '看看', '天气', '日程', '安排', '有什么', '有什么事',
        '下雨', '气温', '几度',
    ]
    if any(kw in text for kw in kw_continue):
        return "continue"
    if any(kw in text for kw in kw_interrupt):
        return "interrupt"
    return "continue"  # 默认继续当前 flow


def check_pending_action(state: AgentState) -> Literal["conflict_resolver", "input_classifier"]:
    """
    入口路由 — active_flow 优先, 支持 interrupt.

    - continue  → conflict_resolver
    - interrupt → pause conflict → input_classifier → query/event
    """
    flow = state.get("active_flow")
    pending = state.get("pending_action", {})
    stage = pending.get("stage", "")
    if flow != "conflict_resolution":
        print(f"[ROUTE] flow={flow} → classifier")
        return "input_classifier"

    user_input = state.get("user_input", "").strip()
    upper = user_input.upper()

    # ═══ waiting_confirm: 锁 ═══
    if stage == "waiting_confirm":
        if upper in ("确认", "是", "YES", "Y", "OK", "好", "可以", "行",
                     "取消", "算了", "不用了", "CANCEL", "放弃",
                     "A", "B", "C"):
            print(f"[ROUTE] confirm cmd → resolver")
            return "conflict_resolver"
        print(f"[ROUTE] confirm locked → resolver")
        return "conflict_resolver"

    # ═══ waiting_choice: continue / interrupt ═══
    if upper in ("取消", "算了", "不用了", "CANCEL", "放弃",
                 "A", "B", "C", "确认", "是", "YES", "Y", "OK"):
        return "conflict_resolver"

    options = pending.get("options", {})
    if _choice_detected(user_input, options):
        return "conflict_resolver"

    relation = _classify_flow_relation(user_input)
    if relation == "interrupt":
        print(f"[ROUTE] interrupt → pause + classifier")
        state["_flow_paused"] = True
        state["_paused_pending"] = pending
        return "input_classifier"

    if _is_new_event_request(user_input):
        print(f"[ROUTE] event_change → detector")
        state["_pending_conflict_warning"] = True
        state["_pending_conflict_context"] = {"summary": pending.get("summary", "")}
        state["_flow_paused"] = True
        state["_paused_pending"] = pending
        return "input_classifier"

    print(f"[ROUTE] ambiguous → resolver")
    return "conflict_resolver"


def _choice_detected(text: str, options: dict) -> bool:
    """检测输入是否含方案选择 (A/B/C + 可能的时间修改)"""
    import re
    upper = text.strip().upper()
    if upper in options:
        return True
    # "A方案" / "选B" / "A " (A后跟空格/标点/指令词) / "选A"
    if re.search(r'(选|选择|方案)\s*[ABCabc]|[ABCabc]\s*(方案|选项|计划|吧|，|,|。|\.|调整|换到|改到)', text):
        return True
    # "第二个" / "第三个" (完整词, 不含裸 "一"/"二"/"三")
    for word in ('第一个', '第二个', '第三个', '第一', '第二', '第三'):
        if word in text:
            return True
    return False


def _is_new_event_request(text: str) -> bool:
    """Delegate to event_detector so the same parser decides create/update intent."""
    try:
        from agent_service.graph.event_detector import _detect_event_statement
        result = _detect_event_statement(text)
        return result.get("intent") in {"create_event", "update_event"} and bool(result.get("sub_tasks"))
    except Exception:
        return False


# ═══════════════════ Input Classifier ═══════════════════

QUERY_KEYWORDS = [
    "查一下", "看看", "有什么", "安排", "日程", "计划",
    "查看", "查询", "显示", "列出", "告诉我",
    "几号", "几点", "什么时候",
]

def _is_query(text: str) -> bool:
    return any(kw in text for kw in QUERY_KEYWORDS) or "?" in text or "？" in text


def _is_bare_city(text: str) -> bool:
    """Bare city name for weather multi-turn: 英德 / 深圳 / 杭州"""
    t = text.strip()
    if not (2 <= len(t) <= 8):
        return False
    # 纯中文, 无标点无空格无指令词
    import re
    if not re.fullmatch(r'[一-鿿]{2,8}', t):
        return False
    # 排除含时间/天气/疑问词/动作词 (避免误判)
    blocked_fragments = {
        '今天', '明天', '后天', '天气', '下雨', '气温', '温度', '几度',
        '呢', '吗', '吧', '呀', '啊', '什么', '怎么', '如何',
        '打', '去', '做', '看', '吃', '学', '买', '开', '查', '写', '见',
        '帮', '安排', '提醒', '取消',
    }
    # 常见城市名库 (≥80% 国人所在城市)
    known_cities = {
        '北京', '上海', '广州', '深圳', '杭州', '成都', '南京', '武汉', '重庆',
        '西安', '长沙', '郑州', '天津', '苏州', '东莞', '佛山', '珠海', '厦门',
        '青岛', '大连', '沈阳', '济南', '合肥', '福州', '南昌', '南宁', '昆明',
        '贵阳', '兰州', '太原', '石家庄', '长春', '哈尔滨', '海口', '银川',
        '西宁', '拉萨', '乌鲁木齐', '呼和浩特', '英德', '汕头', '惠州', '中山',
        '温州', '绍兴', '嘉兴', '无锡', '常州', '南通', '徐州', '烟台', '威海',
    }
    # 优先走已知城市; 未知短中文走 planner 而非硬当城市
    return t in known_cities


MUTATION_KEYWORDS = [
    "删除", "删掉", "删了", "去掉", "移除", "取消", "不要", "不用", "放弃",
    "改到", "改成", "调整到", "挪到", "推到", "改为", "移动到", "延期", "提前",
]


def _is_mutation(text: str) -> bool:
    return any(kw in (text or "") for kw in MUTATION_KEYWORDS)


async def input_classifier_node(state: AgentState) -> dict[str, Any]:
    """Pre-router: 区分 weather / mutation / query / event (规则, 零 LLM)"""
    user_input = state.get("user_input", "")

    from agent_service.graph.event_detector import is_out_of_scope_request, out_of_scope_reply
    if is_out_of_scope_request(user_input):
        print(f"[CLASSIFIER] out_of_scope")
        return {
            "intent": "chat",
            "sub_tasks": [],
            "final_reply": out_of_scope_reply(),
            "_skip_planner": True,
            "source": "out_of_scope_guard",
        }

    # (0) weather > mutation > query — 按优先级依次检查
    from agent_service.graph.event_detector import _detect_weather_query
    weather = _detect_weather_query(user_input)
    if weather:
        p = weather['sub_tasks'][0]['params']
        print(f"[CLASSIFIER] weather city={p['city']} date={p.get('date','?')}")
        return weather

    from agent_service.graph.event_detector import _detect_mutation_statement
    mutation = _detect_mutation_statement(user_input)
    if mutation:
        print(f"[CLASSIFIER] mutation")
        return mutation

    # (0.5) bare city name → weather follow-up (多轮追问)
    if _is_bare_city(user_input):
        print(f"[CLASSIFIER] bare_city weather → {user_input}")
        return {
            'intent': 'query_weather',
            'sub_tasks': [{'action': 'query_weather', 'params': {
                'city': user_input.strip(),
                'date': date.today().isoformat(),
            }}],
            'entities': {'city': user_input.strip(),
                         'time': {'type': 'today', 'value': 'today'}},
            'confidence': 0.90,
            'source': 'weather_followup',
            '_skip_planner': True,
        }

    if _is_query(user_input):
        from agent_service.services.time_resolver import resolve_time_range
        tr = resolve_time_range(user_input)
        params = {}
        if tr.get("time_range"):
            params = {"start_time": tr["time_range"]["start"],
                      "end_time": tr["time_range"]["end"]}
        else:
            params = {"start_time": date.today().isoformat()}
        query_label = _extract_query_label(user_input, tr.get("time_range"))
        print(f"[CLASSIFIER] query")
        return {
            "intent": "query_schedule",
            "sub_tasks": [{"action": "check_calendar", "params": params}],
            "query_date_label": query_label,
            "_skip_planner": True,
            "source": "input_classifier",
        }
    print(f"[CLASSIFIER] → event_detector")
    return {}


def route_after_classifier(state: AgentState) -> Literal["tools_executor", "event_detector", "reply"]:
    if state.get("final_reply"):
        return "reply"
    if state.get("_skip_planner") and state.get("sub_tasks"):
        return "tools_executor"
    return "event_detector"


def route_after_event_detector(state: AgentState) -> Literal["tools_executor", "planner", "reply"]:
    """
    Event Detector 后路由:
      - 规则引擎捕获高置信度事件 → 跳过 planner, 直接 tools_executor
      - 规则引擎无法判断 → planner (LLM)
    """
    if state.get("final_reply"):
        print(f"[ROUTE] detector→reply")
        return "reply"
    if state.get("_skip_planner") and state.get("sub_tasks"):
        print(f"[ROUTE] detector→tools (skip LLM)")
        return "tools_executor"
    print(f"[ROUTE] detector→planner")
    return "planner"


def needs_confirmation(state: AgentState) -> Literal["reply", "tools_executor"]:
    """Validator → Reply (需确认) 或 Tools Executor (通过)"""
    route = "reply" if state.get("needs_confirmation") else "tools_executor"
    print(f"[ROUTE] validator→{route}")
    return route


def _has_task_mutations(state: AgentState) -> bool:
    return bool(state.get("tasks_created", [])) or bool(state.get("tasks_updated", []))


def route_after_tools(state: AgentState) -> Literal["pending_conflict_detector", "conflict_check", "coordinator"]:
    """tools_executor 后: 先 pending_conflict_detector, 再 conflict_check/coordinator"""
    if state.get("_pending_event"):
        return "pending_conflict_detector"
    if state.get("conflicts_found", []):
        return "coordinator"
    if _has_task_mutations(state):
        return "conflict_check"
    return "coordinator"


def route_after_pending_detector(state: AgentState) -> Literal["coordinator", "conflict_check", "reply"]:
    """pending_conflict_detector 后: 有冲突 → coordinator, 有任务变更 → conflict_check, 否则 reply"""
    if state.get("conflicts_found", []):
        return "coordinator"
    if _has_task_mutations(state):
        return "conflict_check"
    return "reply"


def should_check_conflicts(state: AgentState) -> Literal["conflict_check", "coordinator"]:
    """有冲突直接进coordinator, 不重复检测"""
    if state.get("conflicts_found", []):
        return "coordinator"
    if _has_task_mutations(state):
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
    workflow.add_node("input_classifier", input_classifier_node)
    workflow.add_node("event_detector", event_detector_node)
    workflow.add_node("conflict_resolver", conflict_resolver_node)
    workflow.add_node("planner", planner_node)
    workflow.add_node("state_inspector", state_inspector_node)
    workflow.add_node("entity_normalizer", entity_normalizer_node)
    workflow.add_node("validator", validator_node)
    workflow.add_node("tools_executor", tools_executor_node)
    workflow.add_node("pending_conflict_detector", pending_conflict_detector_node)
    workflow.add_node("conflict_check", conflict_check_node)
    workflow.add_node("coordinator", coordinator_node)
    workflow.add_node("reply", reply_node)

    # ═══ 入口: check_pending → conflict_resolver / input_classifier ═══
    workflow.set_conditional_entry_point(
        check_pending_action,
        {
            "conflict_resolver": "conflict_resolver",
            "input_classifier": "input_classifier",
        },
    )

    # ═══ input_classifier → tools_executor (query) 或 event_detector ═══
    workflow.add_conditional_edges(
        "input_classifier",
        route_after_classifier,
        {"tools_executor": "tools_executor", "event_detector": "event_detector", "reply": "reply"},
    )

    # ═══ conflict_resolver → 直接 tools_executor (跳过 planner/validator) ═══
    workflow.add_edge("conflict_resolver", "tools_executor")

    # ═══ event_detector → tools_executor (规则命中) 或 planner (LLM) ═══
    workflow.add_conditional_edges(
        "event_detector",
        route_after_event_detector,
        {"tools_executor": "tools_executor", "planner": "planner", "reply": "reply"},
    )

    # ═══ Planner → Inspector → Normalizer → Validator ═══
    workflow.add_edge("planner", "state_inspector")
    workflow.add_edge("state_inspector", "entity_normalizer")
    workflow.add_edge("entity_normalizer", "validator")

    # ═══ Validator → Tools 或 Reply ═══
    workflow.add_conditional_edges(
        "validator",
        needs_confirmation,
        {"reply": "reply", "tools_executor": "tools_executor"},
    )

    # ═══ 后段: tools → pending_detector → conflict_check → coordinator → reply ═══
    workflow.add_conditional_edges(
        "tools_executor",
        route_after_tools,
        {"pending_conflict_detector": "pending_conflict_detector",
         "conflict_check": "conflict_check",
         "coordinator": "coordinator"},
    )

    workflow.add_conditional_edges(
        "pending_conflict_detector",
        route_after_pending_detector,
        {"coordinator": "coordinator", "conflict_check": "conflict_check", "reply": "reply"},
    )

    workflow.add_conditional_edges(
        "conflict_check",
        has_conflicts,
        {"coordinator": "coordinator", "reply": "reply"},
    )

    workflow.add_edge("coordinator", "reply")
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

    final_reply = state.get("final_reply")
    if final_reply:
        for char in final_reply:
            yield char
            import asyncio
            await asyncio.sleep(0.005)
        return

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
