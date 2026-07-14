"""
Todo Extractor — 从对话中提取待办事项

因为林本质是 Personal Task Manager，
从用户输入中自动识别任务/截止时间/优先级应该是核心能力。

类似 Java: NLP Entity Extractor
"""
import json
import logging
from datetime import datetime
from typing import Any

logger = logging.getLogger(__name__)


class TodoExtractor:
    """
    待办提取器

    用法:
        todos = await TodoExtractor.extract(user_input)
        # [{"task": "提交数学作业", "deadline": "Friday", "priority": "HIGH"}, ...]
    """

    @staticmethod
    async def extract(user_input: str, llm_call=None) -> list[dict]:
        """
        从用户输入中提取待办事项

        Args:
            user_input: 用户输入文本
            llm_call:   可选的 LLM 调用函数

        Returns:
            待办列表
        """
        # 规则引擎快速提取
        rule_result = TodoExtractor._rule_extract(user_input)
        if rule_result:
            return rule_result

        # LLM 提取
        if llm_call:
            return await TodoExtractor._llm_extract(user_input, llm_call)

        return []

    @staticmethod
    def _rule_extract(text: str) -> list[dict] | None:
        """规则引擎提取 — 无需 LLM"""
        import re
        todos = []

        # 模式: "提交/完成/交 + 名词 + 截止时间"
        patterns = [
            (r'(?:提交|完成|交|做|写|准备)(.{2,20}?)(?:，|。|$|截止|之前|周五|周一|下周|明天|今天)', "MEDIUM"),
            (r'(?:记得|别忘了|不要忘了)(.{2,30}?)(?:，|。|$)', "HIGH"),
            (r'(?:考试|期末|答辩|面试)(.{2,20}?)(?:，|。|$|在|于)', "HIGH"),
        ]

        for pattern, priority in patterns:
            matches = re.findall(pattern, text)
            for m in matches:
                task = m.strip().strip("，。！。")
                if len(task) >= 2:
                    todos.append({"task": task, "priority": priority, "source": "rule"})

        # 提取截止时间
        time_keywords = {
            "今天": datetime.now().strftime("%Y-%m-%d"),
            "明天": "tomorrow",
            "周五": "Friday",
            "下周": "next week",
        }
        for kw, val in time_keywords.items():
            if kw in text:
                for todo in todos:
                    if "deadline" not in todo:
                        todo["deadline"] = val

        return todos if todos else None

    @staticmethod
    async def _llm_extract(text: str, llm_call) -> list[dict]:
        """LLM 提取"""
        from agent_service.llm.deepseek_client import is_llm_available, get_structured_llm
        if not is_llm_available():
            return []

        from pydantic import BaseModel, Field

        class TodoList(BaseModel):
            items: list[dict] = Field(default_factory=list)

        prompt = (
            f"从以下用户输入中提取待办事项。每个事项包含 task(任务名)、"
            f"deadline(截止时间, 没有则为null)、priority(HIGH/MEDIUM/LOW)。"
            f"只返回 JSON: {text[:500]}"
        )
        try:
            llm = get_structured_llm(TodoList)
            result = await llm.ainvoke(prompt)
            if hasattr(result, "items"):
                return result.items
        except Exception as e:
            logger.warning(f"LLM todo extraction failed: {e}")
        return []

    @staticmethod
    def merge_todos(existing: list[dict], new: list[dict]) -> list[dict]:
        """合并待办列表，去重"""
        seen = set()
        merged = []
        for todo in new + existing:
            key = todo.get("task", "")[:30]
            if key and key not in seen:
                seen.add(key)
                merged.append(todo)
        return merged
