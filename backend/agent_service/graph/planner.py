"""
Planner Node — 意图识别 (LLM + Confidence Gate)

LLM 失败时返回 UNKNOWN (confidence=0, source=fallback)
不再伪装成 QUERY_CALENDAR。
"""
from datetime import date, datetime
from typing import Any
from agent_service.graph.state import AgentState
from agent_service.graph.schemas import PlannerOutput, Intent, normalize_intent
from agent_service.llm.deepseek_client import is_llm_available, get_structured_llm
from agent_service.llm.prompts import planner_prompt

CONFIDENCE_THRESHOLD = 0.8  # 低于此值需要用户确认


def _normalize_return(r: dict) -> dict:
    """P2: PlannerOutputNormalizer — 所有返回路径统一经过这里"""
    r["intent"] = str(r.get("intent", "chat"))
    r.setdefault("sub_tasks", [])
    r.setdefault("needs_confirmation", False)
    if r.get("intent") in ("unknown", "UNKNOWN"):
        r["intent"] = "chat"
    import json
    print(f"FINAL PLANNER RETURN [type={type(r['intent']).__name__}]",
          json.dumps(r, ensure_ascii=False, default=str)[:500])
    return r


async def planner_node(state: AgentState) -> dict[str, Any]:
    user_input = state["user_input"]

    # ① Context Resolver
    pending = state.get("pending_action", {})
    if pending.get("type") == "conflict_resolution":
        options = pending.get("options", {})
        choice = user_input.strip().upper()
        if choice in options:
            opt = options[choice]
            return _normalize_return({
                "intent": "update_event",
                "sub_tasks": [{"action": "update_task", "params": {
                    "target": opt["task"], "hint": user_input}}],
                "needs_confirmation": False,
                "pending_action": {},
            })

    # ② LLM
    if is_llm_available():
        result = await _llm_plan(user_input)
        if result and str(result.intent) not in ("unknown", "chat"):
            return _normalize_return(_planner_output_to_state(result))

    # ③ Event Detector
    event_result = _detect_event_statement(user_input)
    if event_result["confidence"] >= CONFIDENCE_THRESHOLD:
        return _normalize_return(event_result)

    # ④ Low confidence
    if event_result["confidence"] > 0:
        return _normalize_return({
            "intent": "unknown",
            "sub_tasks": [],
            "needs_confirmation": True,
        })

    # ⑤ Fallback
    return _normalize_return({"intent": "chat", "sub_tasks": []})


async def _llm_plan(user_input: str) -> PlannerOutput | None:
    """LLM Planner — 失败返回 None，绝不静默"""
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
            print("RAW PLANNER OUTPUT=", result.model_dump_json(indent=2))
            return result
    except Exception as e:
        print("RAW PLANNER OUTPUT FAILED:", e)
    return None


def _detect_event_statement(text: str) -> dict[str, Any]:
    """
    事件陈述检测 (不靠关键词)

    判断逻辑: 有未来时间 + 有事件描述 → create_event
    """
    from agent_service.llm.mock_agent import _extract_time, _extract_hour
    from datetime import date as date_type

    time_info = _extract_time(text)
    hour = _extract_hour(text)
    # 有具体小时 或 解析出的日期在未来 → 有时间
    has_time = hour is not None or "T" in time_info.get("start", "")
    if not has_time:
        try:
            parsed_date = date_type.fromisoformat(time_info.get("start", ""))
            has_time = parsed_date > date_type.today()
        except (ValueError, TypeError):
            pass

    # 去掉时间词，剩余文本作为事件名
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
    # 标题清洗: 去掉引导词
    for prefix in ["我要去", "我要", "我想去", "我想", "帮我", "记一下", "提醒我", "安排"]:
        if event_title.startswith(prefix):
            event_title = event_title[len(prefix):]
            break
    # 疑问词 → query_event, 不是 create_event
    question_words = ["什么", "怎么", "吗", "呢", "如何", "有没有", "查看", "查询",
                      "啥", "谁", "哪里", "干嘛", "干啥", "有什么事", "有什么安排"]
    is_query = any(qw in text for qw in question_words) or "?" in text or "？" in text
    has_event = len(event_title) >= 2 and not is_query

    if has_time and has_event:
        entities = {"title": event_title, **time_info}
        if hour:
            d = date.today()
            if "明天" in text:
                from datetime import timedelta
                d = d + timedelta(days=1)
            elif "后天" in text:
                from datetime import timedelta
                d = d + timedelta(days=2)
            entities["start_time"] = f"{d.isoformat()}T{hour:02d}:00:00"

        return {
            "intent": "create_event",
            "sub_tasks": [
                {"action": "check_calendar", "params": entities},
                {"action": "create_task", "params": entities},
            ],
            "confidence": 0.85 if has_time and has_event else 0.5,
            "source": "event_detector",
        }

    # 纯查询: 有时间但无事件
    if has_time and not has_event:
        return {
            "intent": "query_schedule",
            "sub_tasks": [{"action": "check_calendar", "params": time_info}],
            "confidence": 0.7,
            "source": "event_detector",
        }

    return {"intent": "chat", "sub_tasks": [], "confidence": 0.0, "source": "event_detector"}


def _planner_output_to_state(result: PlannerOutput) -> dict[str, Any]:
    """PlannerOutput → AgentState 更新"""
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
    if intent == "arrange_trip":
        sub_tasks.append({"action": "query_weather", "params": entities})

    return {
        "intent": intent_str,
        "sub_tasks": sub_tasks,
        "_confidence": float(result.confidence),
        "_source": result.source,
        "needs_confirmation": result.need_confirmation or result.confidence < CONFIDENCE_THRESHOLD,
    }
