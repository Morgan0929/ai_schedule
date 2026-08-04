"""State Inspector — 调试节点, 验证类型正确性"""
from typing import Any


async def state_inspector_node(state: dict) -> dict[str, Any]:
    """打印关键字段类型, 不做任何修改"""
    intent = state.get("intent", "")
    sub_tasks = state.get("sub_tasks", [])
    print(f"[INSPECTOR] intent={intent!r} type={type(intent).__name__} "
          f"sub_tasks={len(sub_tasks)} needs_confirmation={state.get('needs_confirmation')}")
    return {}  # pass-through, no modification
