"""
Mock Agent — 无需 API Key 的规则引擎回退

当 DeepSeek API Key 未配置时，使用正则/关键词匹配
实现基本的意图识别和任务拆解
"""
import json
import re
from datetime import datetime, timedelta, date
from typing import Any


# ============ 意图识别 ============

def detect_intent(user_input: str) -> dict[str, Any]:
    """
    规则引擎意图识别

    Returns:
        {"intent": "...", "entities": {...}, "confidence": 0.0~1.0}
    """
    text = user_input.strip()

    # === 无关事务检测 (最高优先级) ===
    out_of_scope = [
        "写代码", "编程", "写程序", "调试", "bug", "帮我写", "帮我改",
        "翻译", "数学题", "物理题", "化学题", "解释一下", "什么是",
        "讲笑话", "写诗", "写小说", "写故事", "新闻", "评论",
        "心理咨询", "看病", "诊断", "法律", "建议一下",
    ]
    if any(w in text for w in out_of_scope):
        return {"intent": "CHAT", "entities": {}, "confidence": 0.95}

    # 天气查询
    if any(w in text for w in ["天气", "气温", "下雨", "降温"]):
        return {"intent": "QUERY_WEATHER", "entities": _extract_city(text), "confidence": 0.95}

    # 创建任务（含"安排/创建/添加/帮我"等动词）
    if any(w in text for w in ["安排", "创建", "添加", "新建", "加上", "帮我", "请帮我", "我要", "我想"]):
        # 区分：纯查询 vs 创建
        if any(w in text for w in ["查看", "查询", "看看", "有没有", "有什么", "检查"]):
            return {"intent": "QUERY_SCHEDULE", "entities": _extract_time(text), "confidence": 0.8}
        return {"intent": "CREATE_EVENT", "entities": _extract_task_info(text), "confidence": 0.85}

    # 出差/航班（在普通查询之前检查）
    if any(w in text for w in ["出差", "飞", "航班", "机票", "订票", "出行"]):
        return {"intent": "ARRANGE_TRIP", "entities": _extract_trip_info(text), "confidence": 0.85}

    # 冲突检测
    if any(w in text for w in ["冲突", "检查", "检测", "是否重叠", "会不会撞"]):
        return {"intent": "DETECT_CONFLICT", "entities": _extract_time(text), "confidence": 0.85}

    # 删除
    if any(w in text for w in ["删除", "取消", "去掉", "移除"]):
        return {"intent": "DELETE_TASK", "entities": {}, "confidence": 0.8}

    # 时间线生成
    if any(w in text for w in ["时间线", "timeline", "生成"]):
        return {"intent": "GENERATE_TIMELINE", "entities": _extract_time(text), "confidence": 0.8}

    # 普通查询（查看/查询 + 日期）
    if any(w in text for w in ["查看", "查询", "看看", "有什么", "日程", "今天", "明天", "下周", "这周"]):
        return {"intent": "QUERY_SCHEDULE", "entities": _extract_time(text), "confidence": 0.8}

    # 默认对话
    return {"intent": "CHAT", "entities": {}, "confidence": 0.3}


# ============ 实体提取 ============

def _extract_time(text: str) -> dict:
    """提取时间信息（日期 + 具体时间）"""
    import re
    today = date.today()

    # 提取具体时间（含"半"）
    hour, minute = _extract_hour_minute(text)

    # 提取日期
    day_names = {"周一":0,"周二":1,"周三":2,"周四":3,"周五":4,"周六":5,"周日":6,
                 "星期一":0,"星期二":1,"星期三":2,"星期四":3,"星期五":4,"星期六":5,"星期日":6}

    d = today
    if "明天" in text:
        d = today + timedelta(days=1)
    elif "后天" in text:
        d = today + timedelta(days=2)
    elif "下周" in text:
        for name, wd in day_names.items():
            if name in text:
                days = (7 - today.weekday()) + wd
                d = today + timedelta(days=days)
                break
        else:
            days_until_monday = 7 - today.weekday()
            d = today + timedelta(days=days_until_monday)
    elif "这周" in text or "本周" in text:
        for name, wd in day_names.items():
            if name in text:
                days = wd - today.weekday()
                if days < 0: days += 7
                d = today + timedelta(days=days)
                break
        else:
            d = today - timedelta(days=today.weekday())
    elif "下个月" in text:
        d = today.replace(day=1) + timedelta(days=32)
        d = d.replace(day=1)
    elif any(name in text for name in day_names):
        for name, wd in day_names.items():
            if name in text:
                days = wd - today.weekday()
                if days <= 0: days += 7
                d = today + timedelta(days=days)
                break

    # 构建 ISO 字符串
    if hour is not None:
        result = {
            "start": f"{d.isoformat()}T{hour:02d}:{minute:02d}:00",
            "end": f"{d.isoformat()}T{hour + 1:02d}:{minute:02d}:00",
        }
    else:
        result = {"start": d.isoformat(), "end": d.isoformat()}
    return result


