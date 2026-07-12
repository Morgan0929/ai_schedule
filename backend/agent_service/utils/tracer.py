"""
AI Trace 日志系统

记录每次 Agent 对话的完整链路:
- 用户输入
- Planner 意图识别
- 工具调用 (哪个工具/参数/结果)
- 冲突检测结果
- Coordinator 协调方案
- 最终回复

存入 PostgreSQL agent_session 表 + agent_trace 表
用于排查"AI 为什么这样安排？"
"""
import json
import logging
import time
import uuid
from datetime import datetime
from typing import Any
from dataclasses import dataclass, field, asdict

logger = logging.getLogger("ai_trace")

# 是否同时输出到控制台
CONSOLE_TRACE = True


@dataclass
class TraceStep:
    """Agent 执行链路中的一个步骤"""
    step: str                     # planner / tools / conflict / coordinator / reply
    timestamp: str = field(default_factory=lambda: datetime.now().isoformat())
    duration_ms: float = 0.0
    input_data: dict = field(default_factory=dict)
    output_data: dict = field(default_factory=dict)
    success: bool = True
    error: str = ""


class AgentTracer:
    """Agent 链路追踪器 — 每次对话创建一个实例"""

    def __init__(self, session_id: str, user_id: int, user_input: str):
        self.trace_id = str(uuid.uuid4())[:12]
        self.session_id = session_id
        self.user_id = user_id
        self.user_input = user_input
        self.steps: list[TraceStep] = []
        self.start_time = time.time()

        if CONSOLE_TRACE:
            print(f"\n{'='*60}")
            print(f"[Trace:{self.trace_id}] 会话开始 — user={user_id}")
            print(f"[Trace:{self.trace_id}] 用户输入: {user_input[:200]}")
            print(f"{'='*60}")

    def add_step(self, step_name: str, input_data: dict = None,
                 output_data: dict = None, success: bool = True,
                 error: str = "", duration_ms: float = 0.0):
        """记录一个执行步骤"""
        step = TraceStep(
            step=step_name,
            input_data=input_data or {},
            output_data=output_data or {},
            success=success,
            error=error,
            duration_ms=duration_ms or self._elapsed(),
        )
        self.steps.append(step)

        if CONSOLE_TRACE:
            status = "OK" if success else "FAIL"
            icon = {"planner": "[Plan]", "tools": "[Tool]", "conflict": "[Conflict]",
                    "coordinator": "[Coord]", "reply": "[Reply]"}.get(step_name, "[Step]")
            print(f"[Trace:{self.trace_id}] {icon} {step_name:12s} [{status}] "
                  f"{step.duration_ms:.0f}ms")
            if output_data:
                brief = json.dumps(output_data, ensure_ascii=False)[:150]
                print(f"    → {brief}")

    def finish(self, final_reply: str):
        """标记追踪完成"""
        total_ms = (time.time() - self.start_time) * 1000

        summary = {
            "trace_id": self.trace_id,
            "session_id": self.session_id,
            "user_id": self.user_id,
            "user_input": self.user_input[:500],
            "steps": [asdict(s) for s in self.steps],
            "final_reply": final_reply[:1000],
            "total_ms": round(total_ms, 1),
            "step_count": len(self.steps),
            "success": all(s.success for s in self.steps),
        }

        if CONSOLE_TRACE:
            print(f"{'='*60}")
            print(f"[Trace:{self.trace_id}] 会话结束 — {len(self.steps)}步 "
                  f"耗时{total_ms:.0f}ms "
                  f"{'OK' if summary['success'] else 'FAIL'}")
            print(f"{'='*60}\n")

        # 异步存入数据库（不阻塞回复）
        import asyncio
        asyncio.create_task(self._persist(summary))

        return summary

    async def _persist(self, summary: dict):
        """持久化到 PostgreSQL"""
        try:
            from common.database import async_session_factory
            from sqlalchemy import text

            async with async_session_factory() as db:
                await db.execute(text("""
                    INSERT INTO agent_session (id, user_id, title, messages, agent_state, is_active)
                    VALUES (:id, :user_id, :title, :messages, :state, true)
                    ON CONFLICT (id) DO UPDATE SET
                        messages = agent_session.messages || :append_msg,
                        agent_state = :state,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "id": uuid.UUID(self.session_id) if len(self.session_id) == 36 else uuid.uuid4(),
                    "user_id": self.user_id,
                    "title": self.user_input[:100],
                    "messages": json.dumps([{"role": "user", "content": self.user_input}]),
                    "append_msg": json.dumps([{"role": "assistant", "content": summary["final_reply"][:500]}]),
                    "state": json.dumps(summary, ensure_ascii=False),
                })
                await db.commit()
                logger.info(f"Trace {self.trace_id} persisted to PostgreSQL")
        except Exception as e:
            logger.warning(f"Trace persist failed (non-critical): {e}")

    def _elapsed(self) -> float:
        return (time.time() - self.start_time) * 1000


# 全局快捷函数
def start_trace(session_id: str, user_id: int, user_input: str) -> AgentTracer:
    return AgentTracer(session_id, user_id, user_input)
