"""
Message Pruner — 分层裁剪 + 重要消息保护

策略:
  Layer 1: System Prompt       → 永久保留
  Layer 2: User Profile        → 永久保留
  Layer 3: Important Facts     → 永不裁剪
  Layer 4: Recent Summary      → 注入当前窗口
  Layer 5: Recent Messages     → 保留最近 20 轮 (40 条)
  Layer 6: Tool Results        → 执行后转为事件, 丢弃原始数据
  Layer 7: Low-value Chat      → 直接丢弃

触发: token > 6000 → Summary Node → 裁剪
"""
import logging
from typing import Any

logger = logging.getLogger(__name__)

# 保留窗口大小
MAX_RECENT_ROUNDS = 20       # 最近 20 轮对话
MAX_TOOL_RESULTS = 5         # 最多保留 5 条工具结果
SUMMARY_INTERVAL = 10        # 每 10 轮触发一次摘要检查


# 低价值消息关键词 (直接丢弃)
LOW_VALUE_PATTERNS = [
    "谢谢", "哈哈", "好的", "嗯", "哦", "知道了", "OK", "ok",
    "没事", "不用", "随便", "无所谓",
]


def score_message(content: str) -> float:
    """
    消息重要性评分 (0.0 ~ 1.0)

    高分:
      - 用户习惯 (每天/每周/总是) → 0.95
      - 长期目标                  → 0.90
      - 固定安排                  → 0.85
      - 偏好表达                  → 0.70

    低分:
      - 闲聊                      → 0.05
      - 情绪表达                  → 0.10
      - 工具调用                   → 0.30
      - 一次性信息                 → 0.20
    """
    if not isinstance(content, str):
        return 0.3  # 非文本消息 (Tool Result 等)

    score = 0.3  # baseline

    # 高分信号
    high_signals = {
        "每天": 0.20, "每周": 0.20, "总是": 0.15, "习惯": 0.15,
        "提醒": 0.10, "截止": 0.15, "考试": 0.15, "答辩": 0.15,
        "安排": 0.10, "重要": 0.10, "必须": 0.10,
        "喜欢": 0.10, "偏好": 0.10, "不希望": 0.10,
        "固定": 0.15, "规律": 0.15,
    }
    for kw, boost in high_signals.items():
        if kw in content:
            score += boost

    # 低分信号
    low_signals = ["哈哈", "好的", "嗯", "哦", "谢谢", "知道了"]
    for kw in low_signals:
        if kw == content.strip():
            score = 0.05
            break

    return min(0.99, score)


def is_low_value(content: str) -> bool:
    """是否为低价值消息 (可丢弃)"""
    if not isinstance(content, str):
        return False
    content = content.strip()
    if len(content) <= 3:
        return any(p in content for p in LOW_VALUE_PATTERNS)
    return False


def is_tool_message(msg) -> bool:
    """是否为工具消息"""
    msg_type = getattr(msg, "type", "")
    return msg_type == "tool" or "ToolMessage" in str(type(msg))


def is_system_message(msg) -> bool:
    """是否为系统消息 (永久保留)"""
    msg_type = getattr(msg, "type", "")
    return msg_type == "system" or "SystemMessage" in str(type(msg))


def prune_messages(
    messages: list,
    max_recent: int = MAX_RECENT_ROUNDS * 2,  # 20轮 = 40条
    keep_important: bool = True,
) -> list:
    """
    分层裁剪消息列表

    Returns:
        裁剪后的消息列表 (System + 重要事实 + 最近 N 条)
    """
    if len(messages) <= max_recent:
        return messages

    # 1. System messages → 永远保留
    system_msgs = [m for m in messages if is_system_message(m)]

    # 2. 重要消息 → 保护 (score > 0.7)
    important = []
    if keep_important:
        for m in messages:
            content = getattr(m, "content", "")
            if isinstance(content, str) and score_message(content) > 0.7:
                important.append(m)

    # 3. 最近 N 条
    non_system = [m for m in messages if not is_system_message(m)]
    recent = non_system[-max_recent:]

    # 4. 合并: System + 重要(排除已在recent中的) + Recent
    important_filtered = [m for m in important if m not in recent]
    result = system_msgs + important_filtered + recent

    logger.info(
        f"Pruned: {len(messages)} → {len(result)} "
        f"(system={len(system_msgs)} important={len(important_filtered)} "
        f"recent={len(recent)})"
    )
    return result


def filter_tool_messages(messages: list, keep_last: int = MAX_TOOL_RESULTS) -> list:
    """
    过滤工具消息 — 只保留最近 N 条, 其余丢弃
    """
    tool_indices = [i for i, m in enumerate(messages) if is_tool_message(m)]
    if len(tool_indices) <= keep_last:
        return messages

    # 保留最近 N 条, 移除其余
    to_keep = set(tool_indices[-keep_last:])
    return [m for i, m in enumerate(messages)
            if not is_tool_message(m) or i in to_keep]
