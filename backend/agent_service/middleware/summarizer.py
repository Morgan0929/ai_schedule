"""
Chat Summarizer — 长对话历史压缩

林的秘书会长期聊天 (几千轮)，不能全部塞给模型。
策略: 最近 N 轮 + 历史摘要 + 用户画像

类似 Java: 滑动窗口 + 摘要缓存
"""
import json
from datetime import datetime
from typing import Any

MAX_RECENT_MESSAGES = 20  # 保留最近 20 条消息
SUMMARY_INTERVAL = 10      # 每 10 轮生成一次摘要


class ChatSummarizer:
    """
    对话摘要器

    用法:
        summarizer = ChatSummarizer()
        compressed = await summarizer.compress(messages)
        # compressed = [SystemMessage(摘要), ...最近20条...]
    """

    def __init__(self):
        self._summary: str = ""
        self._compressed_count: int = 0
        self._user_profile: dict[str, Any] = {}

    def should_compress(self, message_count: int) -> bool:
        """消息数超过阈值时需要压缩"""
        return message_count > MAX_RECENT_MESSAGES + SUMMARY_INTERVAL

    async def compress(self, messages: list) -> list:
        """
        压缩消息列表

        保留: 最近 MAX_RECENT_MESSAGES 条
        压缩: 更早的消息 → 摘要
        """
        if len(messages) <= MAX_RECENT_MESSAGES:
            return messages

        recent = messages[-MAX_RECENT_MESSAGES:]
        old = messages[:-MAX_RECENT_MESSAGES]

        # 提取旧消息中的关键信息
        extracted = self._extract_info(old)
        if extracted:
            self._summary = self._build_summary(extracted)
            self._compressed_count += len(old)

        # 在最近消息前插入摘要
        from langchain_core.messages import SystemMessage
        result = list(recent)
        if self._summary:
            result.insert(0, SystemMessage(
                content=f"[历史摘要] {self._summary}"
            ))
        return result

    def _extract_info(self, messages: list) -> list[dict]:
        """从历史消息中提取关键信息"""
        info = []
        for msg in messages[-100:]:  # 只处理最近100条旧消息
            content = getattr(msg, "content", str(msg))
            if not isinstance(content, str):
                continue
            content_lower = content.lower()
            # 提取任务相关
            if any(kw in content_lower for kw in
                   ["任务", "提醒", "安排", "会议", "课程", "作业", "截止", "deadline"]):
                info.append({"type": "task", "text": content[:200]})
            # 提取偏好
            if any(kw in content_lower for kw in
                   ["习惯", "偏好", "通常", "每天", "每周", "总是"]):
                info.append({"type": "preference", "text": content[:200]})
                self._update_profile(content)
        return info

    def _build_summary(self, extracted: list[dict]) -> str:
        """构建文本摘要"""
        tasks = [e for e in extracted if e["type"] == "task"]
        prefs = [e for e in extracted if e["type"] == "preference"]

        parts = []
        if tasks:
            parts.append(f"历史任务({len(tasks)}条)")
        if prefs:
            parts.append(f"用户偏好({len(prefs)}条)")
        if self._user_profile:
            profile_str = json.dumps(self._user_profile, ensure_ascii=False)
            parts.append(f"用户画像: {profile_str}")

        return " | ".join(parts) if parts else ""

    def _update_profile(self, text: str):
        """更新用户画像"""
        # 简单关键词提取
        patterns = {
            "reminder_preference": ["提前", "提醒"],
            "morning_person": ["早上", "上午", "早起"],
            "evening_person": ["晚上", "深夜"],
            "prefer_brief": ["简洁", "简短", "不要啰嗦"],
        }
        for key, kws in patterns.items():
            if any(kw in text for kw in kws):
                self._user_profile[key] = True

    @property
    def summary(self) -> str:
        return self._summary

    @property
    def profile(self) -> dict:
        return self._user_profile
