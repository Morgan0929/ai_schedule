"""
AI 协调决策模块

当检测到任务冲突时，生成多方案建议
- LLM 模式：调用 DeepSeek 分析并生成方案
- Mock 模式：规则引擎生成模板化方案
"""
import json
from typing import Any
from agent_service.graph.state import AgentState
from agent_service.llm.deepseek_client import chat_completion_json, is_llm_available


async def coordinator_node(state: AgentState) -> dict[str, Any]:
    """
    协调决策节点：分析冲突，生成多方案
    """
    conflicts = state.get("conflicts_found", [])
    user_input = state.get("user_input", "")

    if not conflicts:
        return {"suggestions": [], "recommended_plan": "", "error": None}

    # 尝试 LLM 模式
    if is_llm_available():
        result = await _llm_coordinate(conflicts, user_input)
        if result:
            return result

    # Mock 回退
    return await _mock_coordinate(conflicts)


async def _llm_coordinate(conflicts: list[dict], user_input: str) -> dict | None:
    """LLM 协调"""
    prompt = f"""你是 AI 协调决策引擎。分析以下时间冲突，给出 2-3 个解决方案。

冲突信息:
{json.dumps(conflicts, ensure_ascii=False, indent=2)}

用户原始输入: {user_input}

输出必须是合法 JSON:
{{
    "suggestions": [
        {{"plan_id": "A", "title": "...", "description": "...", "impact": "...", "is_recommended": true}},
        {{"plan_id": "B", "title": "...", "description": "...", "impact": "...", "is_recommended": false}}
    ],
    "recommended_plan": "A",
    "reasoning": "推荐理由"
}}"""

    messages = [
        {"role": "system", "content": prompt},
        {"role": "user", "content": "请给出协调方案。"},
    ]
    result = await chat_completion_json(messages, temperature=0.5, max_tokens=1500)

    if result and result.get("suggestions"):
        return {
            "suggestions": result.get("suggestions", []),
            "recommended_plan": result.get("recommended_plan", ""),
            "error": None,
        }
    return None


async def _mock_coordinate(conflicts: list[dict]) -> dict[str, Any]:
    """Mock 协调 — 规则引擎生成方案"""
    suggestions = []

    for i, conflict in enumerate(conflicts):
        task_a = conflict.get("task_a", f"任务A{i}")
        task_b = conflict.get("task_b", f"任务B{i}")
        severity = conflict.get("severity", "WARNING")

        suggestions.append({
            "plan_id": "A",
            "title": f"延后「{task_b}」",
            "description": f"将「{task_b}」推迟到「{task_a}」结束后进行。",
            "impact": f"「{task_b}」的时间将有所调整，不影响任务内容。",
            "is_recommended": True,
        })
        suggestions.append({
            "plan_id": "B",
            "title": f"提前「{task_a}」",
            "description": f"将「{task_a}」提前 30 分钟开始，错开冲突时段。",
            "impact": f"需要提前通知「{task_a}」的参与者。",
            "is_recommended": False,
        })
        if severity != "CRITICAL":
            suggestions.append({
                "plan_id": "C",
                "title": "线上参加",
                "description": f"将「{task_b}」改为线上形式，减少地点切换时间。",
                "impact": "需要确认线上会议条件是否满足。",
                "is_recommended": False,
            })

    return {
        "suggestions": suggestions[:5],  # 最多 5 个方案
        "recommended_plan": "A",
        "error": None,
    }
