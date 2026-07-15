"""
User Profile — 长期人格/习惯/偏好 (带置信度)

表: user_profile
字段: user_id, key, value, confidence, source
"""
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

# 预定义的 profile key 分类
PROFILE_KEYS = {
    "communication": {
        "reply_style": "casual",         # casual / formal
        "reply_length": "short",         # short / detailed
        "emoji_usage": "medium",         # none / low / medium / high
    },
    "habit": {
        "wake_time": "07:30",
        "sleep_time": "23:00",
        "reminder_advance": "30min",     # 15min / 30min / 1hour
        "prefer_morning": "true",
    },
    "preference": {
        "likes_summary": "true",
        "likes_reminder": "true",
        "daily_brief_time": "08:00",
    },
}


class ProfileManager:
    """用户画像管理器 — 读/写/更新置信度"""

    @staticmethod
    async def get(user_id: int, key: str) -> dict | None:
        """读取单个 profile"""
        try:
            import asyncpg
            conn = await _get_pg_conn()
            row = await conn.fetchrow(
                "SELECT key, value, confidence, source FROM user_profile "
                "WHERE user_id=$1 AND key=$2", user_id, key
            )
            await conn.close()
            if row:
                return {"key": row["key"], "value": row["value"],
                        "confidence": row["confidence"], "source": row["source"]}
        except Exception as e:
            logger.warning(f"Profile read failed: {e}")
        return None

    @staticmethod
    async def set(user_id: int, key: str, value: str,
                  confidence: float = 0.5, source: str = "agent"):
        """写入/更新 profile"""
        try:
            conn = await _get_pg_conn()
            await conn.execute(
                "INSERT INTO user_profile (user_id, key, value, confidence, source) "
                "VALUES ($1,$2,$3,$4,$5) "
                "ON CONFLICT (user_id, key) DO UPDATE SET "
                "value=$3, confidence=$4, source=$5, updated_at=CURRENT_TIMESTAMP",
                user_id, key, value, confidence, source
            )
            await conn.close()
            logger.info(f"Profile set: {key}={value} (conf={confidence})")
        except Exception as e:
            logger.warning(f"Profile write failed: {e}")

    @staticmethod
    async def boost_confidence(user_id: int, key: str, delta: float = 0.1):
        """提升置信度 (用户多次确认)"""
        current = await ProfileManager.get(user_id, key)
        if current:
            new_conf = min(0.99, current["confidence"] + delta)
            await ProfileManager.set(user_id, key, current["value"], new_conf)

    @staticmethod
    async def get_all(user_id: int) -> dict:
        """读取用户全部画像"""
        try:
            conn = await _get_pg_conn()
            rows = await conn.fetch(
                "SELECT key, value, confidence FROM user_profile WHERE user_id=$1",
                user_id
            )
            await conn.close()
            return {r["key"]: {"value": r["value"], "confidence": r["confidence"]}
                    for r in rows}
        except Exception as e:
            logger.warning(f"Profile all read failed: {e}")
            return {}

    @staticmethod
    async def get_context_text(user_id: int) -> str:
        """生成注入到 System Prompt 的画像上下文"""
        profile = await ProfileManager.get_all(user_id)
        if not profile:
            return ""

        lines = ["[用户画像]"]
        for k, v in profile.items():
            if v["confidence"] >= 0.7:  # 只使用高置信度的画像
                lines.append(f"- {k}: {v['value']}")
        return "\n".join(lines) if len(lines) > 1 else ""


async def _get_pg_conn():
    """获取 PostgreSQL 连接"""
    import asyncpg
    from common.config import Settings
    s = Settings()
    return await asyncpg.connect(
        host=s.POSTGRES_HOST, port=s.POSTGRES_PORT,
        user=s.POSTGRES_USER, password=s.POSTGRES_PASSWORD,
        database=s.POSTGRES_DB, timeout=5,
    )


def _default_profile() -> dict:
    out = {}
    for category, items in PROFILE_KEYS.items():
        for k, v in items.items():
            out[f"{category}.{k}"] = {"value": v, "confidence": 0.5}
    return out
