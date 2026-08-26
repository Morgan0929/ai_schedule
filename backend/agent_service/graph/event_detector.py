"""
Event Detector Node — 规则引擎优先, 日程类确定任务不浪费 LLM

优先级: regex/time parser > keyword match > fallback to planner

输出:
  high confidence + sub_tasks → 跳过 planner, 直接 tools_executor
  low confidence / chat      → 进入 planner (LLM)
"""
import re
from datetime import date, datetime, timedelta
from typing import Any


SPECIAL_DATE_WORDS = ('生日', '纪念日', '节日', '周年', '忌日')
TODO_QUERY_WORDS = ('待办', '代办', 'todo', 'to-do')


def is_out_of_scope_request(text: str) -> bool:
    """识别明显不属于个人事务秘书范围的请求。"""
    normalized = (text or "").strip().lower()
    out_of_scope = [
        '写代码', '写程序', '写一段', '写个函数', '二分查找', '算法', '编程',
        'debug', 'bug', '代码', '程序', 'python', 'java', 'javascript', 'dart',
        '解释一下', '什么是', '讲个笑话', '写诗', '写小说', '写故事',
        '推荐一部电影', '怎么学', '学好英语', '翻译', '数学题', '物理题',
        '化学题', '法律', '诊断', '心理咨询',
    ]
    return any(word in normalized for word in out_of_scope)


def out_of_scope_reply() -> str:
    return (
        "我理解你的需求，不过我主要负责日程、待办、提醒、天气和冲突处理。\n"
        "这类写代码或知识讲解的问题不在我的工作范围内，我就不替你处理了。"
    )


def _normalize_time_aliases(text: str) -> str:
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


def extract_event_title(text: str) -> str:
    """
    清洗标题: 去掉时间词/指令词, 只保留事件名

    "明天下午三点打游戏"       → "打游戏"
    "后天上午10点客户沟通"     → "客户沟通"
    "帮我安排周五晚上的会议"   → "会议"
    "明天晚上我要看电影"       → "看电影"
    "明天早上八点和朋友吃早餐" → "和朋友吃早餐"
    "下午2点提醒我开会"        → "开会"
    """
    result = _normalize_time_aliases(text)

    # ── 第1步: 去掉时间表达 (长→短, 防残留) ──
    # CN = 中文数字 [一二两三四五六七八九十]{1,2}
    CN = r'[一二两三四五六七八九十]{1,2}'
    time_patterns = [
        # "明天下午3点半" / "明天下午三点半" (日期+时段+时刻)
        rf'明天(下午|晚上|上午|中午|早上|早晨)\s*(\d{{1,2}}|{CN})\s*点\s*(半|\d{{1,2}}分)?',
        rf'后天(下午|晚上|上午|中午|早上|早晨)\s*(\d{{1,2}}|{CN})\s*点\s*(半|\d{{1,2}}分)?',
        rf'今天(下午|晚上|上午|中午|早上|早晨)\s*(\d{{1,2}}|{CN})\s*点\s*(半|\d{{1,2}}分)?',
        # "下周一下午3点" — 必须在下周[一二三] 和 周[一二三] 之前
        rf'下周[一二三四五六日]\s*(下午|晚上|上午|中午|早上|早晨)\s*(\d{{1,2}}|{CN})\s*点\s*(半|\d{{1,2}}分)?',
        # "周一下午3点" / "周一下午三点"
        rf'周[一二三四五六日]\s*(下午|晚上|上午|中午|早上|早晨)\s*(\d{{1,2}}|{CN})\s*点\s*(半|\d{{1,2}}分)?',
        # "下午3点" / "下午三点"
        rf'(下午|晚上|上午|中午|傍晚)\s*(\d{{1,2}}|{CN})\s*点\s*(半|\d{{1,2}}分)?',
        # "3点半" / "三点半" (裸时间, 无时段)
        rf'(\d{{1,2}}|{CN})\s*点\s*(半|\d{{1,2}}分)?',
        # "明天下午" / "后天上午" / "今天晚上" (无具体时刻)
        r'明天(下午|晚上|上午|中午|早上|早晨)',
        r'后天(下午|晚上|上午|中午|早上|早晨)',
        r'今天(下午|晚上|上午|中午|早上|早晨)',
        # 周几
        r'下周[一二三四五六日]',
        r'周[一二三四五六日]',
        # 未来日期 "8月15号"
        r'\d{1,2}\s*[.\-/]\s*\d{1,2}',
        r'\d{1,2}月\d{1,2}[号日]',
        r'(?:\d{1,2}\s*月\s*)?\d{1,2}\s*[号日]',
        # 单个时间词
        r'明天|后天|今天|下周|这周|本周|下个月|月底',
        r'下午|晚上|上午|中午|傍晚|早上|早晨',
    ]
    for pat in time_patterns:
        result = re.sub(pat, '', result)

    # ── 第2步: 去掉指令词 (长→短) ──
    commands = [
        '帮我安排一下', '帮我安排', '请帮我', '麻烦你',
        '提醒我', '记得提醒我', '记得', '记一下',
        '我要去', '我想要', '我想去', '我要', '我想',
        '帮我', '安排', '提醒', '创建', '添加', '新建', '加上',
    ]
    for cmd in sorted(commands, key=len, reverse=True):
        result = result.replace(cmd, '')

    # ── 第3步: 清理连接词/标点/空格 ──
    result = result.strip('的，,。.；;：:！!？? 、 \t\n\r')
    # 去掉开头的结构性虚词；人物连接词如“和/跟/与”属于标题内容。
    for junk in ['把', '去', '在', '一下', '一个', '的']:
        if result.startswith(junk):
            result = result[len(junk):].strip()

    return result if len(result) >= 2 else ''


