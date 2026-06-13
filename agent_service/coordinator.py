"""
AI 协调决策模块

当检测到任务冲突时，调用 LLM 生成多方案建议
"""
from typing import Any
from common.models.conflict import ConflictDTO
from agent_service.llm.deepseek_client import chat_completion
from agent_service.llm.prompts import COORDINATOR_PROMPT


class AICoordinator:
    """AI 协调决策引擎"""

    @staticmethod
    async def resolve_conflicts(
        conflicts: list[ConflictDTO],
        user_preferences: str = "",
        user_feedback: str = "",
    ) -> dict[str, Any]:
        """
        对冲突列表进行 AI 协调，生成解决方案

        Args:
            conflicts: 冲突列表
            user_preferences: 用户偏好描述
            user_feedback: 用户对方案的补充意见

        Returns:
            AI 协调结果，包含多个方案
        """
        # 构建冲突描述
        conflict_descriptions = []
        for c in conflicts:
            desc = (
                f"冲突 {c.id}: "
                f"「{c.task_a_title}」与「{c.task_b_title}」"
                f" 在 {c.overlap_start} ~ {c.overlap_end} 重叠"
                f"（严重程度: {c.severity}）"
            )
            conflict_descriptions.append(desc)

        conflict_info = "\n".join(conflict_descriptions)

        # 构建提示词
        prompt = COORDINATOR_PROMPT.format(
            conflict_info=conflict_info,
            user_preferences=user_preferences + "\n用户补充意见: " + (user_feedback or "无"),
        )

        messages = [
            {"role": "system", "content": prompt},
            {"role": "user", "content": "请分析以上冲突并给出解决方案。"},
        ]

        try:
            response = await chat_completion(messages, temperature=0.7)
            # TODO: 解析 JSON 响应
            return {
                "raw_response": response,
                "suggestions": [],
                "reasoning": "",
            }
        except Exception as e:
            return {"error": str(e), "suggestions": [], "reasoning": ""}

    @staticmethod
    def calculate_priority_score(task: dict) -> float:
        """
        计算任务优先级评分（用于规则引擎回退方案）

        权重分配：
        - 优先级 40%
        - 参与人数 20%
        - 是否外部客户 20%
        - 是否可调整 20%
        """
        priority_weight = {"HIGH": 1.0, "MEDIUM": 0.6, "LOW": 0.3}
        score = 0.0

        score += priority_weight.get(task.get("priority", "MEDIUM"), 0.6) * 0.4
        # TODO: 补充其他维度的计算
        return score
