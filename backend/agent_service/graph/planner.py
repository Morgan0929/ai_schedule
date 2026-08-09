"""
Planner Node — LLM 意图识别

前置: event_detector 已运行, 规则引擎无法判断的才到这里
       pending_action 已在 graph 路由层拦截, 永不进入 planner

唯一出口: normalize_planner_result
"""
from datetime import date, datetime
from typing import Any
from agent_service.graph.state import AgentState
from agent_service.graph.schemas import PlannerOutput, Intent, normalize_intent
from agent_service.llm.deepseek_client import is_llm_available, get_structured_llm
from agent_service.llm.prompts import planner_prompt


def normalize_planner_result(
    intent: str, sub_tasks: list = None,
    confidence: float = 0.0, source: str = "",
    needs_confirmation: bool = False, **extra
) -> dict[str, Any]:
    """Planner 唯一出口"""
    n = normalize_intent(intent)
    intent_str = n.value if hasattr(n, 'value') else str(n)
    if intent_str in ("unknown", "UNKNOWN"):
        intent_str = "chat"

    # 统一时间字段: start→start_time, end→end_time, 删旧字段
    tasks = list(sub_tasks or [])
    for t in tasks:
        p = t.get("params", {}) if isinstance(t.get("params"), dict) else {}
        # start → start_time
        if "start" in p:
            if "start_time" not in p:
                p["start_time"] = p["start"]
            del p["start"]
        # end → end_time
        if "end" in p:
            if "end_time" not in p:
                p["end_time"] = p["end"]
            del p["end"]
        # date → ScheduleQuery
        if t.get("action") in ("check_calendar", "query_calendar"):
            from agent_service.graph.calendar_service import ScheduleQuery
            q = ScheduleQuery.from_params(p)
            if q:
                s, e = q.to_iso()
                t["params"] = {"start_time": s, "end_time": e}

    result = {
        "intent": intent_str,
        "sub_tasks": sub_tasks or [],
        "_confidence": confidence,
        "_source": source or ("llm" if is_llm_available() else "fallback"),
        "needs_confirmation": needs_confirmation,
        **extra,
    }
    print(f"[PLANNER] intent={intent_str} src={result['_source']} tasks={len(result.get('sub_tasks',[]))}")
    return result


async def planner_node(state: AgentState) -> dict[str, Any]:
    """
    Planner Node — LLM 深度分析
    """
    # (3) 首次调用时打印 schema (仅一次)
    if not hasattr(planner_node, '_schema_printed'):
        from agent_service.graph.schemas import PlannerOutput, Intent
        print(f"[PLANNER] schema — intents={[e.value for e in Intent]} fields={list(PlannerOutput.model_fields.keys())}")
        planner_node._schema_printed = True

    user_input = state["user_input"]

    # ═══ 只有一条路径: LLM → fallback to chat ═══
    # event_detector 已处理了规则能处理的所有情况
    # 这里只做 LLM 深度分析和最终的 chat fallback

    if is_llm_available():
        result = await _llm_plan(user_input)
        if result and str(result.intent) not in ("unknown", "chat"):
            r = _planner_output_to_state(result)
            return normalize_planner_result(
                r.pop("intent"), r.pop("sub_tasks", []),
                confidence=r.pop("_confidence", 0), source=r.pop("_source", "llm"),
                **r,
            )

    # LLM 无法判断 → chat
    return normalize_planner_result("chat", [], source="fallback")


async def _llm_plan(user_input: str) -> PlannerOutput | None:
    """LLM Planner"""
    today = date.today().isoformat()
    prompt_value = planner_prompt.invoke({"today": today, "user_input": user_input})
    try:
        llm = get_structured_llm(PlannerOutput)
        result = await llm.ainvoke(prompt_value)
        # (1) LLM 结构化输出成功
        if isinstance(result, PlannerOutput):
            result.source = "llm"
            if not result.confidence:
                result.confidence = 0.85
            result.intent = normalize_intent(result.intent.value if hasattr(result.intent, 'value') else str(result.intent))
            return result
    except Exception as e:
        # (2) structured output 异常
        import traceback
        print(f"[PLANNER] ERROR {type(e).__name__}: {e}\n{traceback.format_exc()[-300:]}")
    return None


def _planner_output_to_state(result: PlannerOutput) -> dict[str, Any]:
    """PlannerOutput → dict"""
    intent = normalize_intent(result.intent.value if isinstance(result.intent, Intent) else str(result.intent))
    intent_str = intent.value
    sub_tasks = []
    entities = result.entities or {}

    intent_to_action = {
        Intent.CREATE_EVENT: "create_pending",
        Intent.DELETE_EVENT: "delete_task",
        Intent.UPDATE_EVENT: "update_task",
        Intent.QUERY_SCHEDULE: "check_calendar",
        Intent.QUERY_WEATHER: "query_weather",
    }
    action = intent_to_action.get(intent)
    if action:
        sub_tasks.append({"action": action, "params": entities.copy()})

    if intent in (Intent.CREATE_EVENT, Intent.UPDATE_EVENT):
        sub_tasks.insert(0, {"action": "check_calendar", "params": entities})

    return {
        "intent": intent_str,
        "sub_tasks": sub_tasks,
        "_confidence": float(result.confidence),
        "_source": result.source,
    }
