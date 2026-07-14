"""
Coordinator Node — 冲突协调 & 多方案生成

IN:  conflicts_found, user_input
OUT: ConflictOutput (Pydantic structured output)
"""
import json
from typing import Any
from agent_service.graph.state import AgentState
from agent_service.graph.schemas import ConflictOutput
from agent_service.llm.deepseek_client import is_llm_available, get_structured_llm
from agent_service.llm.prompts import coordinator_prompt


async def coordinator_node(state: AgentState) -> dict[str, Any]:
    conflicts = state.get("conflicts_found", [])
    user_input = state.get("user_input", "")

    if not conflicts:
        return {"suggestions": [], "recommended_plan": ""}

    if is_llm_available():
        result = await _llm_coordinate(conflicts, user_input)
        if result:
            return _conflict_output_to_state(result)

    return await _mock_coordinate(conflicts)


async def _llm_coordinate(conflicts: list[dict], user_input: str) -> ConflictOutput | None:
    """LLM: ChatPromptTemplate → with_structured_output → Pydantic"""
    conflict_text = json.dumps(conflicts, ensure_ascii=False, indent=2)
    prompt_value = coordinator_prompt.invoke({
        "conflict_info": conflict_text,
        "user_preferences": user_input,
    })

    try:
        llm = get_structured_llm(ConflictOutput)
        result = await llm.ainvoke(prompt_value)
        if isinstance(result, ConflictOutput):
            return result
    except Exception:
        pass
    return None


def _conflict_output_to_state(result: ConflictOutput) -> dict[str, Any]:
    """将 ConflictOutput 转为 AgentState 格式"""
    suggestions = []
    for i, sol in enumerate(result.solutions):
        plan_id = chr(ord("A") + i) if i < 26 else str(i)
        suggestions.append({
            "plan_id": plan_id,
            "title": sol,
            "is_recommended": i == 0,
        })

    return {
        "conflicts_found": [{"reason": c} for c in result.conflicts],
        "conflict_count": len(result.conflicts),
        "suggestions": suggestions,
        "recommended_plan": "A" if suggestions else "",
    }


async def _mock_coordinate(conflicts: list[dict]) -> dict[str, Any]:
    suggestions = []
    for c in conflicts[:3]:
        a, b = c.get("task_a", "任务A"), c.get("task_b", "任务B")
        suggestions.append({"plan_id": "A", "title": f"延后「{b}」",
            "description": f"将「{b}」推迟", "impact": "时间微调", "is_recommended": True})
        suggestions.append({"plan_id": "B", "title": f"提前「{a}」",
            "description": f"将「{a}」提前30分钟", "impact": "需通知参与者", "is_recommended": False})
    return {"suggestions": suggestions[:5], "recommended_plan": "A"}
