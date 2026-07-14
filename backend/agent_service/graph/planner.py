"""
Planner Node — 意图识别 & 任务拆解

IN:  user_input
OUT: PlannerOutput (Pydantic structured output)
"""
from typing import Any
from agent_service.graph.state import AgentState
from agent_service.graph.schemas import PlannerOutput
from agent_service.llm.deepseek_client import is_llm_available, get_structured_llm
from agent_service.llm.mock_agent import detect_intent
from agent_service.llm.prompts import planner_prompt


async def planner_node(state: AgentState) -> dict[str, Any]:
    user_input = state["user_input"]

    if is_llm_available():
        result = await _llm_plan(user_input)
        if result:
            return _planner_output_to_state(result)

    return await _mock_plan(user_input)


async def _llm_plan(user_input: str) -> PlannerOutput | None:
    """LLM: ChatPromptTemplate → with_structured_output → Pydantic"""
    from datetime import date
    today = date.today().isoformat()
    prompt_value = planner_prompt.invoke({"today": today, "user_input": user_input})

    try:
        llm = get_structured_llm(PlannerOutput)
        result = await llm.ainvoke(prompt_value)
        if isinstance(result, PlannerOutput):
            return result
    except Exception:
        pass
    return None


def _planner_output_to_state(result: PlannerOutput) -> dict[str, Any]:
    """将 Pydantic 输出转换为 AgentState 更新"""
    # 规范化 intent（大写→小写）
    intent = result.intent.lower() if result.intent else "chat"

    sub_tasks = []
    entities = result.entities or {}

    if result.tool:
        sub_tasks.append({"action": result.tool, "params": entities.copy()})

    # 补充 check_calendar（创建/修改任务前先查已有日程）
    if intent in ("create_task", "update_task", "arrange_trip"):
        sub_tasks.insert(0, {"action": "check_calendar",
                             "params": _extract_time_params(entities)})
    if intent == "arrange_trip":
        sub_tasks.append({"action": "query_weather",
                          "params": _extract_city_params(entities)})

    return {
        "intent": intent,
        "sub_tasks": sub_tasks,
    }


def _extract_time_params(entities: dict) -> dict:
    keys = ["start", "end", "start_time", "end_time", "date", "deadline"]
    return {k: v for k, v in entities.items()
            if k in keys or "time" in k.lower() or "date" in k.lower()}


def _extract_city_params(entities: dict) -> dict:
    keys = ["city", "destination", "location", "目的地"]
    return {k: v for k, v in entities.items() if k in keys}


async def _mock_plan(user_input: str) -> dict[str, Any]:
    """规则引擎回退"""
    info = detect_intent(user_input)
    intent = info["intent"]
    entities = info.get("entities", {})

    sub_tasks = []
    if intent == "CREATE_TASK":
        sub_tasks = [{"action": "check_calendar", "params": entities},
                     {"action": "create_task", "params": entities}]
    elif intent in ("QUERY_CALENDAR", "DETECT_CONFLICT"):
        sub_tasks = [{"action": "check_calendar", "params": entities}]
    elif intent == "ARRANGE_TRIP":
        sub_tasks = [{"action": "check_calendar", "params": entities},
                     {"action": "query_weather", "params": entities},
                     {"action": "create_task", "params": entities}]
    elif intent == "QUERY_WEATHER":
        sub_tasks = [{"action": "query_weather", "params": entities}]

    return {"intent": intent, "sub_tasks": sub_tasks}
