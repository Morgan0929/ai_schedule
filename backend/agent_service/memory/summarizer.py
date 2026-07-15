"""
Summary Node — 对话摘要提取 (结构化, 不污染人格)

架构:
  Messages → Token Counter → 超过阈值 → Summary Node → 结构化摘要
  摘要 ≠ 聊天记录 — 只提取事实/任务/偏好, 丢弃情绪/闲聊
"""
import json
import logging
from datetime import datetime
from typing import Any
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

# 触发阈值
SUMMARY_TOKEN_THRESHOLD = 6000


class ConversationSummary(BaseModel):
    """结构化对话摘要 — Summary Node 输出"""

    unfinished_tasks: list[str] = Field(
        default_factory=list,
        description="当前未完成的任务 (如 '提交论文', '准备考试')"
    )
    events: list[str] = Field(
        default_factory=list,
        description="重要事件 (如 '7月20日期末考试', '下周五项目答辩')"
    )
    user_preferences: list[str] = Field(
        default_factory=list,
        description="用户偏好 (如 '喜欢提前30分钟提醒', '偏好简洁回复')"
    )
    important_facts: list[str] = Field(
        default_factory=list,
        description="重要事实 (如 '每周一9点有数学课', '学号是2024001')"
    )
    discard: list[str] = Field(
        default_factory=list,
        description="摘要时丢弃的低价值信息 (闲聊/情绪/一次性) — 仅记录, 不保存"
    )
    summary_text: str = Field(
        default="",
        description="一句话摘要, 注入到 System Prompt 后方"
    )


# Summary Node 的 ChatPromptTemplate
SUMMARY_PROMPT_TEMPLATE = """你是林的记忆整理助手。

请从以下对话中提取结构化信息:

对话内容:
{conversation_text}

## 提取规则
1. unfinished_tasks: 用户提到但尚未完成的任务
2. events: 有明确时间的重要事件 (考试/会议/旅行/答辩等)
3. user_preferences: 用户表达的习惯/偏好/沟通风格
4. important_facts: 需要长期记住的事实 (课程/地点/联系方式等)
5. discard: 对话中的闲聊/情绪表达/一次性信息 (这些不需要保存)

## 不记录
- 闲聊 (谢谢/哈哈/好的)
- 情绪表达 (好累/困了/烦)
- 一次性信息 (今天天气真好)
- 工具返回的原始数据

## 输出 JSON
{{"unfinished_tasks": ["..."], "events": ["..."], "user_preferences": ["..."], "important_facts": ["..."], "discard": ["..."], "summary_text": "一句话摘要"}}
"""


class SummaryNode:
    """
    摘要节点 — 从对话中提取结构化知识

    用法:
        summary = await SummaryNode.summarize(messages)
        # → ConversationSummary 实例
    """

    @staticmethod
    async def summarize(messages: list, user_id: int = 0) -> ConversationSummary | None:
        """
        对消息列表进行结构化摘要

        Args:
            messages: LangChain Message 列表
            user_id: 用户 ID

        Returns:
            ConversationSummary 或 None
        """
        # 提取纯文本
        conversation_text = _messages_to_text(messages[-50:])  # 只摘要最近50条

        if len(conversation_text) < 100:
            return None  # 太短不摘要

        # LLM 提取
        from agent_service.llm.deepseek_client import is_llm_available, get_structured_llm

        if not is_llm_available():
            return None

        prompt = SUMMARY_PROMPT_TEMPLATE.format(conversation_text=conversation_text[:4000])

        try:
            llm = get_structured_llm(ConversationSummary)
            result = await llm.ainvoke(prompt)
            if isinstance(result, ConversationSummary):
                logger.info(
                    f"Summary: {len(result.unfinished_tasks)} tasks, "
                    f"{len(result.events)} events, {len(result.important_facts)} facts"
                )
                return result
        except Exception as e:
            logger.warning(f"Summary LLM failed: {e}")
        return None

    @staticmethod
    async def save_to_db(user_id: int, summary: ConversationSummary):
        """将摘要持久化到 PostgreSQL"""
        if not summary or not summary.summary_text:
            return

        try:
            import asyncpg
            from common.config import Settings
            s = Settings()

            conn = await asyncpg.connect(
                host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
                user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD,
                database=s.POSTGRES_DB, timeout=5,
            )

            today = datetime.now().date().isoformat()
            content = json.dumps(summary.model_dump(), ensure_ascii=False)

            await conn.execute(
                "INSERT INTO conversation_summary (user_id, date, summary, event_count) "
                "VALUES ($1, $2, $3, $4) "
                "ON CONFLICT (user_id, date) DO UPDATE SET "
                "summary=$3, event_count=$4, created_at=CURRENT_TIMESTAMP",
                user_id, today, content,
                len(summary.events) + len(summary.unfinished_tasks)
            )
            await conn.close()
            logger.info(f"Summary saved to PG for user {user_id}")
        except Exception as e:
            logger.warning(f"Summary save failed: {e}")

    @staticmethod
    async def load_recent(user_id: int, days: int = 7) -> str:
        """加载最近 N 天的摘要文本, 注入到 System Prompt"""
        try:
            import asyncpg
            from common.config import Settings
            s = Settings()

            conn = await asyncpg.connect(
                host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
                user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD,
                database=s.POSTGRES_DB, timeout=5,
            )

            rows = await conn.fetch(
                "SELECT summary FROM conversation_summary "
                "WHERE user_id=$1 AND date >= CURRENT_DATE - $2::INTEGER "
                "ORDER BY date DESC",
                user_id, days
            )
            await conn.close()

            if not rows:
                return ""

            texts = []
            for r in rows:
                try:
                    data = json.loads(r["summary"])
                    texts.append(data.get("summary_text", ""))
                except Exception:
                    pass

            if texts:
                return "[近期摘要]\n" + "\n".join(f"- {t}" for t in texts[:7])
        except Exception as e:
            logger.warning(f"Summary load failed: {e}")
        return ""


def _messages_to_text(messages: list) -> str:
    """Message 列表 → 纯文本"""
    lines = []
    for msg in messages:
        role = getattr(msg, "type", "unknown")
        content = getattr(msg, "content", str(msg))
        if isinstance(content, str):
            lines.append(f"[{role}] {content[:200]}")
    return "\n".join(lines)


def estimate_tokens(messages: list) -> int:
    """
    估算消息列表的 token 数

    粗略规则: 1 个中文字 ≈ 1.5 tokens, 1 个英文词 ≈ 1.3 tokens
    """
    total = 0
    for msg in messages:
        content = getattr(msg, "content", str(msg))
        if isinstance(content, str):
            # 简单估算: 字符数 / 1.5
            total += len(content) // 2
        elif isinstance(content, list):
            # 多模态消息
            for part in content:
                if isinstance(part, dict):
                    total += len(str(part.get("text", ""))) // 2
    return total


def should_summarize(messages: list, threshold: int = SUMMARY_TOKEN_THRESHOLD) -> bool:
    """是否需要触发摘要"""
    return estimate_tokens(messages) > threshold
