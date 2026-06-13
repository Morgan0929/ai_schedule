"""
Planner 节点 — 分析用户意图，拆解任务

对应 Agent 工作流的第一个节点：
用户输入 → Planner → 拆解为子任务列表
"""
from typing import Any
from langchain_core.messages import SystemMessage, HumanMessage
from agent_service.graph.state import AgentState
from agent_service.llm.deepseek_client import get_llm_client


# Planner 系统提示词
PLANNER_SYSTEM_PROMPT = """你是一个日程管理 AI 的规划器 (Planner)。

你的职责是分析用户的自然语言输入，拆解为具体的子任务。

## 你需要识别以下意图类型：
- CREATE_TASK: 创建新任务/行程
- QUERY_CALENDAR: 查询某时间段的安排
- UPDATE_TASK: 修改已有任务
- DELETE_TASK: 删除任务
- ARRANGE_TRIP: 安排出差/旅行
- DETECT_CONFLICT: 检查冲突
- RESOLVE_CONFLICT: 解决冲突
- GENERATE_TIMELINE: 生成时间线

## 输出格式（JSON）：
{
    "intent": "CREATE_TASK",
    "sub_tasks": [
        {"action": "check_calendar", "params": {"start": "2026-03-10", "end": "2026-03-15"}},
        {"action": "create_task", "params": {"title": "上海出差", "start": "2026-03-11T09:00", "end": "2026-03-11T18:00"}}
    ],
    "reasoning": "用户想安排上海出差，需要先查询已有安排再创建"
}
"""


async def planner_node(state: AgentState) -> dict[str, Any]:
    """
    Planner 节点

    输入：用户消息
    输出：意图分类 + 子任务列表
    """
    llm = get_llm_client()

    messages = [
        SystemMessage(content=PLANNER_SYSTEM_PROMPT),
        HumanMessage(content=state["user_input"]),
    ]

    try:
        response = await llm.ainvoke(messages)
        content = response.content

        # TODO: 解析 JSON 响应
        # 目前返回占位结果
        return {
            "intent": "CREATE_TASK",
            "sub_tasks": [
                {"action": "check_calendar", "params": {}},
                {"action": "parse_user_input", "params": {"input": state["user_input"]}},
            ],
        }
    except Exception as e:
        return {"error": str(e)}
