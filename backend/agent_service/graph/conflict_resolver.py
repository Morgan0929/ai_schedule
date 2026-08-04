"""
Conflict Resolver — 用户选择 A/B/C, 直接执行

不经过 planner/validator/normalizer
输入: user_input + pending_action
输出: executor action
"""
from typing import Any


async def conflict_resolver_node(state: dict) -> dict[str, Any]:
    """解析用户选择, 直接返回执行动作"""
    pending = state.get("pending_action", {})
    user_input = state.get("user_input", "").strip().upper()
    options = pending.get("options", {})

    if user_input not in options:
        return {
            "needs_confirmation": True,
            "_confirm_message": f"请选择方案: {', '.join(sorted(options.keys()))}",
            "_issues": ["invalid_choice"],
        }

    opt = options[user_input]
    action = opt.get("action", "")
    new_task = opt.get("new_task", "")
    existing_task = opt.get("existing_task", "")

    if action == "keep_existing":
        return {
            "intent": "update_event",
            "sub_tasks": [
                {"action": "delete_task", "params": {"title": new_task}},
            ],
            "needs_confirmation": False,
            "pending_action": {},  # 清除
            "_confirm_message": f"删除「{new_task}」, 保留「{existing_task}」。",
            "_skip_validator": True,
        }
    elif action == "keep_new":
        return {
            "intent": "update_event",
            "sub_tasks": [
                {"action": "create_task", "params": {
                    "title": new_task,
                    "hint": f"用户选择保留{new_task}, 需要调整{existing_task}"
                }},
            ],
            "needs_confirmation": False,
            "pending_action": {},
            "_confirm_message": f"保留「{new_task}」, 需要调整「{existing_task}」。",
            "_skip_validator": True,
        }
    elif action == "cancel_new":
        return {
            "intent": "delete_event",
            "sub_tasks": [
                {"action": "delete_task", "params": {"title": new_task}},
            ],
            "needs_confirmation": False,
            "pending_action": {},
            "_confirm_message": f"已取消「{new_task}」。",
            "_skip_validator": True,
        }

    return {
        "needs_confirmation": True,
        "_confirm_message": "此方案暂不支持自动执行。",
        "_issues": ["unsupported_action"],
        "pending_action": {},
    }
