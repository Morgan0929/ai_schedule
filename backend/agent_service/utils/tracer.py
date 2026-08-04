"""
AI Trace 日志系统 — 双层记录

本地:  控制台实时输出 + PostgreSQL agent_session 表
云端:  LangSmith (飞行记录仪 — 不依赖它运行核心功能)

记录每次 Agent 对话的完整链路:
- 用户输入
- Planner 意图识别
- 工具调用 (哪个工具/参数/结果)
- 冲突检测结果
- Coordinator 协调方案
- 最终回复
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


# ============ LangSmith 飞行记录仪 ============

def _get_langsmith_client():
    """获取 LangSmith 客户端（不影响核心功能，失败了就当不存在）"""
    try:
        from common.config import settings
        if not settings.LANGCHAIN_API_KEY:
            return None

        from langsmith import Client
        return Client(api_key=settings.LANGCHAIN_API_KEY)
    except Exception:
        return None


def _send_to_langsmith(trace_id: str, summary: dict):
    """
    异步发送 Trace 到 LangSmith

    这是"飞行记录仪"——只记录，不影响飞行。
    失败了就静默忽略，不让 LangSmith 成为单点故障。
    """
    try:
        client = _get_langsmith_client()
        if not client:
            return

        # 创建 Run
        run = client.create_run(
            name=f"Lin-Chat-{trace_id}",
            run_type="chain",
            inputs={"user_input": summary.get("user_input", "")},
            outputs={"reply": summary.get("final_reply", "")[:500]},
            project_name="lin-ai-secretary",
            tags=["agent", "lin"],
            extra={
                "session_id": summary.get("session_id", ""),
                "user_id": summary.get("user_id", 0),
                "steps": summary.get("steps", []),
                "total_ms": summary.get("total_ms", 0),
            },
        )
        logger.debug(f"LangSmith run: {run.id}")
    except Exception:
        pass  # 飞行记录仪故障不影响飞行


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

        # 异步存入数据库 + LangSmith 飞行记录仪（不阻塞回复）
        import asyncio
        asyncio.create_task(self._persist(summary))
        # LangSmith 后台发送 —— 失败了不影响用户
        try:
            loop = asyncio.get_running_loop()
            loop.run_in_executor(None, _send_to_langsmith, self.trace_id, summary)
        except RuntimeError:
            pass

        return summary

    async def _persist(self, summary: dict):
        """持久化到 PostgreSQL"""
        try:
            from common.database import async_session_factory
            from sqlalchemy import text

            async with async_session_factory() as db:
                await db.execute(text("""
                    INSERT INTO agent_session (id, user_id, title, messages, agent_state, is_active)
                    VALUES (:id, :user_id, :title, :messages::jsonb, :state::jsonb, true)
                    ON CONFLICT (id) DO UPDATE SET
                        messages = agent_session.messages || :append_msg::jsonb,
                        agent_state = :state::jsonb,
                        updated_at = CURRENT_TIMESTAMP
                """), {
                    "id": uuid.UUID(self.session_id) if len(self.session_id) == 36 else uuid.uuid4(),
                    "user_id": self.user_id,
                    "title": self.user_input[:100],
                    "messages": [{"role": "user", "content": self.user_input}],
                    "append_msg": [{"role": "assistant", "content": summary["final_reply"][:500]}],
                    "state": summary,
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
