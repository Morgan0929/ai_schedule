"""
Tool Call Limit — 防止 Agent 死循环烧 Token

类似 Java @RateLimiter 或 Spring Retry maxAttempts
"""
import logging

logger = logging.getLogger(__name__)

MAX_TOOL_CALLS = 5  # 单次对话最多 5 次工具调用


class ToolCallLimiter:
    """
    工具调用限流器

    用法:
        limiter = ToolCallLimiter()
        if not limiter.allow(): return "已达最大工具调用次数"
        limiter.record_tool_call("create_task")
    """

    def __init__(self, max_calls: int = MAX_TOOL_CALLS):
        self.max_calls = max_calls
        self.count = 0
        self.history: list[str] = []

    def allow(self) -> bool:
        return self.count < self.max_calls

    def record(self, tool_name: str):
        self.count += 1
        self.history.append(tool_name)
        if self.count >= self.max_calls:
            logger.warning(
                f"ToolCallLimit reached: {self.count}/{self.max_calls}. "
                f"History: {self.history}"
            )

    def remaining(self) -> int:
        return max(0, self.max_calls - self.count)

    @property
    def limit_hit(self) -> bool:
        return self.count >= self.max_calls


# 集成到 AgentState: state["tool_calls_count"]
def check_tool_limit(state: dict) -> bool:
    """检查 state 中的工具调用计数是否超限"""
    return state.get("tool_calls_count", 0) < MAX_TOOL_CALLS


def increment_tool_count(state: dict, tool_name: str = ""):
    """递增工具调用计数"""
    count = state.get("tool_calls_count", 0) + 1
    state["tool_calls_count"] = count
    history = state.get("_tool_history", [])
    history.append(tool_name)
    state["_tool_history"] = history
