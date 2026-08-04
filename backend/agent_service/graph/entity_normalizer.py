"""
EntityNormalizer Node — Planner 输出后处理

位置: planner → normalize → validator

职责:
  1. 标题清洗 (去"我"/"我要"/"去"/引导词/时间词残留)
  2. 时间 schema 统一 (start/end → start_time/end_time)
  3. intent 标准化 (使用 normalize_intent)
"""
from typing import Any

TITLE_PREFIXES = [
    "我要去", "我想去", "我要", "我想", "我打算", "我准备",
    "帮我", "帮我安排", "帮我记一下", "记一下", "提醒我",
    "安排", "去", "做", "写", "交", "提交", "完成",
]
TITLE_SUFFIXES = ["吧", "一下", "下", "了", "哦", "啊", "呢", "吗", "呀"]


def _clean_title(title: str) -> str:
    """清洗标题: 去引导词/后缀/空白"""
    t = title.strip().strip("，,。.；;：:！!？? ")
    for prefix in sorted(TITLE_PREFIXES, key=len, reverse=True):
        if t.startswith(prefix) and len(t) > len(prefix) + 1:
            t = t[len(prefix):]
            break
    for suffix in TITLE_SUFFIXES:
        if t.endswith(suffix) and len(t) > len(suffix) + 1:
            t = t[:-len(suffix)]
            break
    return t.strip() if len(t.strip()) >= 1 else title


async def entity_normalizer_node(state: dict) -> dict[str, Any]:
    """Planner → Normalizer: 清洗实体 + 统一 schema"""
    from agent_service.graph.schemas import normalize_intent
    import logging

    updates = {}
    intent = state.get("intent", "")
    sub_tasks = state.get("sub_tasks", [])

    # 1. intent 标准化
    if intent:
        normalized = normalize_intent(str(intent))
        if normalized.value != intent:
            updates["intent"] = normalized.value

    # 2. sub_tasks 中每个 task 的 params 清洗
    cleaned_tasks = []
    for task in sub_tasks:
        params = dict(task.get("params", {})) if task.get("params") else {}
        # 统一时间字段
        if "start" in params and "start_time" not in params:
            params["start_time"] = params.pop("start")
        if "end" in params and "end_time" not in params:
            params["end_time"] = params.pop("end")
        # 清洗 title
        if "title" in params:
            params["title"] = _clean_title(params["title"])
        cleaned_tasks.append({**task, "params": params})

    if cleaned_tasks != sub_tasks:
        updates["sub_tasks"] = cleaned_tasks

    return updates if updates else {}
