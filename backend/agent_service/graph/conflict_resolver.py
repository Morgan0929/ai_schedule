"""
Conflict Resolver Node — 处理用户对冲突方案的选择 (A/B/C)

流程: check_pending_action → 有pending → conflict_resolver
"""
from typing import Any


async def conflict_resolver_node(state: dict) -> dict[str, Any]:
    """解析用户选择, 执行对应操作"""
    pending = state.get("pending_action", {})
    user_input = state.get("user_input", "").strip().upper()
    options = pending.get("options", {})

    if user_input not in options:
        return {
            "needs_confirmation": True,
            "_confirm_message": f"请选择方案: {', '.join(options.keys())}",
            "_issues": ["invalid_choice"],
        }

    opt = options[user_input]
    action = opt.get("action", "move_new")
    task = opt.get("task", "")

    if action == "move_new":
        return {
            "intent": "create_event",
            "sub_tasks": [
                {"action": "create_task", "params": {
                    "title": task,
                    "start_time": state.get("_choice_time", ""),  # TODO: parse from user input
                }},
            ],
            "needs_confirmation": False,
            "pending_action": {},  # 清除
        }
    elif action == "keep_existing":
        return {
            "intent": "chat",
            "sub_tasks": [],
            "needs_confirmation": False,
            "pending_action": {},
            "_confirm_message": f"保留「{opt.get('conflict_with','')}」, 不创建「{task}」。",
        }

    return {
        "needs_confirmation": True,
        "_confirm_message": f"方案{user_input}暂不支持自动执行。",
        "_issues": ["unsupported_action"],
    }
