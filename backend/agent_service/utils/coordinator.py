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
    print("COORDINATOR INPUT:", conflicts)

    if not conflicts:
        return {"suggestions": [], "recommended_plan": ""}

    # LLM 只负责建议, 不改 conflicts_found (数据库说了算)
    if is_llm_available():
        llm_result = await _llm_coordinate(conflicts, user_input)
        if llm_result:
            suggestions = _extract_suggestions(llm_result)
            # 不替用户决定 — 所有方案平等, 等用户选
            for s in suggestions:
                s["is_recommended"] = False
            r = {
                "conflicts_found": conflicts,
                "conflict_count": len(conflicts),
                "suggestions": suggestions,
                "recommended_plan": "",  # 等用户选择
            }
            print("COORDINATOR OUTPUT:", r)
            return r

    r = {
        "conflicts_found": conflicts,
        "conflict_count": len(conflicts),
        **_mock_coordinate(conflicts),
    }
    print("COORDINATOR OUTPUT:", r)
    return r


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


def _extract_suggestions(result: ConflictOutput) -> list[dict]:
    """从 LLM 输出提取建议, 不改 conflicts_found"""
    suggestions = []
    for i, sol in enumerate(result.solutions):
        plan_id = chr(ord("A") + i) if i < 26 else str(i)
        suggestions.append({
            "plan_id": plan_id, "title": sol,
            "is_recommended": i == 0,
        })
    return suggestions


def _conflict_output_to_state(result: ConflictOutput) -> dict[str, Any]:
    """已废弃 — 保留兼容, 不再覆盖 conflicts_found"""
    return {
        "suggestions": _extract_suggestions(result),
        "recommended_plan": "A",
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
