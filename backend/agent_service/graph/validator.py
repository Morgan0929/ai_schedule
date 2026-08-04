"""
State Validator Node — Planner 输出检查

检查:
  1. intent 存在且有效
  2. sub_tasks 不空
  3. 任务类意图必须有 title
  4. 任务类意图必须有时间
  5. confidence 合理

不合格 → 补全或要求用户确认
"""
from typing import Any


def _vlog(prefix, data):
    import json
    print(prefix, json.dumps(data, ensure_ascii=False, default=str)[:500])


async def validator_node(state: dict) -> dict[str, Any]:
    """Planner → Validator: 检查输出完整性"""
    _vlog("BEFORE VALIDATOR", {k: state.get(k) for k in
        ["intent", "sub_tasks", "needs_confirmation", "_confidence", "_source"]})
    intent = state.get("intent", "")
    sub_tasks = state.get("sub_tasks", [])
    user_input = state.get("user_input", "")

    # 1. intent 类型守卫 + 白名单
    ALLOWED_INTENTS = {"create_event", "create_todo", "create_reminder",
                       "query_schedule", "query_weather",
                       "update_event", "delete_event", "arrange_trip",
                       "chat", "unknown"}
    if not isinstance(intent, str) or intent not in ALLOWED_INTENTS:
        r = {
            "needs_confirmation": True,
            "_confirm_message": "请问你是想安排日程、查询安排，还是其他事务？",
            "_issues": ["intent_invalid", f"got={intent!r} type={type(intent).__name__}"],
        }; _vlog("AFTER VALIDATOR", r); return r

    # 2. sub_tasks 不空
    if not sub_tasks:
        r = {
            "needs_confirmation": True,
            "_confirm_message": "我理解了你的意图，但缺少执行步骤。请提供更多信息。",
            "_issues": ["no_sub_tasks"],
        }; _vlog("AFTER VALIDATOR", r); return r

    # 3. 任务类意图必须检查参数
    from agent_service.graph.schemas import Intent
    task_intents = (Intent.CREATE_EVENT.value, Intent.CREATE_TODO.value,
                    Intent.CREATE_REMINDER.value, Intent.UPDATE_EVENT.value,
                    Intent.DELETE_EVENT.value, Intent.ARRANGE_TRIP.value)
    if intent in task_intents:
        issues = []
        task_params = {}
        # 从 sub_tasks 中收集 create_task/update_task 的参数
        for st in sub_tasks:
            if st.get("action") in ("create_task", "update_task", "delete_task", "create_task_tool"):
                task_params = st.get("params", {})
                break

        title = task_params.get("title", "")
        has_start = task_params.get("start_time") or task_params.get("start")
        has_end = task_params.get("end_time") or task_params.get("end")

        # 缺标题 → 从原始输入提取
        if not title and intent in ("create_event", "create_todo", "create_reminder"):
            # 尝试用之前的事件检测逻辑
            title = _extract_event_from_input(user_input)
            if title:
                for st in sub_tasks:
                    if st.get("action") in ("create_task", "create_task_tool"):
                        st["params"]["title"] = title
            else:
                issues.append("missing_title")

        if not has_start:
            issues.append("missing_time")

        if issues:
            # 有缺字段 → 要求确认
            if "missing_title" in issues:
                r = {"needs_confirmation": True,
                    "_confirm_message": f"请问你要安排的具体事项是什么？",
                    "_issues": issues}; _vlog("AFTER VALIDATOR", r); return r
            if "missing_time" in issues and has_start is False:
                r = {"needs_confirmation": True,
                    "_confirm_message": f"请问具体是什么时间？",
                    "_issues": issues}; _vlog("AFTER VALIDATOR", r); return r

    # 4. 置信度检查
    confidence = state.get("_confidence", 0.85)
    source = state.get("_source", "unknown")
    if confidence < 0.6:
        r = {"needs_confirmation": True,
            "_confirm_message": f"你的意思是「{user_input[:50]}」吗？我想确认一下。",
            "_issues": ["low_confidence"],
            "_confidence": confidence}; _vlog("AFTER VALIDATOR", r); return r

    # 通过
    r = {"needs_confirmation": False, "_issues": [], "_validated": True}
    _vlog("AFTER VALIDATOR", r)
    return r


def _extract_event_from_input(text: str) -> str:
    """从用户输入中提取事件名（去掉时间词和引导词）"""
    remove = ["明天", "后天", "下周", "这周", "今天", "上午", "下午", "晚上",
              "周一", "周二", "周三", "周四", "周五", "周六", "周日",
              "下个月", "下周三", "下周一", "下周二", "下周四", "下周五",
              "1点", "2点", "3点", "4点", "5点", "6点", "7点", "8点",
              "9点", "10点", "11点", "12点", "半",
              "提醒我", "帮我", "帮我安排", "提醒", "安排",
              "在", "的", "去"]
    result = text
    for w in sorted(remove, key=len, reverse=True):
        result = result.replace(w, "")
    result = result.strip("，,。.；;：:！!？? ")
    return result if len(result) >= 2 else ""
