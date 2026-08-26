import asyncio
import sys
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_service.utils import tracer


class _FakeGovernor:
    def submit(self, coro, *, name="agent-bg"):
        coro.close()
        return None


class _FakeLoop:
    def run_in_executor(self, *args, **kwargs):
        return None


def test_agent_tracer_finish_does_not_fail_when_event_loop_is_available():
    fake_loop = _FakeLoop()
    with patch.object(tracer, "BACKGROUND_TASK_GOVERNOR", _FakeGovernor()), patch.object(
        tracer.asyncio, "get_running_loop", return_value=fake_loop
    ):
        item = tracer.AgentTracer("session-1", 3, "测试追踪")
        item.add_step("reply", output_data={"reply": "ok"})
        summary = item.finish("ok")

    assert summary["final_reply"] == "ok"
    assert summary["success"] is True
