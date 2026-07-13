"""
Planner Node — 意图识别 & 任务拆解

IN:  user_input
OUT: intent, sub_tasks
"""
from datetime import date
from typing import Any
from agent_service.graph.state import AgentState
from agent_service.llm.deepseek_client import is_llm_available, get_llm_client
from agent_service.llm.mock_agent import detect_intent
from agent_service.llm.prompts import planner_prompt


async def planner_node(state: AgentState) -> dict[str, Any]:
    user_input = state["user_input"]

    if is_llm_available():
        result = await _llm_plan(user_input)
        if result and result.get("intent"):
            return {"intent": result["intent"], "sub_tasks": result.get("sub_tasks", [])}

    return await _mock_plan(user_input)


async def _llm_plan(user_input: str) -> dict | None:
    """LLM: ChatPromptTemplate → DeepSeek → parsed JSON"""
    today = date.today().isoformat()
    prompt_value = planner_prompt.invoke({"today": today, "user_input": user_input})
    messages = prompt_value.to_messages()

    client = get_llm_client()

    try:
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": m.type if hasattr(m, 'type') else m.__class__.__name__.replace('Message','').lower(),
                       "content": m.content} for m in messages],
            temperature=0.3,
            max_tokens=1024,
        )
        raw = resp.choices[0].message.content.strip()

        # Parse JSON
        import json
        try: return json.loads(raw)
        except json.JSONDecodeError:
            for marker in ["```json", "```"]:
                if marker in raw:
                    try:
                        s = raw.index(marker) + len(marker)
                        e = raw.index("```", s)
                        return json.loads(raw[s:e].strip())
                    except (ValueError, json.JSONDecodeError): continue
            try:
                s, e = raw.index("{"), raw.rindex("}") + 1
                return json.loads(raw[s:e])
            except (ValueError, json.JSONDecodeError): pass
        return None
    except Exception:
        return None


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
