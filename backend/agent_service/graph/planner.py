"""
Planner Node — 意图识别 (唯一出口: normalize_planner_result)
"""
from datetime import date, datetime
from typing import Any
from agent_service.graph.state import AgentState
from agent_service.graph.schemas import PlannerOutput, Intent, normalize_intent
from agent_service.llm.deepseek_client import is_llm_available, get_structured_llm
from agent_service.llm.prompts import planner_prompt

CONFIDENCE_THRESHOLD = 0.8


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

    result = {
        "intent": intent_str,
        "sub_tasks": sub_tasks or [],
        "_confidence": confidence,
        "_source": source or ("llm" if is_llm_available() else "fallback"),
        "needs_confirmation": needs_confirmation,
        **extra,
    }
    import json
    print(f"PLANNER RETURN [intent={intent_str}] [source={result['_source']}]",
          json.dumps(result, ensure_ascii=False, default=str)[:500])
    return result


async def planner_node(state: AgentState) -> dict[str, Any]:
    user_input = state["user_input"]

    # ① Context Resolver
    pending = state.get("pending_action", {})
    if pending.get("type") == "conflict_resolution":
        options = pending.get("options", {})
        choice = user_input.strip().upper()
        if choice in options:
            opt = options[choice]
            return normalize_planner_result(
                "update_event",
                [{"action": "update_task", "params": {"target": opt["task"], "hint": user_input}}],
                source="context_resolver", pending_action={},
            )

    # ② LLM
    if is_llm_available():
        result = await _llm_plan(user_input)
        if result and str(result.intent) not in ("unknown", "chat"):
            r = _planner_output_to_state(result)
            return normalize_planner_result(
                r.pop("intent"), r.pop("sub_tasks", []),
                confidence=r.pop("_confidence", 0), source=r.pop("_source", "llm"),
                **r,
            )

    # ③ Event Detector
    event_result = _detect_event_statement(user_input)
    if event_result["confidence"] >= CONFIDENCE_THRESHOLD:
        return normalize_planner_result(
            event_result.pop("intent"), event_result.pop("sub_tasks", []),
            confidence=event_result.pop("confidence", 0),
            source=event_result.pop("source", "event_detector"),
            **event_result,
        )

    # ④ Low confidence
    if event_result.get("confidence", 0) > 0:
        return normalize_planner_result("unknown", [], source="event_detector", needs_confirmation=True)

    # ⑤ Fallback
    return normalize_planner_result("chat", [], source="fallback")


async def _llm_plan(user_input: str) -> PlannerOutput | None:
    """LLM Planner"""
    today = date.today().isoformat()
    prompt_value = planner_prompt.invoke({"today": today, "user_input": user_input})
    try:
        llm = get_structured_llm(PlannerOutput)
        result = await llm.ainvoke(prompt_value)
        if isinstance(result, PlannerOutput):
            result.source = "llm"
            if not result.confidence:
                result.confidence = 0.85
            result.intent = normalize_intent(result.intent.value if hasattr(result.intent, 'value') else str(result.intent))
            return result
    except Exception:
        pass
    return None


def _detect_event_statement(text: str) -> dict[str, Any]:
    """事件陈述检测"""
    from agent_service.llm.mock_agent import _extract_time, _extract_hour
    from datetime import date as date_type

    time_info = _extract_time(text)
    h = _extract_hour(text)

    has_time = h is not None or "T" in time_info.get("start", "")
    if not has_time:
        try:
            parsed_date = date_type.fromisoformat(time_info.get("start", ""))
            has_time = parsed_date > date_type.today()
        except (ValueError, TypeError):
            pass

    time_words = ["明天", "后天", "下周", "这周", "今天", "上午", "下午", "晚上",
                  "周一", "周二", "周三", "周四", "周五", "周六", "周日",
                  "下个月", "下周三", "下周一", "下周二", "下周四", "下周五",
                  "1点", "2点", "3点", "4点", "5点", "6点", "7点", "8点",
                  "9点", "10点", "11点", "12点",
                  "半", "点半", "1点半", "2点半", "3点半", "4点半", "5点半",
                  "6点半", "7点半", "8点半", "9点半", "10点半", "11点半", "12点半",
                  "提醒我", "帮我", "帮我安排", "提醒"]
    event_title = text
    for w in time_words:
        event_title = event_title.replace(w, "")
    event_title = event_title.strip().strip("，,。.；;：:！!？? ")
    for prefix in ["我要去", "我要", "我想去", "我想", "帮我", "记一下", "提醒我", "安排"]:
        if event_title.startswith(prefix):
            event_title = event_title[len(prefix):]
            break

    question_words = ["什么", "怎么", "吗", "呢", "如何", "有没有", "查看", "查询",
                      "啥", "谁", "哪里", "干嘛", "干啥", "有什么事", "有什么安排"]
    is_query = any(qw in text for qw in question_words) or "?" in text or "？" in text
    has_event = len(event_title) >= 2 and not is_query

    entities = {"title": event_title, **time_info}
    if h:
        d = date.today()
        if "明天" in text: d += __import__('datetime').timedelta(days=1)
        elif "后天" in text: d += __import__('datetime').timedelta(days=2)
        entities["start_time"] = f"{d.isoformat()}T{h:02d}:00:00"

    if has_time and has_event:
        return {"intent": "create_event", "sub_tasks": [
            {"action": "check_calendar", "params": entities},
            {"action": "create_task", "params": entities},
        ], "confidence": 0.85, "source": "event_detector"}

    if has_time and not has_event:
        return {"intent": "query_schedule", "sub_tasks": [
            {"action": "check_calendar", "params": time_info},
        ], "confidence": 0.7, "source": "event_detector"}

    return {"intent": "chat", "sub_tasks": [], "confidence": 0.0, "source": "event_detector"}


def _planner_output_to_state(result: PlannerOutput) -> dict[str, Any]:
    """PlannerOutput → dict"""
    intent = normalize_intent(result.intent.value if isinstance(result.intent, Intent) else str(result.intent))
    intent_str = intent.value
    sub_tasks = []
    entities = result.entities or {}

    intent_to_action = {
        Intent.CREATE_EVENT: "create_task",
        Intent.CREATE_TODO: "create_task",
        Intent.CREATE_REMINDER: "create_task",
        Intent.DELETE_EVENT: "delete_task",
        Intent.UPDATE_EVENT: "update_task",
        Intent.QUERY_SCHEDULE: "check_calendar",
        Intent.QUERY_WEATHER: "query_weather",
        Intent.ARRANGE_TRIP: "create_task",
    }
    action = intent_to_action.get(intent)
    if action:
        sub_tasks.append({"action": action, "params": entities.copy()})

    if intent in (Intent.CREATE_EVENT, Intent.CREATE_TODO, Intent.CREATE_REMINDER,
                  Intent.UPDATE_EVENT, Intent.ARRANGE_TRIP):
        sub_tasks.insert(0, {"action": "check_calendar", "params": entities})

    return {
        "intent": intent_str,
        "sub_tasks": sub_tasks,
        "_confidence": float(result.confidence),
        "_source": result.source,
    }