def _extract_hour_minute(text: str) -> tuple:
    """提取小时和分钟, 支持 '下午3点半' → (15, 30)"""
    import re

    hour, minute = None, 0

    # "下午3点半" / "上午10点" / "晚上8点" / "3点30分"
    m = re.search(r'(下午|晚上|傍晚|中午)\s*(\d{1,2})\s*点\s*(半|(\d{1,2})\s*分)?', text)
    if not m:
        m = re.search(r'(上午|早上|早晨)\s*(\d{1,2})\s*点\s*(半|(\d{1,2})\s*分)?', text)
    if not m:
        m = re.search(r'(?<![上下晚早中午])[\s](\d{1,2})\s*点\s*(半|(\d{1,2})\s*分)?', text)
    if not m:
        m = re.search(r'^(\d{1,2})\s*点\s*(半|(\d{1,2})\s*分)?', text)

    if m:
        groups = m.groups()
        period = groups[0] if groups[0] else ""
        h = int(groups[1])
        half_or_min = groups[2] if len(groups) > 2 else None

        if half_or_min == "半":
            minute = 30
        elif half_or_min and half_or_min.isdigit():
            minute = int(half_or_min)

        if period in ('下午', '晚上', '傍晚'):
            hour = h + 12 if h != 12 else h
        elif period in ('上午', '早上', '早晨'):
            hour = h if h != 12 else 0
        elif period == '中午':
            hour = 12
        elif groups[0] and groups[0].isdigit():
            hour = h
        else:
            hour = h

    return hour, minute


def _extract_hour(text: str) -> int | None:
    """兼容旧接口"""
    h, _ = _extract_hour_minute(text)
    return h


def _extract_city(text: str) -> dict:
    """提取城市名"""
    cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "南京", "武汉", "重庆", "西安",
              "英德", "清远", "东莞", "佛山", "珠海", "惠州", "中山", "江门", "肇庆", "湛江",
              "长沙", "郑州", "天津", "苏州", "厦门", "青岛", "大连", "昆明", "贵阳", "南宁"]
    for c in cities:
        if c in text:
            return {"city": c}
    return {"city": "北京"}


def _extract_task_info(text: str) -> dict:
    """从文本中提取任务信息"""
    info = _extract_time(text)
    info.update(_extract_city(text))

    # 尝试提取标题（去掉动词前缀后的部分）
    title = text
    for prefix in ["帮我", "请", "安排", "创建", "添加", "新建", "我要", "我想"]:
        title = title.replace(prefix, "")
    info["title"] = title.strip().strip("。，.！!；;")
    info["priority"] = "HIGH" if any(w in text for w in ["重要", "紧急", "客户", "必须"]) else "MEDIUM"

    return info


def _extract_trip_info(text: str) -> dict:
    """提取出差信息"""
    info = _extract_task_info(text)
    cities = ["北京", "上海", "广州", "深圳", "杭州", "成都"]
    found = [c for c in cities if c in text]
    if len(found) >= 1:
        info["destination"] = found[-1]
    return info


# ============ Mock 对话 ============

async def mock_chat(user_input: str) -> str:
    """
    Mock 对话引擎 — 无需 LLM 的规则驱动回复
    """
    intent_info = detect_intent(user_input)
    intent = intent_info["intent"]
    entities = intent_info["entities"]

    if intent == "QUERY_SCHEDULE":
        start = entities.get("start", "今天")
        end = entities.get("end", "7天后")
        return (
            f"【当前安排】{start} ~ {end}\n暂无日程。\n\n需要安排什么？比如「明天下午3点开会」。"
        )

    if intent == "CREATE_TASK":
        title = entities.get("title", user_input)
        return (
            f"【确认】已创建\n任务：{title}\n时间：{entities.get('start', '待定')}\n优先级：{entities.get('priority', 'MEDIUM')}"
        )

    if intent == "ARRANGE_TRIP":
        dest = entities.get("destination", entities.get("city", "目的地"))
        return (
            f"【确认】出差：{dest}\n准备：1.查{dest}天气 2.检查日程冲突 3.生成时间线\n告诉我具体日期。"
        )

    if intent == "DETECT_CONFLICT":
        return (
            f"【当前安排】检查范围：{entities.get('start', '未来7天')}\n未发现时间冲突。"
        )

    if intent == "GENERATE_TIMELINE":
        return (
            f"日期：{entities.get('start', date.today().isoformat())}\n暂无安排，时间线为空。"
        )

    if intent == "QUERY_WEATHER":
        city = entities.get("city", "北京")
        return f"查询{city}天气中。\n（当前为离线模式，配置后可实时查询）"

    # 无关事务 → 拒绝
    out_of_scope = [
        "写代码", "编程", "写程序", "调试", "bug", "帮我写", "帮我改",
        "翻译", "数学题", "物理题", "化学题", "解释一下", "什么是",
        "讲笑话", "写诗", "写小说", "写故事", "新闻", "评论",
        "心理咨询", "看病", "诊断", "法律", "建议一下",
    ]
    if any(w in user_input for w in out_of_scope):
        return (
            "我是林，你的个人事务秘书。\n"
            "这个问题不属于我的工作范围。\n\n"
            "可以帮你：查看日程 / 创建任务 / 冲突检测 / 安排出差"
        )

    # 普通对话 — 林的开场白
    return (
        "我是林，你的个人事务秘书。\n\n"
        "可以帮你：\n"
        "  查看日程 —「查看明天的安排」\n"
        "  创建任务 —「帮我安排周五下午的会议」\n"
        "  冲突检测 —「检查下周有没有冲突」\n"
        "  安排出差 —「下周去上海出差」"
    )
