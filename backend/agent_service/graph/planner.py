"""
Planner 节点 — 分析用户意图，拆解任务

双模式：
- LLM 模式：调用 DeepSeek 解析自然语言 → JSON
- Mock 模式：规则引擎关键词匹配
"""
from typing import Any
from datetime import date
from agent_service.graph.state import AgentState
from agent_service.llm.deepseek_client import chat_completion_json, is_llm_available
from agent_service.llm.mock_agent import detect_intent
from agent_service.llm.prompts import PLANNER_SYSTEM_PROMPT


async def planner_node(state: AgentState) -> dict[str, Any]:
    """
    Planner 节点：分析用户输入 → 输出意图 + 子任务
    """
    user_input = state["user_input"]

    # 尝试 LLM 模式
    if is_llm_available():
        result = await _llm_plan(user_input)
        if result and result.get("intent"):
            return {
                "intent": result.get("intent", "CHAT"),
                "sub_tasks": result.get("sub_tasks", []),
                "error": None,
            }

    # Mock 回退
    return await _mock_plan(user_input)


async def _llm_plan(user_input: str) -> dict | None:
    """LLM 模式规划"""
    today = date.today().isoformat()
    system_prompt = PLANNER_SYSTEM_PROMPT.replace("{today}", today)

    messages = [
        {"role": "system", "content": system_prompt},
        {"role": "user", "content": user_input},
    ]
    return await chat_completion_json(messages, temperature=0.3, max_tokens=1024)


async def _mock_plan(user_input: str) -> dict[str, Any]:
    """Mock 模式规划 — 规则引擎"""
    info = detect_intent(user_input)
    intent = info["intent"]
    entities = info.get("entities", {})

    sub_tasks = []
    if intent == "CREATE_TASK":
        sub_tasks = [
            {"action": "check_calendar", "params": entities},
            {"action": "create_task", "params": entities},
        ]
    elif intent in ("QUERY_CALENDAR", "DETECT_CONFLICT"):
        sub_tasks = [
            {"action": "check_calendar", "params": entities},
        ]
    elif intent == "ARRANGE_TRIP":
        sub_tasks = [
            {"action": "check_calendar", "params": entities},
            {"action": "query_weather", "params": entities},
            {"action": "create_task", "params": entities},
        ]
    elif intent == "QUERY_WEATHER":
        sub_tasks = [
            {"action": "query_weather", "params": entities},
        ]
    elif intent == "GENERATE_TIMELINE":
        sub_tasks = [
            {"action": "check_calendar", "params": entities},
        ]

    return {
        "intent": intent,
        "sub_tasks": sub_tasks,
        "error": None,
    }