def _parse_time(text: str) -> dict:
    """
    纯规则时间解析: 返回 {type, start_time, end_time, precision}

    type:
      POINT   — 有具体时刻, 用于创建事件 ("明天下午3点")
      RANGE   — 有日期无时刻, 用于查询 ("周五", "下周")
      UNKNOWN — 无时间信息

    precision: exact / period / day / week / month / unknown
    """
    text = _normalize_time_aliases(text)
    today = date.today()

    # ── 提取小时+分钟 ──
    hour, minute = None, 0
    _CN_NUM = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
               '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
    _HOUR = r'(\d{1,2}|[一二两三四五六七八九十]{1,2})'

    m = re.search(rf'(下午|晚上|傍晚|中午)\s*{_HOUR}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)
    if not m:
        m = re.search(rf'(上午|早上|早晨)\s*{_HOUR}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)
    if not m:
        m = re.search(rf'(?<![上下午晚早中午])[\s]{_HOUR}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)
    if not m:
        m = re.search(rf'^{_HOUR}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)

    if m:
        groups = m.groups()
        period = groups[0] if groups[0] else ''
        hour_str = groups[1]
        half_or_min = groups[2] if len(groups) > 2 else None
        if hour_str.isdigit():
            h = int(hour_str)
        else:
            h = _CN_NUM.get(hour_str, 0)
            if h == 0 and len(hour_str) == 2 and hour_str[0] == '十':
                h = 10 + _CN_NUM.get(hour_str[1], 0)
        if half_or_min == '半':
            minute = 30
        elif half_or_min and half_or_min.isdigit():
            minute = int(half_or_min)
        if period in ('下午', '晚上', '傍晚'):
            hour = h + 12 if h != 12 else h
        elif period in ('上午', '早上', '早晨'):
            hour = h if h != 12 else 0
        elif period == '中午':
            hour = 12
        else:
            hour = h

    # ── 提取日期 ──
    day_names = {'周一': 0, '周二': 1, '周三': 2, '周四': 3, '周五': 4, '周六': 5, '周日': 6,
                 '星期一': 0, '星期二': 1, '星期三': 2, '星期四': 3, '星期五': 4, '星期六': 5, '星期日': 6}
    d = today
    date_precision = "unknown"
    if '明天' in text:
        d = today + timedelta(days=1); date_precision = "day"
    elif '后天' in text:
        d = today + timedelta(days=2); date_precision = "day"
    elif re.search(r'(?:月底)?(?:\d{1,2}\s*月\s*)?\d{1,2}\s*[号日]', text):
        from agent_service.services.time_resolver import resolve_time_range
        resolved = resolve_time_range(text)
        if resolved.get('time_range'):
            d = datetime.fromisoformat(resolved['time_range']['start']).date()
            date_precision = "day"
    elif '下周' in text:
        date_precision = "week"
        for name, wd in day_names.items():
            if name in text:
                d = today + timedelta(days=(7 - today.weekday()) + wd)
                date_precision = "day"
                break
        else:
            d = today + timedelta(days=7 - today.weekday())
    elif '这周' in text or '本周' in text:
        date_precision = "week"
        for name, wd in day_names.items():
            if name in text:
                days = wd - today.weekday()
                if days < 0: days += 7
                d = today + timedelta(days=days)
                date_precision = "day"
                break
        else:
            d = today - timedelta(days=today.weekday())
    elif '下个月' in text:
        date_precision = "month"
        d = today.replace(day=1) + timedelta(days=32)
        d = d.replace(day=1)
    elif any(name in text for name in day_names):
        date_precision = "day"
        for name, wd in day_names.items():
            if name in text:
                days = wd - today.weekday()
                if days <= 0: days += 7
                d = today + timedelta(days=days)
                break
    elif '今天' in text:
        date_precision = "day"

    # ── 判定 precision ──
    if hour is not None:
        precision = "exact"
    elif re.search(r'(下午|晚上|上午|中午|傍晚|早上|早晨)', text):
        precision = "period"
    elif date_precision in ("day", "week", "month"):
        precision = date_precision
    else:
        precision = "unknown"

    # ── 构建结果 ──
    if precision == "exact":
        return {
            'type': 'POINT',
            'start_time': f'{d.isoformat()}T{hour:02d}:{minute:02d}:00',
            'end_time': f'{d.isoformat()}T{hour + 1:02d}:{minute:02d}:00',
            'precision': precision,
        }
    # 有日期无时刻 → RANGE (用于查询)
    if precision in ("day", "week", "month", "period"):
        return {
            'type': 'RANGE',
            'start_time': f'{d.isoformat()}T00:00:00',
            'end_time': f'{d.isoformat()}T23:59:59',
            'precision': precision,
            'reference_date': d.isoformat(),
        }
    # 无时间信息
    return {
        'type': 'UNKNOWN',
        'start_time': None,
        'end_time': None,
        'precision': 'unknown',
    }


def _has_time_indicator(text: str) -> bool:
    """检测是否有时间表达 (不要求具体时刻)"""
    text = _normalize_time_aliases(text)
    CN = r'[一二两三四五六七八九十]{1,2}'
    indicators = [
        r'明天', r'后天', r'今天',
        r'下周[一二三四五六日]', r'周[一二三四五六日]',
        r'下周', r'这周', r'本周', r'下个月', r'月底',
        rf'(\d{{1,2}}|{CN})点', r'\d{1,2}:\d{2}',
        r'下午', r'上午', r'晚上', r'中午', r'傍晚',
        r'\d{1,2}月\d{1,2}[号日]',
        r'(?:\d{1,2}\s*月\s*)?\d{1,2}\s*[号日]',
    ]
    return any(re.search(pat, text) for pat in indicators)


def _parse_numeric_month_day(text: str) -> date | None:
    """解析 9.29 / 9-29 / 9月29日 这类月日。"""
    match = re.search(r'(?<!\d)(\d{1,2})\s*(?:[.\-/月])\s*(\d{1,2})\s*(?:号|日)?(?!\d)', text)
    if not match:
        return None
    month = int(match.group(1))
    day = int(match.group(2))
    today = date.today()
    try:
        target = date(today.year, month, day)
    except ValueError:
        return None
    if target < today:
        target = date(today.year + 1, month, day)
    return target


def _detect_special_date_reminder(text: str) -> dict[str, Any] | None:
    """生日/纪念日/节日等日期提醒，默认当天 09:00 提醒。"""
    target_date = _parse_numeric_month_day(text)
    if not target_date or not any(word in text for word in SPECIAL_DATE_WORDS):
        return None

    title = extract_event_title(text)
    if not title:
        title = next((word for word in SPECIAL_DATE_WORDS if word in text), '提醒')
    title = title.replace('我生日', '我的生日').replace('我的的生日', '我的生日')
    start = datetime(target_date.year, target_date.month, target_date.day, 9, 0)
    end = start + timedelta(hours=1)
    entities = {
        'title': title,
        'type': 'POINT',
        'time_range': {'start': start.isoformat(), 'end': end.isoformat()},
        'start_time': start.isoformat(),
        'end_time': end.isoformat(),
        'date': target_date.isoformat(),
        'need_info': [],
        'reminder_type': 'special_date',
    }
    return {
        'intent': 'create_event',
        'sub_tasks': [{'action': 'check_calendar', 'params': entities}],
        '_pending_event': entities,
        'confidence': 0.90,
        'source': 'special_date_detector',
        '_skip_planner': True,
    }


def _detect_todo_query(text: str) -> dict[str, Any] | None:
    """查询待办队列。兼容“代办”错别字。"""
    if not any(word in text.lower() for word in TODO_QUERY_WORDS):
        return None
    if not _is_query(text):
        return None
    return {
        'intent': 'query_todos',
        'sub_tasks': [{'action': 'list_todos', 'params': {'status': 'ACTIVE'}}],
        'confidence': 0.88,
        'source': 'todo_query_detector',
        '_skip_planner': True,
    }


def _is_event_like(text: str) -> bool:
    """
    检测文本是否像日程事件 (动作词 / 事件名词)

    不要求 "我要/帮我/安排" 等指令词
    只要时间表达 + 动作词/事件名词 → 日程
    """
    keywords = [
        # ── 单字动作动词 ──
        '打', '开', '做', '写', '见', '去', '看', '吃', '学', '买',
        '跑', '练', '教', '讲', '修', '理', '洗', '寄', '取', '送',
        '约', '签', '谈', '逛', '玩', '飞', '交', '睡', '喝',
        # ── 双字动作/活动 ──
        '开会', '沟通', '讨论', '商量', '汇报', '面试', '拜访',
        '提交', '参加',
        '出差', '旅行', '旅游', '回家', '搬家', '购物', '逛街',
        '健身', '游泳', '打球', '跑步', '瑜伽', '跳舞',
        '看病', '体检', '复查', '打针', '吃药',
        '上课', '考试', '复习', '学习', '培训', '答辩',
        '唱歌', '聚餐', '吃饭', '喝酒', '聚会',
        '睡觉', '休息', '午休', '起床',
        '看电影', '看剧', '看展', '看书', '听歌',
        '打扫', '整理', '收拾', '做饭', '洗碗',
        '接人', '送人', '接机', '送机',
        '签约', '付款', '报销', '报税',
        '保养', '维修', '审车', '加油',
        # ── 事件名词 (本身即是日程) ──
        '会议', '报告', '演讲', '发布会', '讲座', '课程',
        '婚礼', '葬礼', '展览', '演出', '音乐会', '比赛',
        # ── 三字+ ──
        '做头发', '做美容', '做指甲', '做体检',
    ]
    return any(kw in text for kw in keywords)


UPDATE_WORDS = [
    '改到', '改成', '调整到', '调整', '挪到', '换到', '换成',
    '延后', '推迟', '提前', '顺延', '移动到',
]
DELETE_WORDS = ['取消', '删除', '删掉', '删了', '去掉', '移除', '不用', '放弃']


def _extract_mutation_title(text: str, trigger_words: list[str]) -> str:
    """从修改/取消表达中提取被操作的日程标题。"""
    normalized = _normalize_time_aliases(text)
    before = normalized
    for word in sorted(trigger_words, key=len, reverse=True):
        if word in normalized:
            before = normalized.split(word, 1)[0] if word not in DELETE_WORDS else normalized.replace(word, '', 1)
            break
    title = extract_event_title(before) or extract_event_title(normalized)
    for suffix in ('的日程', '日程', '的安排', '安排'):
        if title.endswith(suffix):
            title = title[:-len(suffix)].strip()
            break
    return title


def _detect_mutation_statement(text: str) -> dict[str, Any] | None:
    """识别修改/取消已有日程, 避免被误判成自然创建。"""
    normalized = _normalize_time_aliases(text)
    is_delete = any(word in normalized for word in DELETE_WORDS)
    is_update = any(word in normalized for word in UPDATE_WORDS)
    if not is_delete and not is_update:
        return None

    from agent_service.services.time_resolver import resolve_time_range
    title = _extract_mutation_title(normalized, DELETE_WORDS if is_delete else UPDATE_WORDS)
    time_text = normalized
    if is_update:
        for word in sorted(UPDATE_WORDS, key=len, reverse=True):
            if word in normalized:
                time_text = normalized.split(word, 1)[1]
                break
    tr = resolve_time_range(time_text)
    params = {
        'title': title,
        'raw_text': text,
    }
    if tr.get('time_range'):
        params['time_range'] = tr['time_range']
        params['start_time'] = tr['time_range'].get('start')
        params['end_time'] = tr['time_range'].get('end')
        params['type'] = tr.get('type', 'UNKNOWN')
    if is_delete:
        return {
            'intent': 'delete_event',
            'sub_tasks': [{'action': 'delete_task', 'params': params}],
            'confidence': 0.82,
            'source': 'event_detector',
            '_skip_planner': True,
        }
    return {
        'intent': 'update_event',
        'sub_tasks': [{'action': 'update_task', 'params': params}],
        'confidence': 0.82,
        'source': 'event_detector',
        '_skip_planner': True,
    }


def _is_query(text: str) -> bool:
    """判断是否为查询而非创建"""
    query_words = [
        '什么', '怎么', '吗', '呢', '如何', '有没有', '查看', '查询',
        '啥', '谁', '哪里', '干嘛', '干啥', '有什么事', '有什么安排',
        '告诉我', '看一下', '查一下',
    ]
    return any(qw in text for qw in query_words) or '?' in text or '？' in text


WEATHER_KEYWORDS = ('天气', '气温', '下雨', '降温', '温度', '几度', '多少度')

# ── 时间/日期噪声 (先清洗再抽城市) ──
_TIME_NOISE_WORDS = (
    '大后天', '后天', '明天', '今天', '昨天',
    '下周', '这周', '本周', '下个月', '月底',
    '星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日',
    '周一', '周二', '周三', '周四', '周五', '周六', '周日',
    '上午', '下午', '晚上', '中午', '早上', '早晨', '傍晚',
)

# 数字日期模式 (8-12 / 08-12 / 8.12 / 8/12 / 8月12号 等)
_DATE_NOISE_RE = re.compile(
    r'\d{4}[-./]\d{1,2}[-./]\d{1,2}'    # 2026-08-12
    r'|\d{1,2}[-./]\d{1,2}(?:[-./]\d{2,4})?'  # 8-12 / 08-12 / 8-12-2026
    r'|\d{1,2}月\d{1,2}[号日]?'           # 8月12号
)


def _clean_time_noise(text: str) -> str:
    """Step 1: 清洗时间词 + 数字日期, 再抽城市"""
    result = text
    # (a) text noise words
    for word in sorted(_TIME_NOISE_WORDS, key=len, reverse=True):
        result = result.replace(word, '')
    # (b) numeric date patterns
    result = _DATE_NOISE_RE.sub('', result)
    return result


def _resolve_weather_date(text: str) -> tuple[str, str, str]:
    """
    Step 2: 日期解析 (从原始文本)
    Returns: (iso_date, time_type, time_value)
      time_type: today | relative | absolute
      time_value: today | tomorrow | ... | 2026-08-12
    """
    today = date.today()

    # ── (a) 数字日期: 8-12 / 08-12 / 8月12号 / 2026-08-12 ──
    m_num = re.search(r'(?:^|[^\d])(\d{1,2})[-./](\d{1,2})(?:[-./]\d{2,4})?[号日]?(?:[^\d]|$)', text)
    if m_num:
        month = int(m_num.group(1))
        day = int(m_num.group(2))
        if 1 <= month <= 12 and 1 <= day <= 31:
            try:
                resolved = date(today.year, month, day)
                if resolved < today:
                    resolved = date(today.year + 1, month, day)  # 跨年
                return (resolved.isoformat(), 'absolute',
                        f'{resolved.month}月{resolved.day}日')
            except ValueError:
                pass

    # ── (b) YYYY-MM-DD ──
    m_iso = re.search(r'(\d{4})-(\d{2})-(\d{2})', text)
    if m_iso:
        return (f'{m_iso.group(1)}-{m_iso.group(2)}-{m_iso.group(3)}',
                'absolute', f'{m_iso.group(2)}月{m_iso.group(3)}日')

    # ── (c) 星期: 下周一 / 周五 / 下周 等 ──
    if any(w in text for w in ('周一', '周二', '周三', '周四', '周五', '周六', '周日',
                                '星期一', '星期二', '星期三', '星期四', '星期五', '星期六', '星期日',
                                '下周', '这周', '本周')):
        from agent_service.services.time_resolver import resolve_time_range
        tr = resolve_time_range(text)
        if tr.get('time_range') and tr['time_range'].get('start'):
            d = tr['time_range']['start'][:10]
            return (d, 'absolute', d)

    # ── (d) 相对日: 大后天 / 后天 / 明天 ──
    if '大后天' in text:
        return ((today + timedelta(days=3)).isoformat(),
                'relative', 'day_after_day_after_tomorrow')
    if '后天' in text:
        return ((today + timedelta(days=2)).isoformat(),
                'relative', 'day_after_tomorrow')
    if '明天' in text:
        return ((today + timedelta(days=1)).isoformat(),
                'relative', 'tomorrow')

    # ── (d) 默认今天 ──
    return (today.isoformat(), 'today', 'today')


def _extract_weather_city(cleaned_text: str) -> str:
    """
    Step 3: 城市提取 (从已清洗时间+日期的文本)
    返回城市名, 默认 '北京'
    """
    marker = next((keyword for keyword in WEATHER_KEYWORDS if keyword in cleaned_text), '')
    if not marker:
        return '北京'
    prefix = cleaned_text.split(marker, 1)[0]
    # 清理残余虚词
    prefix = re.sub(r'(的|怎么样|如何|吗|呢|啊|吧|呀|在|有|没有|会|不会|会不会)', '', prefix)
    prefix = re.sub(r'[，。！？?、\s]', '', prefix)
    if 2 <= len(prefix) <= 8:
        return prefix
    return '北京'


def _extract_weather_period(text: str) -> str | None:
    """提取时段: afternoon / evening / morning"""
    if any(w in text for w in ('下午',)):
        return 'afternoon'
    if any(w in text for w in ('晚上', '傍晚')):
        return 'evening'
    if any(w in text for w in ('上午', '早上', '早晨')):
        return 'morning'
    return None


def _detect_weather_query(text: str) -> dict[str, Any] | None:
    """天气查询 → 三层解析: Location / Date / QueryType"""
    if not any(keyword in text for keyword in WEATHER_KEYWORDS):
        return None
    if not _is_query(text) and not any(word in text for word in ('查', '看', '下雨', '几度', '多少度')):
        return None

    # ═══ Step 1: 清洗时间噪声 ═══
    cleaned = _clean_time_noise(text)

    # ═══ Step 2: 日期解析 ═══
    iso_date, time_type, time_value = _resolve_weather_date(text)

    # ═══ Step 3: 城市提取 ═══
    city = _extract_weather_city(cleaned)

    # ═══ Step 4: 时段 (可选) ═══
    period = _extract_weather_period(text)

    entities: dict[str, Any] = {
        'city': city,
        'time': {'type': time_type, 'value': time_value},
    }
    if period:
        entities['period'] = period

    return {
        'intent': 'query_weather',
        'sub_tasks': [{'action': 'query_weather', 'params': {
            'city': city,
            'date': iso_date,
        }}],
        'entities': entities,
        'confidence': 0.95,
        'source': 'event_detector',
        '_skip_planner': True,
    }


def _detect_event_statement(text: str) -> dict[str, Any]:
    """
    规则引擎: 检测事件陈述

    条件: 有时间表达 + 有动作词/事件名 → create_event
         有时间表达 + 查询词        → query_schedule
         只有时间表达               → query_schedule (倾向查询)
         都没有                     → chat (进 planner)
    """
    text = _normalize_time_aliases(text)
    if is_out_of_scope_request(text):
        return {
            'intent': 'chat',
            'sub_tasks': [],
            'final_reply': out_of_scope_reply(),
            'confidence': 0.95,
            'source': 'out_of_scope_guard',
            '_skip_planner': True,
        }

    todo_query = _detect_todo_query(text)
    if todo_query:
        return todo_query

    mutation = _detect_mutation_statement(text)
    if mutation:
        return mutation

    weather = _detect_weather_query(text)
    if weather:
        return weather

    special_date = _detect_special_date_reminder(text)
    if special_date:
        return special_date

    has_time = _has_time_indicator(text)
    is_query = _is_query(text)
    title = extract_event_title(text)
    is_event = _is_event_like(text)  # 动作词/事件名词检测
    has_event = bool(title) and is_event  # 有标题 + 像事件

    # ── 查询类: 有时间 + 疑问 → RANGE ──
    if has_time and is_query:
        time_info = _parse_time(text)
        # 用 RANGE 的 start/end, 否则用 reference_date 构造全天范围
        st = time_info.get('start_time') or f'{time_info.get("reference_date", date.today().isoformat())}T00:00:00'
        et = time_info.get('end_time') or f'{time_info.get("reference_date", date.today().isoformat())}T23:59:59'
        return {
            'intent': 'query_schedule',
            'sub_tasks': [
                {'action': 'check_calendar', 'params': {
                    'start_time': st,
                    'end_time': et,
                }},
            ],
            'confidence': 0.75,
            'source': 'event_detector',
            '_skip_planner': True,
        }

    # ── 创建类: 有时间 + 有事件名 ──
    if has_time and has_event:
        from agent_service.services.time_resolver import resolve_time_range
        tr = resolve_time_range(text)
        time_type = tr.get('type', 'UNKNOWN')
        time_range = tr.get('time_range') or {}

        # RANGE (有日期无时刻) → create_todo (不追问具体时间)
        if time_type == 'RANGE':
            due_date = time_range.get('start', '')[:10] if time_range.get('start') else ''
            return {
                'intent': 'create_todo',
                'sub_tasks': [
                    {'action': 'save_pending_todo', 'params': {
                        'title': title,
                        'due_date': due_date,
                    }},
                ],
                'confidence': 0.78,
                'source': 'event_detector',
                '_skip_planner': True,
            }

        # POINT → create_event (正常日程)
        entities = {
            'title': title,
            'type': time_type,
            'time_range': tr.get('time_range'),
            'start_time': time_range.get('start'),
            'end_time': time_range.get('end'),
            'date': tr.get('date'),
            'need_info': [],
        }
        return {
            'intent': 'create_event',
            'sub_tasks': [
                {'action': 'check_calendar', 'params': entities},
            ],
            '_pending_event': entities,
            'confidence': 0.88,
            'source': 'event_detector',
            '_skip_planner': True,
        }

    # ── 有事件名但无时间 → create_todo (Redis 暂存) ──
    if not has_time and has_event:
        return {
            'intent': 'create_todo',
            'sub_tasks': [
                {'action': 'save_pending_todo', 'params': {
                    'title': title,
                    'due_date': '',
                }},
            ],
            'confidence': 0.70,
            'source': 'event_detector',
            '_skip_planner': True,
        }

    # ── 只有时间没有事件 + 疑问 → 查询 ──
    if has_time and not has_event and is_query:
        time_info = _parse_time(text)
        st = time_info.get('start_time') or f'{time_info.get("reference_date", date.today().isoformat())}T00:00:00'
        et = time_info.get('end_time') or f'{time_info.get("reference_date", date.today().isoformat())}T23:59:59'
        return {
            'intent': 'query_schedule',
            'sub_tasks': [
                {'action': 'check_calendar', 'params': {
                    'start_time': st,
                    'end_time': et,
                }},
            ],
            'confidence': 0.65,
            'source': 'event_detector',
            '_skip_planner': True,
        }

    # ── 无时间无事件 → 交给 planner ──
    return {
        'intent': '',
        'sub_tasks': [],
        'confidence': 0.0,
        'source': 'event_detector',
        '_skip_planner': False,
    }


# ═══════════════════════════════════════════════════════
# LangGraph Node
# ═══════════════════════════════════════════════════════

async def event_detector_node(state: dict) -> dict[str, Any]:
    """
    Event Detector — 规则引擎优先

    日程类确定任务不浪费 LLM token。
    只有规则引擎无法判断的才交给 planner。
    """
    user_input = state.get('user_input', '')
    print(f'[EVENT_DET] "{user_input[:40]}"')

    result = _detect_event_statement(user_input)

    import json
    intent = result.get('intent',''); skip = result.get('_skip_planner',False)
    print(f'[EVENT_DET] → intent={intent} skip_llm={skip}')

    return result
