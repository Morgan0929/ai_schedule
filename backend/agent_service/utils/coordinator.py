"""
Coordinator Node — 冲突协调 & 多方案生成

IN:  conflicts_found, user_input
OUT: suggestions, recommended_plan
Prompt: coordinator_prompt ChatPromptTemplate
"""
import json
from typing import Any
from agent_service.graph.state import AgentState
from agent_service.llm.deepseek_client import is_llm_available, get_llm_client
from agent_service.llm.prompts import coordinator_prompt


async def coordinator_node(state: AgentState) -> dict[str, Any]:
    conflicts = state.get("conflicts_found", [])
    user_input = state.get("user_input", "")

    if not conflicts:
        return {"suggestions": [], "recommended_plan": ""}

    if is_llm_available():
        result = await _llm_coordinate(conflicts, user_input)
        if result:
            return result

    return await _mock_coordinate(conflicts)


async def _llm_coordinate(conflicts: list[dict], user_input: str) -> dict | None:
    conflict_text = json.dumps(conflicts, ensure_ascii=False, indent=2)
    prompt_value = coordinator_prompt.invoke({
        "conflict_info": conflict_text,
        "user_preferences": user_input,
    })

    client = get_llm_client()
    try:
        resp = await client.chat.completions.create(
            model="deepseek-chat",
            messages=[{"role": "system", "content": prompt_value.messages[0].content},
                      {"role": "user", "content": prompt_value.messages[1].content}],
            temperature=0.5, max_tokens=1500,
        )
        raw = resp.choices[0].message.content.strip()
        try: return json.loads(raw)
        except json.JSONDecodeError:
            try:
                s, e = raw.index("{"), raw.rindex("}") + 1
                return json.loads(raw[s:e])
            except (ValueError, json.JSONDecodeError): pass
    except Exception: pass
    return None


async def _mock_coordinate(conflicts: list[dict]) -> dict[str, Any]:
    suggestions = []
    for c in conflicts[:3]:
        a, b = c.get("task_a", "任务A"), c.get("task_b", "任务B")
        suggestions.append({"plan_id": "A", "title": f"延后「{b}」",
            "description": f"将「{b}」推迟到「{a}」结束后", "impact": "时间微调", "is_recommended": True})
        suggestions.append({"plan_id": "B", "title": f"提前「{a}」",
            "description": f"将「{a}」提前30分钟", "impact": "需通知参与者", "is_recommended": False})
    return {"suggestions": suggestions[:5], "recommended_plan": "A"}
