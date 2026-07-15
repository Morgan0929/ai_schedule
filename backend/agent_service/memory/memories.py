"""
User Memory — 通用记忆 (habit/event/preference/fact)

表: user_memory
字段: memory_type, content, importance, confidence, expire_at
"""
import logging
from datetime import datetime, timedelta

logger = logging.getLogger(__name__)

# 什么值得保存
SAVE_RULES = {
    "habit": ["每天", "每周", "经常", "总是", "习惯", "通常", "一般都会", "规律"],
    "preference": ["喜欢", "偏好", "想要", "希望", "比较习惯", "更愿意"],
    "fact": ["我的", "我在", "我住", "我电话", "我学号"],
    "event": ["考试", "答辩", "面试", "旅行", "出差", "搬家"],
}

# 什么不保存
SKIP_RULES = [
    "好累", "困了", "烦", "不想", "随便", "无所谓",
    "今天天气", "开玩笑", "测试", "哈哈", "嗯", "哦",
]


class MemoryManager:
    """通用记忆管理器"""

    @staticmethod
    async def save(
        user_id: int, memory_type: str, content: str,
        importance: float = 0.5, confidence: float = 0.5,
        source: str = "agent", expire_days: int = None,
    ) -> int | None:
        """保存一条记忆"""
        try:
            import asyncpg
            from agent_service.memory.profile import _get_pg_conn

            expire_at = None
            if expire_days:
                expire_at = datetime.now() + timedelta(days=expire_days)

            conn = await _get_pg_conn()
            row = await conn.fetchrow(
                "INSERT INTO user_memory (user_id, memory_type, content, "
                "importance, confidence, source, expire_at) "
                "VALUES ($1,$2,$3,$4,$5,$6,$7) RETURNING id",
                user_id, memory_type, content, importance, confidence, source, expire_at
            )
            await conn.close()
            mem_id = row["id"] if row else None
            logger.info(f"Memory saved: [{memory_type}] {content[:60]} (imp={importance})")
            return mem_id
        except Exception as e:
            logger.warning(f"Memory save failed: {e}")
            return None

    @staticmethod
    async def query(
        user_id: int, memory_type: str = None,
        min_importance: float = 0.3, limit: int = 20,
    ) -> list[dict]:
        """查询记忆"""
        try:
            from agent_service.memory.profile import _get_pg_conn
            conn = await _get_pg_conn()

            query = ("SELECT id, memory_type, content, importance, confidence, expire_at "
                     "FROM user_memory WHERE user_id=$1 AND is_active=true "
                     "AND importance >= $2 AND (expire_at IS NULL OR expire_at > NOW())")
            params = [user_id, min_importance]

            if memory_type:
                query += " AND memory_type=$3"
                params.append(memory_type)

            query += " ORDER BY importance DESC, created_at DESC LIMIT $4"
            params.append(limit)

            rows = await conn.fetch(query, *params)
            await conn.close()
            return [{"id": r["id"], "type": r["memory_type"], "content": r["content"],
                     "importance": r["importance"], "confidence": r["confidence"]}
                    for r in rows]
        except Exception as e:
            logger.warning(f"Memory query failed: {e}")
            return []

    @staticmethod
    async def should_save(text: str) -> tuple[bool, str | None, float]:
        """
        判断一段文本是否值得保存为记忆

        Returns: (should_save, memory_type, importance)
        """
        # 检查是否在不保存列表中
        for skip in SKIP_RULES:
            if skip in text:
                return False, None, 0.0

        # 按优先级匹配
        for mem_type, keywords in SAVE_RULES.items():
            for kw in keywords:
                if kw in text:
                    importance = 0.8 if mem_type in ("habit", "event") else 0.5
                    return True, mem_type, importance

        return False, None, 0.0

    @staticmethod
    async def extract_from_conversation(user_input: str, ai_reply: str) -> list[dict]:
        """从对话中提取值得保存的记忆片段"""
        memories = []

        # 检查用户输入
        should_save, mem_type, importance = await MemoryManager.should_save(user_input)
        if should_save and mem_type:
            memories.append({
                "type": mem_type, "content": user_input[:500],
                "importance": importance, "confidence": 0.5,
            })

        return memories
