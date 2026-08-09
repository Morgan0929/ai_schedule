"""
Coordinator Node — 冲突协调 (纯 Python, 零 LLM)

输出 action-based options:
  RESCHEDULE_PENDING  — 调整 PendingTask 时间
  RESCHEDULE_TASK     — 调整已有 Task 时间
  DISCARD_PENDING     — 取消 PendingTask
"""
from typing import Any
from agent_service.graph.state import AgentState
from agent_service.graph.pending_task import STAGE_WAITING_CHOICE


# ═══════════════════ ActionType ═══════════════════

RESCHEDULE_PENDING = "reschedule_pending"
RESCHEDULE_TASK = "update_task"
DISCARD_PENDING = "discard_pending"
COMMIT_PENDING = "commit_pending"
DELETE_TASK = "delete_task"


async def coordinator_node(state: AgentState) -> dict[str, Any]:
    conflicts = state.get("conflicts_found", [])
    print(f"[COORD] conflicts={len(conflicts)}")

    if not conflicts:
        return {"suggestions": [], "recommended_plan": ""}

    options = {}
    suggestions = []
    # 实体数据: task_id → {title, time} / ref_id → {title, start_time}
    entities = {}

    for i, c in enumerate(conflicts[:3]):
        ext = c.get("existing_task", {})
        pending = c.get("pending_task", {}) or c.get("new_task", {})
        pending_rid = c.get("pending_ref", pending.get("ref_id", ""))
        new_id = pending.get("id", 0)
        persisted_new = bool(new_id) and not pending_rid
        ext_id = ext.get("id", 0)
        ext_title = ext.get("title", "")
        new_title = pending.get("title", "")

        # 注册实体
        entities[ext_id] = {"title": ext_title, "time": ext.get("time", ""), "kind": "task"}
        if pending_rid:
            entities[pending_rid] = {
                "title": new_title,
                "start_time": pending.get("start_time") or pending.get("time", ""),
                "end_time": pending.get("end_time", ""),
                "kind": "pending",
            }
        elif persisted_new:
            entities[new_id] = {
                "title": new_title,
                "time": pending.get("time", ""),
                "kind": "task",
            }

        if "A" not in options:
            label = f"保留「{ext_title}」, 调整「{new_title}」"
            options["A"] = {
                "label": label,
                "description": label,
                "preview": {"keep": ext_title, "change": f"{new_title} → 待指定"},
                "actions": ([{"type": RESCHEDULE_TASK, "task_id": new_id}]
                            if persisted_new else
                            [{"type": RESCHEDULE_PENDING, "ref_id": pending_rid}]),
                "requires_time": True,
                "move_time": pending.get("start_time") or pending.get("time", ""),
            }
            suggestions.append({"plan_id": "A", "title": label, "description": label, "impact": "", "is_recommended": False})
        if "B" not in options:
            label = f"保留「{new_title}」, 调整「{ext_title}」"
            options["B"] = {
                "label": label,
                "description": label,
                "preview": {"keep": new_title, "change": f"{ext_title} → 待指定"},
                "actions": [
                    {"type": RESCHEDULE_TASK, "task_id": ext_id},
                ] + ([] if persisted_new else [{
                    "type": RESCHEDULE_PENDING,
                    "ref_id": pending_rid,
                    "preserve_time": True,
                }]),
                "requires_time": True,
                "move_time": ext.get("time", ""),
            }
            suggestions.append({"plan_id": "B", "title": label, "description": label, "impact": "", "is_recommended": False})
        if "C" not in options:
            label = f"取消「{new_title}」"
            options["C"] = {
                "label": label,
                "description": label,
                "preview": {"discard": new_title},
                "actions": [],  # confirm 时 discard
                "requires_time": False,
            }
            if persisted_new:
                options["C"]["actions"] = [{"type": DELETE_TASK, "task_id": new_id}]
            suggestions.append({"plan_id": "C", "title": label, "description": label, "impact": "", "is_recommended": False})

    # 确保至少 A/B/C
    defaults = [
        ("A", RESCHEDULE_PENDING, "保留已有, 新任务延后"),
        ("B", RESCHEDULE_TASK, "保留新任务, 已有任务调整"),
        ("C", DISCARD_PENDING, "取消新任务"),
    ]
    for plan_id, action_type, label in defaults:
        if plan_id not in options:
            c0 = conflicts[0] if conflicts else {}
            ext = c0.get("existing_task", {})
            pending = c0.get("pending_task", {}) or c0.get("new_task", {})
            pending_rid = c0.get("pending_ref", pending.get("ref_id", ""))
            ext_id = ext.get("id", 0)
            if plan_id == "A":
                options[plan_id] = {
                    "label": label,
                    "description": label,
                    "actions": [{"type": action_type, "ref_id": pending_rid}],
                    "requires_time": True,
                }
            elif plan_id == "B":
                options[plan_id] = {
                    "label": label,
                    "description": label,
                    "actions": [
                        {"type": action_type, "task_id": ext_id},
                        {
                            "type": RESCHEDULE_PENDING,
                            "ref_id": pending_rid,
                            "preserve_time": True,
                        },
                    ],
                    "requires_time": True,
                }
            elif plan_id == "C":
                options[plan_id] = {
                    "label": label,
                    "description": label,
                    "actions": [],
                    "requires_time": False,
                }
            suggestions.append({"plan_id": plan_id, "title": label, "description": label, "impact": "", "is_recommended": False})

    result = {
        "conflicts_found": conflicts,
        "conflict_count": len(conflicts),
        "suggestions": suggestions,
        "recommended_plan": "",
        "active_flow": "conflict_resolution",
        "pending_action": {
            "type": "conflict_resolution",
            "stage": STAGE_WAITING_CHOICE,
            "options": options,
            "entities": entities,
        },
    }
    print(f"[COORD] → {len(options)} options")
    return result
