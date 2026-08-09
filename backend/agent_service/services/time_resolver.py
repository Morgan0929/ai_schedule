"""
Time Resolver — 自然语言时间 → 标准时间范围 (纯规则, 零 LLM)

用法:
  r = resolve_time_range("周五")
  → {"type": "RANGE", "time_range": {"start": "2026-08-07T00:00:00", "end": "2026-08-07T23:59:59"}}

  r = resolve_time_range("周五下午3点")
  → {"type": "POINT", "time_range": {"start": "2026-08-07T15:00:00", "end": "2026-08-07T16:00:00"}}
"""
import re
import calendar
from datetime import date, timedelta, datetime
from typing import Literal

WEEKDAY_MAP = {
    "周一": 0, "周二": 1, "周三": 2, "周四": 3, "周五": 4, "周六": 5, "周日": 6,
    "星期一": 0, "星期二": 1, "星期三": 2, "星期四": 3, "星期五": 4, "星期六": 5, "星期日": 6,
}
CN_NUM = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
          '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
PERIOD_HOURS = {
    '上午': (8, 12), '早上': (7, 12), '早晨': (7, 12),
    '中午': (12, 14), '下午': (13, 18), '傍晚': (17, 20),
    '晚上': (18, 23),
}


def _normalize_aliases(text: str) -> str:
    """把口语时间缩写展开, 让后续规则只处理一种形态。"""
    aliases = {
        '明早': '明天早上',
        '明晚': '明天晚上',
        '今早': '今天早上',
        '今晚': '今天晚上',
        '后早': '后天早上',
        '后晚': '后天晚上',
        '月末': '月底',
    }
    for src, dst in aliases.items():
        text = text.replace(src, dst)
    return text


def _cn_to_int(s: str) -> int:
    if s.isdigit():
        return int(s)
    if s in CN_NUM:
        return CN_NUM[s]
    if len(s) == 2 and s[0] == '十':
        return 10 + CN_NUM.get(s[1], 0)
    return 0


def _resolve_date(text: str, today: date) -> date:
    """解析日期部分 → date 对象 (默认未来最近)"""
    text = _normalize_aliases(text)
    if '明天' in text:
        return today + timedelta(days=1)
    if '后天' in text:
        return today + timedelta(days=2)
    if '今天' in text:
        return today

    if '月底' in text:
        last_day = calendar.monthrange(today.year, today.month)[1]
        return today.replace(day=last_day)

    # 下周X (优先于裸周X)
    if '下周' in text:
        for word, wd in WEEKDAY_MAP.items():
            if word in text:
                return today + timedelta(days=(7 - today.weekday()) + wd)
        return today + timedelta(days=7 - today.weekday())

    # 这周/本周 (允许过去)
    if '这周' in text or '本周' in text:
        for word, wd in WEEKDAY_MAP.items():
            if word in text:
                return today + timedelta(days=wd - today.weekday())
        return today - timedelta(days=today.weekday())

    # 周X (未来最近, 今天=当天)
    for word, wd in WEEKDAY_MAP.items():
        if word in text:
            delta = wd - today.weekday()
            if delta < 0:
                delta += 7
            return today + timedelta(days=delta)

    # 下个月
    if '下个月' in text:
        d = today.replace(day=1) + timedelta(days=32)
        return d.replace(day=1)

    return today


def _extract_hour_minute(text: str) -> tuple:
    """提取小时+分钟, 返回 (hour, minute, period) 或 (None, 0, None)"""
    text = _normalize_aliases(text)
    HOUR_PAT = r'(\d{1,2}|[一二两三四五六七八九十]{1,2})'
    m = re.search(rf'(下午|晚上|傍晚|中午)\s*{HOUR_PAT}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)
    if not m:
        m = re.search(rf'(上午|早上|早晨)\s*{HOUR_PAT}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)
    if not m:
        m = re.search(rf'(今天|明天|后天|下周[一二三四五六日]|周[一二三四五六日])\s*{HOUR_PAT}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)
    if not m:
        m = re.search(rf'(?<![上下午晚早中午])[\s]{HOUR_PAT}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)
    if not m:
        m = re.search(rf'^(){HOUR_PAT}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)
    if not m:
        return None, 0, None

    groups = m.groups()
    period = groups[0] if groups[0] else ''
    h = _cn_to_int(groups[1]) if groups[1] else 0
    half_or_min = groups[2] if len(groups) > 2 else None
    min_digits = groups[3] if len(groups) > 3 else None  # inner capture for "30分"
    if half_or_min == '半':
        minute = 30
    elif min_digits and min_digits.isdigit():
        minute = int(min_digits)
    elif half_or_min and half_or_min.isdigit():
        minute = int(half_or_min)
    else:
        minute = 0

    if period in ('下午', '晚上', '傍晚'):
        hour = h + 12 if h != 12 else h
    elif period in ('上午', '早上', '早晨'):
        hour = h if h != 12 else 0
    elif period == '中午':
        hour = 12
    else:
        hour = h
    return hour, minute, period


def resolve_time_range(text: str, now: date = None) -> dict:
    """
    自然语言时间 → 标准时间范围

    Returns:
      POINT:  {"type": "POINT", "time_range": {"start": "...T15:00:00", "end": "...T16:00:00"}}
      RANGE:  {"type": "RANGE", "time_range": {"start": "...T00:00:00", "end": "...T23:59:59"}}
      UNKNOWN: {"type": "UNKNOWN", "time_range": None}
    """
    text = _normalize_aliases(text)
    today = now or date.today()
    d = _resolve_date(text, today)
    hour, minute, period = _extract_hour_minute(text)

    # POINT: 有具体时刻
    if hour is not None:
        return {
            "type": "POINT",
            "time_range": {
                "start": f"{d.isoformat()}T{hour:02d}:{minute:02d}:00",
                "end": f"{d.isoformat()}T{hour + 1:02d}:{minute:02d}:00",
            },
            "date": d.isoformat(),
        }

    # RANGE: 有时段无时刻 (period 来自 _extract_hour_minute)
    # 补充检测: "下午"/"上午" 等无具体时刻的时段词
    if not period:
        for p in PERIOD_HOURS:
            if p in text:
                period = p
                break

    if period:
        start_h, end_h = PERIOD_HOURS.get(period, (9, 12))
        return {
            "type": "RANGE",
            "time_range": {
                "start": f"{d.isoformat()}T{start_h:02d}:00:00",
                "end": f"{d.isoformat()}T{end_h:02d}:00:00",
            },
            "date": d.isoformat(),
        }

    # RANGE: 有日期无时段
    if any(kw in text for kw in ['明天', '后天', '今天', '周', '下周', '这周', '下个月', '月底']):
        return {
            "type": "RANGE",
            "time_range": {
                "start": f"{d.isoformat()}T00:00:00",
                "end": f"{d.isoformat()}T23:59:59",
            },
            "date": d.isoformat(),
        }

    # UNKNOWN
    return {"type": "UNKNOWN", "time_range": None, "date": today.isoformat()}
