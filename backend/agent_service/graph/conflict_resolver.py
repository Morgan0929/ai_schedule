"""
Conflict Resolver — 用户选择 A/B/C, 直接执行

不经过 planner/validator/normalizer
输入: user_input + pending_action
输出: executor action
"""
from typing import Any


async def conflict_resolver_node(state: dict) -> dict[str, Any]:
    """解析用户选择/确认"""
    pending = state.get("pending_action", {})
    stage = pending.get("stage", "")
    user_input = state.get("user_input", "").strip().upper()

    # Stage 2: 用户确认 → 执行
    if stage == "waiting_confirm" and user_input in ("确认", "YES", "OK", "Y", "是"):
        proposed = pending.get("proposed_actions", [])
        sub_tasks = [
            {"action": p["action"], "params": {"title": p.get("target", ""), "note": p.get("note", "")}}
            for p in proposed
        ]
        return {
            "intent": "update_event",
            "sub_tasks": sub_tasks,
            "needs_confirmation": False,
            "pending_action": {},  # 清除
            "_skip_validator": True,
        }

    # Stage 1: 用户选择 A/B/C
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
            "sub_tasks": [],  # 不直接执行, 先展示确认
            "needs_confirmation": True,
            "pending_action": {
                "type": "conflict_resolution",
                "stage": "waiting_confirm",
                "selected_plan": user_input,
                "proposed_actions": [{"action": "delete_task", "target": new_task}],
                "summary": f"删除「{new_task}」, 保留「{existing_task}」。",
            },
            "_confirm_message": f"确认删除「{new_task}」, 保留「{existing_task}」？回复「确认」执行。",
            "_skip_validator": True,
        }
    elif action == "keep_new":
        return {
            "intent": "update_event",
            "sub_tasks": [],
            "needs_confirmation": True,
            "pending_action": {
                "type": "conflict_resolution",
                "stage": "waiting_confirm",
                "selected_plan": user_input,
                "proposed_actions": [{"action": "create_task", "target": new_task, "note": f"需调整{existing_task}"}],
                "summary": f"保留「{new_task}」, 调整「{existing_task}」。",
            },
            "_confirm_message": f"确认保留「{new_task}」？回复「确认」执行。",
            "_skip_validator": True,
        }
    elif action == "cancel_new":
        return {
            "intent": "delete_event",
            "sub_tasks": [],
            "needs_confirmation": True,
            "pending_action": {
                "type": "conflict_resolution",
                "stage": "waiting_confirm",
                "selected_plan": user_input,
                "proposed_actions": [{"action": "delete_task", "target": new_task}],
                "summary": f"取消「{new_task}」。",
            },
            "_confirm_message": f"确认取消「{new_task}」？回复「确认」执行。",
            "_skip_validator": True,
        }

    return {
        "needs_confirmation": True,
        "_confirm_message": "此方案暂不支持自动执行。",
        "_issues": ["unsupported_action"],
        "pending_action": {},
    }
