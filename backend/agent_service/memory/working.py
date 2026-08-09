"""
Working Memory — 当前对话状态 (Redis)

生命周期: 单次会话, 会话结束即清除
存储: Redis (key: working:mem:{session_id}, TTL=30min)
内容: intent, entities, tool_calls, partial_results
"""
import json
import logging
from datetime import datetime

logger = logging.getLogger(__name__)

WORKING_TTL = 1800  # 30 分钟


class WorkingMemory:
    """工作记忆 — 当前对话的上下文"""

    @staticmethod
    async def save(session_id: str, key: str, value: any):
        """保存工作记忆片段"""
        try:
            from common.redis_client import get_redis
            redis = await get_redis()
            rkey = f"working:mem:{session_id}"
            data = await redis.get(rkey) or "{}"
            mem = json.loads(data) if isinstance(data, (str, bytes)) else {}
            mem[key] = value
            mem["_updated"] = datetime.now().isoformat()
            await redis.setex(rkey, WORKING_TTL, json.dumps(mem, ensure_ascii=False))
        except Exception as e:
            logger.debug(f"Working memory save failed (non-critical): {e}")

    @staticmethod
    async def get(session_id: str, key: str = None) -> dict | None:
        """读取工作记忆"""
        try:
            from common.redis_client import get_redis
            redis = await get_redis()
            rkey = f"working:mem:{session_id}"
            data = await redis.get(rkey)
            if not data:
                return None
            mem = json.loads(data) if isinstance(data, (str, bytes)) else {}
            if key:
                return mem.get(key)
            return mem
        except Exception as e:
            logger.debug(f"Working memory read failed: {e}")
            return None

    @staticmethod
    async def delete_key(session_id: str, key: str):
        """删除工作记忆中的某个 key"""
        try:
            from common.redis_client import get_redis
            redis = await get_redis()
            rkey = f"working:mem:{session_id}"
            data = await redis.get(rkey)
            if data:
                mem = json.loads(data) if isinstance(data, (str, bytes)) else {}
                mem.pop(key, None)
                if mem:
                    mem["_updated"] = datetime.now().isoformat()
                    await redis.setex(rkey, WORKING_TTL, json.dumps(mem, ensure_ascii=False))
                else:
                    await redis.delete(rkey)
        except Exception as e:
            logger.debug(f"Working memory delete_key failed: {e}")

    @staticmethod
    async def clear(session_id: str):
        """清除工作记忆"""
        try:
            from common.redis_client import get_redis
            redis = await get_redis()
            await redis.delete(f"working:mem:{session_id}")
        except Exception:
            pass
