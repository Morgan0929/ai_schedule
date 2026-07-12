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

    # 天气查询（最高优先级：含"天气"关键词）
    if any(w in text for w in ["天气", "气温", "下雨", "降温"]):
        return {"intent": "QUERY_WEATHER", "entities": _extract_city(text), "confidence": 0.95}

    # 创建任务（含"安排/创建/添加/帮我"等动词）
    if any(w in text for w in ["安排", "创建", "添加", "新建", "加上", "帮我", "请帮我", "我要", "我想"]):
        # 区分：纯查询 vs 创建
        if any(w in text for w in ["查看", "查询", "看看", "有没有", "有什么", "检查"]):
            return {"intent": "QUERY_CALENDAR", "entities": _extract_time(text), "confidence": 0.8}
        return {"intent": "CREATE_TASK", "entities": _extract_task_info(text), "confidence": 0.85}

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
        return {"intent": "QUERY_CALENDAR", "entities": _extract_time(text), "confidence": 0.8}

    # 默认对话
    return {"intent": "CHAT", "entities": {}, "confidence": 0.3}


# ============ 实体提取 ============

def _extract_time(text: str) -> dict:
    """提取时间信息（日期 + 具体时间）"""
    result = {}
    today = date.today()
    hour = None
    minute = 0

    # 提取具体时间
    hour = _extract_hour(text)

    # 提取日期
    if "明天" in text:
        d = today + timedelta(days=1)
    elif "后天" in text:
        d = today + timedelta(days=2)
    elif "下周" in text:
        days_until_monday = 7 - today.weekday()
        d = today + timedelta(days=days_until_monday)
    elif "这周" in text or "本周" in text:
        days_since_monday = today.weekday()
        d = today - timedelta(days=days_since_monday)
    else:
        d = today

    # 构建带时间的 ISO 字符串
    if hour is not None:
        result["start"] = f"{d.isoformat()}T{hour:02d}:{minute:02d}:00"
        result["end"] = f"{d.isoformat()}T{hour + 1:02d}:{minute:02d}:00"
    else:
        result["start"] = d.isoformat()
        result["end"] = d.isoformat()

    return result


def _extract_hour(text: str) -> int | None:
    """
    从文本中提取具体小时

    支持: 下午3点, 上午10点, 3点, 4点30, 晚上8点, 中午12点
    """
    import re

    # 匹配模式: [上午/下午/晚上] N 点 [M 分]
    patterns = [
        r'(下午|晚上|傍晚)\s*(\d{1,2})\s*点(?:\s*(\d{1,2})\s*分)?',
        r'(上午|早上|早晨)\s*(\d{1,2})\s*点(?:\s*(\d{1,2})\s*分)?',
        r'(?<![上下晚早])[\s](\d{1,2})\s*点(?:\s*(\d{1,2})\s*分)?',
        r'^(\d{1,2})\s*点(?:\s*(\d{1,2})\s*分)?',
    ]

    for pattern in patterns:
        match = re.search(pattern, text)
        if match:
            groups = match.groups()
            if groups[0] and groups[0] in ('下午', '晚上', '傍晚'):
                h = int(groups[1])
                return h + 12 if h != 12 else h
            elif groups[0] and groups[0] in ('上午', '早上', '早晨'):
                h = int(groups[1])
                return h if h != 12 else 0
            elif groups[0] and groups[0].isdigit():
                return int(groups[0])
            elif len(groups) >= 2 and groups[0] is None and groups[1]:
                return int(groups[1])

    return None


def _extract_city(text: str) -> dict:
    """提取城市名"""
    cities = ["北京", "上海", "广州", "深圳", "杭州", "成都", "南京", "武汉", "重庆", "西安"]
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

    if intent == "QUERY_CALENDAR":
        start = entities.get("start", "今天")
        end = entities.get("end", "7天后")
        return (
            f"好的呀，帮你看看 {start} ~ {end} 的安排～\n\n"
            f"【当前安排】\n"
            f"这段时间暂时还没有日程，挺空的。\n\n"
            f"需要我帮你安排什么吗？比如「明天下午3点开会」这样告诉我就行。"
        )

    if intent == "CREATE_TASK":
        title = entities.get("title", user_input)
        return (
            f"收到，已经帮你记下啦～\n\n"
            f"【确认】\n"
            f"任务：{title}\n"
            f"时间：{entities.get('start', '待定')}\n"
            f"优先级：{entities.get('priority', 'MEDIUM')}\n\n"
            f"如果需要指定具体时间，告诉我「下午3点到5点」就行。"
        )

    if intent == "ARRANGE_TRIP":
        dest = entities.get("destination", entities.get("city", "目的地"))
        return (
            f"好的，{dest}之行走起～\n\n"
            f"【确认】\n"
            f"出差地点：{dest}\n\n"
            f"我会帮你准备好：\n"
            f"  1. 查一下 {dest} 那几天的天气\n"
            f"  2. 确认已有的日程有没有冲突\n"
            f"  3. 生成一份出行时间线\n\n"
            f"告诉我具体日期，我帮你一站式搞定。"
        )

    if intent == "DETECT_CONFLICT":
        return (
            f"好嘞，帮你扫描一下～\n\n"
            f"【当前安排】\n"
            f"检查范围：{entities.get('start', '未来7天')}\n"
            f"目前没有发现时间冲突，安排挺合理的。\n\n"
            f"如果有新的安排，随时告诉我，我会帮你检查会不会撞时间。"
        )

    if intent == "GENERATE_TIMELINE":
        return (
            f"帮你整理一下时间线～\n\n"
            f"日期：{entities.get('start', date.today().isoformat())}\n"
            f"今天还没有安排呢，时间线是空的。\n\n"
            f"先添加一些任务吧，我会帮你排成一条漂亮的时间线。"
        )

    if intent == "QUERY_WEATHER":
        city = entities.get("city", "北京")
        return (
            f"帮你看看 {city} 的天气～\n\n"
            f"（天气数据需要后台服务支持，当前是离线模式）\n"
            f"配置好之后就能实时查询啦。"
        )

    # 默认对话 — 林的开场白
    return (
        f"嗨，我是林，你的个人事务秘书～\n\n"
        f"我能帮你打理这些事情：\n"
        f"• 📅 查询日程 — 试试「查看明天的安排」\n"
        f"• ✏️ 创建任务 — 试试「帮我安排周五下午的会议」\n"
        f"• 🔍 冲突检测 — 试试「检查下周有没有冲突」\n"
        f"• ✈️ 安排出差 — 试试「下周去上海出差」\n"
        f"• 📋 生成时间线 — 试试「生成明天的时间线」\n\n"
        f"配置 DeepSeek API Key 后，AI 将更智能地理解您的需求。"
    )
