"""
Conflict Resolver — 独立对话状态机 + 轻量解析器

不经过 planner / event_detector / LLM
输入: user_input + pending_action (从 Redis 加载)

═══════════════════════════════════════════════════
ConflictChoiceParser (regex, 零 LLM token)
═══════════════════════════════════════════════════

  "B方案吧 换到晚上九点"  →  {choice:"B", new_time:"2026-08-06T21:00:00"}
  "选A"                  →  {choice:"A"}
  "第二个 改到明天下午3点"  →  {choice:"B", new_time:"..."}
  "取消"                  →  {cancel:true}

═══════════════════════════════════════════════════
状态机
═══════════════════════════════════════════════════

  waiting_choice
     │
     ├── 精确 A/B/C → execute_plan → waiting_confirm
     │
     ├── 自然语言(含choice+参数) → execute_plan → waiting_confirm
     │
     ├── 自然语言(含choice, 参数模糊) → clarification
     │     │
     │     └── 用户澄清 → execute_plan → waiting_confirm
     │
     ├── 取消/放弃 → clear
     │
     └── 完全无法解析 → clarification (NOT abandon!)
           │
           └── 用户澄清/放弃 → ...

  waiting_confirm
     │
     ├── 确认 → commit → clear
     │
     └── 取消 → clear
"""
import re
from datetime import date, timedelta, datetime
from dataclasses import dataclass, field
from typing import Any
from agent_service.graph.pending_task import (
    STAGE_WAITING_CHOICE, STAGE_WAITING_CONFIRM,
    STAGE_COMMITTED, STAGE_CANCELLED,
)
from agent_service.utils.coordinator import (
    RESCHEDULE_PENDING, RESCHEDULE_TASK, DISCARD_PENDING, COMMIT_PENDING, DELETE_TASK,
)


CONFIRM_WORDS = {
    '确认', '确定', '是', '是的', '对', '对的', '好', '好的', '可以', '行',
    '同意', '执行', '就这样', '没问题', '嗯', '嗯嗯', 'YES', 'Y', 'OK', 'OKAY',
    'yes', 'y', 'ok', 'okay',
}


# ═══════════════════════════════════════════════════
# ConflictChoice — 解析结果
# ═══════════════════════════════════════════════════

@dataclass
class ConflictChoice:
    choice: str | None = None        # "A" | "B" | "C"
    new_time: str | None = None      # ISO datetime "2026-08-06T21:00:00"
    cancel: bool = False
    raw: str = ""                    # 原始输入

    @property
    def is_valid(self) -> bool:
        return bool(self.choice) or self.cancel


# ═══════════════════════════════════════════════════
# ConflictChoiceParser — 零 LLM, 纯 regex
# ═══════════════════════════════════════════════════

class ConflictChoiceParser:
    """
    轻量解析器: 从自然语言中提取 choice + override 参数

    设计原则:
      - 不调用 LLM, 零 token 消耗
      - 日程是确定任务, regex 够用
      - 不清楚时返回 None → 上层发 clarification
    """

    # ── Choice 模式 ──
    CHOICE_ORDINAL = {
        '一': 'A', '第一个': 'A', '1': 'A',
        '二': 'B', '第二个': 'B', '两': 'B', '2': 'B',
        '三': 'C', '第三个': 'C', '3': 'C',
    }

    @classmethod
    def parse(cls, text: str, options: dict) -> ConflictChoice:
        """
        解析用户输入

        Args:
            text: 用户原始输入 (保持原样, 不上 strip/upper)
            options: pending_action 中的 options dict
        """
        result = ConflictChoice(raw=text)

        # ── 1. 检测取消 ──
        if cls._is_cancel(text):
            result.cancel = True
            return result

        # ── 2. 提取 Choice ──
        result.choice = cls._extract_choice(text, options)
        if not result.choice:
            result.choice = cls._infer_choice(text, options)

        # ── 3. 提取参考日期 (从冲突事件, 非今天) ──
        ref_date = cls._extract_reference_date(options, result.choice)

        # ── 4. 提取新时间 (使用冲突日期作为基准) ──
        result.new_time = cls._extract_relative_time(text, options, result.choice)
        if not result.new_time:
            result.new_time = cls._extract_new_time(text, reference_date=ref_date)

        return result

    @classmethod
    def _extract_reference_date(cls, options: dict, choice: str | None) -> str | None:
        """从 options 提取冲突事件日期作为时间解析基准"""
        if choice and choice in options:
            t = options[choice].get('move_time', '')
            if t:
                return t[:10]
        for opt in options.values():
            t = opt.get('move_time', '')
            if t:
                return t[:10]
        return None

    @classmethod
    def _is_cancel(cls, text: str) -> bool:
        t = text.strip()
        return t in ('取消', '算了', '不用了', '放弃', 'cancel', 'CANCEL')

    @classmethod
    def _extract_choice(cls, text: str, options: dict) -> str | None:
        """从文本中直接提取 A/B/C"""
        upper = text.strip().upper()

        # "B" / "A" / "C" 独立输入
        if upper in options:
            return upper

        # "B方案吧" / "选B" / "B方案" / "方案B"
        m = re.search(r'[ABCabc]', text)
        if m:
            ch = m.group().upper()
            if ch in options:
                return ch

        # "第一个" / "第二个" / "第三个"
        for word, ch in cls.CHOICE_ORDINAL.items():
            if word in text and ch in options:
                return ch

        return None

    @classmethod
    def _infer_choice(cls, text: str, options: dict) -> str | None:
        """
        无明确字母 → 从语义推断
        新格式: options 的 description 字段包含任务名
        """
        if any(word in text for word in ('调整客户沟通', '改客户沟通', '挪客户沟通', '推迟客户沟通')):
            for key, opt in options.items():
                for action in opt.get('actions', []):
                    if action.get('type') == RESCHEDULE_TASK:
                        return key
        if any(word in text for word in ('调整学习', '改学习', '挪学习', '推迟学习')):
            for key, opt in options.items():
                for action in opt.get('actions', []):
                    if action.get('type') == RESCHEDULE_PENDING:
                        return key
        if '保留客户沟通' in text:
            for key, opt in options.items():
                if opt.get('preview', {}).get('keep') == '客户沟通':
                    return key
        if '保留学习' in text:
            for key, opt in options.items():
                if opt.get('preview', {}).get('keep') == '学习':
                    return key
        for key, opt in options.items():
            desc = opt.get('description', '')
            titles = re.findall(r'「([^」]+)」', desc)
            if desc and titles and all(title in text for title in titles[:1]):
                return key
        return None

    @classmethod
    def _extract_new_time(cls, text: str, reference_date: str | None = None) -> str | None:
        """
        提取时间修改意图

        "换到晚上九点"     → 使用 reference_date (冲突事件日期)
        "改到明天下午3点"  → 明天15:00
        "挪到后天上午"     → 后天09:00

        Bug4 修复: 没有显式日期时, 使用冲突事件日期, 不是今天
        """
        time_intent = re.search(r'(换到|改到|挪到|推迟到|提前到|调整到|换成|改成)', text)
        if not time_intent:
            return cls._extract_direct_time(text, reference_date=reference_date)

        after = text[time_intent.end():]
        return cls._parse_time_expression(after, reference_date=reference_date)

    @classmethod
    def _extract_direct_time(cls, text: str, reference_date: str | None = None) -> str | None:
        """Parse bare time replies in confirmation, e.g. “那就早上九点吧”."""
        if not re.search(r'(早上|早晨|上午|中午|下午|晚上|傍晚|\d{1,2}\s*点|[一二两三四五六七八九十]{1,2}\s*点)', text):
            return None
        return cls._parse_time_expression(text, reference_date=reference_date)

    @classmethod
    def _extract_relative_time(cls, text: str, options: dict, choice: str | None) -> str | None:
        """解析“延后一小时/提前半小时/推迟30分钟”这类相对调整。"""
        if not choice or choice not in options:
            return None
        direction = 0
        if any(word in text for word in ('延后', '推迟', '往后', '顺延')):
            direction = 1
        elif any(word in text for word in ('提前', '往前')):
            direction = -1
        if not direction:
            return None

        minutes = cls._extract_duration_minutes(text)
        if not minutes:
            return None

        base = options[choice].get('move_to', '') or options[choice].get('move_time', '')
        if not base:
            return None
        try:
            return (datetime.fromisoformat(base) + direction * timedelta(minutes=minutes)).isoformat()
        except (TypeError, ValueError):
            return None

    @classmethod
    def _extract_duration_minutes(cls, text: str) -> int | None:
        # Handle colloquial Chinese duration: "提前一个钟" = 60 minutes.
        if any(token in text for token in ("\u4e00\u4e2a\u949f", "\u4e00\u949f", "1\u4e2a\u949f", "1\u949f")):
            return 60
        if '半小时' in text or '半个小时' in text:
            return 30
        m = re.search(r'(\d+|[一二两三四五六七八九十]{1,2})\s*(个)?\s*小时', text)
        if m:
            val = cls._duration_num_to_int(m.group(1))
            return val * 60 if val else None
        m = re.search(r'(\d+|[一二两三四五六七八九十]{1,2})\s*分钟', text)
        if m:
            return cls._duration_num_to_int(m.group(1))
        return None

    @classmethod
    def _duration_num_to_int(cls, raw: str) -> int | None:
        if raw.isdigit():
            return int(raw)
        cn = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
              '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}
        if raw in cn:
            return cn[raw]
        if len(raw) == 2 and raw[0] == '十':
            return 10 + cn.get(raw[1], 0)
        return None

    @classmethod
    def _parse_time_expression(cls, text: str, reference_date: str | None = None) -> str | None:
        """
        解析时间表达 → ISO datetime string

        Bug4 修复: reference_date 是冲突事件日期 (来自 options.move_time)
        没有显式日期时, 基准是 reference_date, 不是今天
        """
        # 基准日期: 优先冲突事件日期, 否则今天
        if reference_date:
            try:
                base_date = datetime.strptime(reference_date, '%Y-%m-%d').date()
            except (ValueError, TypeError):
                base_date = date.today()
        else:
            base_date = date.today()

        hour, minute = None, 0

        # ── 中文数字 → int ──
        _CN = {'一': 1, '二': 2, '两': 2, '三': 3, '四': 4, '五': 5,
               '六': 6, '七': 7, '八': 8, '九': 9, '十': 10}

        def _cn_to_int(s: str) -> int | None:
            if s.isdigit():
                return int(s)
            if s in _CN:
                return _CN[s]
            if len(s) == 2 and s[0] == '十':
                return 10 + _CN.get(s[1], 0)
            return None

        # ── 提取小时间分钟 ──
        HOUR_CN = r'(\d{1,2}|[一二两三四五六七八九十]{1,2})'
        m = re.search(rf'(下午|晚上|傍晚|中午)\s*{HOUR_CN}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)
        if not m:
            m = re.search(rf'(上午|早上|早晨)\s*{HOUR_CN}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)
        if not m:
            m = re.search(rf'(?<![上下午晚早中午])[\s]{HOUR_CN}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)
        if not m:
            m = re.search(rf'^{HOUR_CN}\s*点\s*(半|(\d{{1,2}})\s*分)?', text)

        if m:
            groups = m.groups()
            period = groups[0] if groups[0] else ''
            hour_raw = groups[1]
            half_or_min = groups[2] if len(groups) > 2 else None

            h = _cn_to_int(hour_raw)
            if h is not None:
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

        # 只有时段没有具体时间 → 默认整点
        if hour is None:
            if '晚上' in text:
                hour = 20
            elif '下午' in text:
                hour = 15
            elif '上午' in text or '早上' in text:
                hour = 9
            elif '中午' in text:
                hour = 12
            else:
                return None  # 无法解析

        # ── 提取日期 ──
        day_names = {'周一': 0, '周二': 1, '周三': 2, '周四': 3, '周五': 4, '周六': 5, '周日': 6,
                     '星期一': 0, '星期二': 1, '星期三': 2, '星期四': 3, '星期五': 4, '星期六': 5, '星期日': 6}
        d = base_date
        if '明天' in text:
            d = base_date + timedelta(days=1)
        elif '后天' in text:
            d = base_date + timedelta(days=2)
        elif any(name in text for name in day_names):
            for name, wd in day_names.items():
                if name in text:
                    days = wd - base_date.weekday()
                    if days <= 0:
                        days += 7
                    d = base_date + timedelta(days=days)
                    break
        elif hour is not None and hour < 12 and reference_date is None:
            # 上午的时间, 如果现在是下午 → 默认明天
            now = datetime.now()
            if now.hour >= 12:
                d = base_date + timedelta(days=1)

        return f'{d.isoformat()}T{hour:02d}:{minute:02d}:00'


# ═══════════════════════════════════════════════════
# LangGraph Node
# ═══════════════════════════════════════════════════

async def conflict_resolver_node(state: dict) -> dict[str, Any]:
    """
    冲突解决状态机

    状态: waiting_choice | waiting_confirm | clarification
    """
    # Resume: 从 interrupt 恢复暂停的 conflict
    if state.get('_flow_paused'):
        paused = state.get('_paused_pending')
        if paused:
            state['pending_action'] = paused
        state['_flow_paused'] = False

    pending = state.get('pending_action', {})
    stage = pending.get('stage', STAGE_WAITING_CHOICE)
    user_input = state.get('user_input', '')
    _hydrate_pending_move_times(pending, state.get('pending_tasks', []))
    options = pending.get('options', {})

    print(f'[CONFLICT] {stage} "{user_input[:30]}"')

    # ═══════════════════════════════════
    # 全局: 取消/放弃 (任何 stage)
    # ═══════════════════════════════════
    if ConflictChoiceParser._is_cancel(user_input):
        print(f'[CONFLICT] {stage}→CANCEL')
        # 取被取消的任务标题
        ptasks = state.get('pending_tasks', [])
        cancelled = ptasks[0].get('title', '') if ptasks else ''
        return await _clear('已取消冲突处理。需要帮你安排什么？',
                            pending_tasks=ptasks, cancelled_title=cancelled)

    # ═══════════════════════════════════
    # Stage: clarification
    # ═══════════════════════════════════
    if stage == 'clarification':
        return _handle_clarification(pending, user_input)

    if stage == STAGE_WAITING_CONFIRM:
        return _handle_confirm(pending, user_input)

    # ═══════════════════════════════════
    # Stage: waiting_choice
    # ═══════════════════════════════════
    return await _handle_choice(pending, user_input, options)


def _hydrate_pending_move_times(pending: dict, pending_tasks: list[dict]) -> None:
    """兼容旧 Redis 状态: 从 pending_tasks 回填方案的原始时间。"""
    if not pending or not pending_tasks:
        return

    by_ref = {
        task.get('ref_id'): task
        for task in pending_tasks
        if task.get('ref_id')
    }
    for option in (pending.get('options', {}) or {}).values():
        if option.get('move_time'):
            continue
        for action in option.get('actions', []) or []:
            if action.get('type') != RESCHEDULE_PENDING:
                continue
            task = by_ref.get(action.get('ref_id'))
            if task:
                move_time = task.get('start_time') or task.get('time', '')
                if move_time:
                    option['move_time'] = move_time
                    break


# ═══════════════════════════════════════════════════
# Stage handlers
# ═══════════════════════════════════════════════════

async def _handle_choice(pending: dict, user_input: str,
                         options: dict) -> dict[str, Any]:
    """waiting_choice 阶段: 解析用户输入 → 执行/确认/澄清"""

    # ── 轻量解析 ──
    parsed = ConflictChoiceParser.parse(user_input, options)

    # ── 精确 A/B/C (无附加参数) ──
    if parsed.choice and not parsed.new_time:
        return _execute_plan(parsed.choice, options, pending)

    # ── A/B/C + 时间修改 ──
    if parsed.choice and parsed.new_time:
        opt = options.get(parsed.choice, {})
        move_target = opt.get('move', opt.get('new_task', ''))
        return _execute_plan_with_override(
            parsed.choice, options, pending,
            move_to=parsed.new_time,
            move_target=move_target,
        )

    # ── 语义推断成功 ──
    if parsed.choice:
        return _execute_plan(parsed.choice, options, pending)

    # ── 完全无法解析 → clarification (NOT abandon!) ──
    print(f'[CONFLICT] unparsable → clarification')
    labels = _describe_options(options)
    return {
        'needs_confirmation': True,
        'pending_action': {
            **pending,
            'stage': 'clarification',  # 内部 stage, 不是 conflict stage
        },
        '_confirm_message': (
            f'不太确定你的意思。当前可选方案:\n{labels}\n'
            f'你可以说 "选B"、 "B方案, 换到晚上九点" 或 "取消"。'
        ),
        '_issues': ['unparsable_input'],
        '_skip_validator': True,
    }


def _handle_clarification(pending: dict, user_input: str) -> dict[str, Any]:
    """clarification 阶段: 用户澄清 → 重新解析"""
    options = pending.get('options', {})

    # 重新解析 (用户可能这次说清楚了)
    parsed = ConflictChoiceParser.parse(user_input, options)

    if parsed.choice:
        if parsed.new_time:
            opt = options.get(parsed.choice, {})
            move_target = opt.get('move', opt.get('new_task', ''))
            return _execute_plan_with_override(
                parsed.choice, options, pending,
                move_to=parsed.new_time,
                move_target=move_target,
            )
        return _execute_plan(parsed.choice, options, pending)

    # 仍然无法理解 → 最后一次尝试
    labels = _describe_options(options)
    return {
        'needs_confirmation': True,
        'pending_action': {**pending, 'stage': 'clarification'},
        '_confirm_message': (
            f'还是不太确定。你可以直接回复字母:\n{labels}\n'
            f'或者回复 "取消" 放弃这次冲突处理。'
        ),
        '_issues': ['still_unclear'],
        '_skip_validator': True,
    }


def _handle_confirm(pending: dict, user_input: str) -> dict[str, Any]:
    """waiting_confirm 阶段: 确认/取消"""
    upper = user_input.strip().upper()

    if user_input.strip() in CONFIRM_WORDS or upper in CONFIRM_WORDS:
        # 从 options + plan 重建 commit actions
        plan = pending.get('selected_plan', '')
        options = pending.get('options', {})
        entities = pending.get('entities', pending.get('task_data', {}))
        move_to = (options.get(plan, {}) or {}).get('move_to', '')
        summary = pending.get('summary', '')

        opt = options.get(plan, {})
        if opt.get('requires_time') and not move_to:
            title = _plan_target_title(opt, entities)
            return {
                'intent': 'update_event',
                'sub_tasks': [],
                'needs_confirmation': True,
                'pending_action': {**pending, 'stage': STAGE_WAITING_CONFIRM},
                'pending_tasks': [],
                'active_flow': 'conflict_resolution',
                '_confirm_message': (
                    f'请先指定「{title}」的新时间，再点同意执行。\n'
                    f'例如：换到晚上九点 / 改到明天下午三点。'
                ),
                '_skip_validator': True,
            }
        sub_tasks = _build_commit_actions(plan, options, entities, move_to)
        print(f'[CONFLICT] confirm→COMMIT {len(sub_tasks)}acts plan={plan}')

        if not sub_tasks:
            return {
                'intent': 'chat',
                'sub_tasks': [],
                'needs_confirmation': True,
                'pending_action': {},
                'pending_tasks': [],
                'active_flow': None,
                '_confirm_message': opt.get('confirm_reply') or '好的，已按该方案处理。',
                '_skip_validator': True,
            }

        # execution_context
        action = opt.get('action', {})
        move_title = _get_title(action.get('target'), entities)

        return {
            'intent': 'update_event',
            'sub_tasks': sub_tasks,
            'needs_confirmation': False,
            'pending_action': {},
            'pending_tasks': [],   # 清空
            'active_flow': None,
            'execution_context': {
                'reason': 'conflict_resolution',
                'selected_plan': plan,
                'summary': summary,
                'action_type': (opt.get('action', {}) or {}).get('type', ''),
                'target_title': move_title,
            },
            '_skip_validator': True,
        }

    # ── 时间修改? (往后延一个小时 / 换到晚上九点) ──
    plan = pending.get('selected_plan', '')
    options = pending.get('options', {})
    ref_date = ConflictChoiceParser._extract_reference_date(options, plan)
    new_time = ConflictChoiceParser._extract_relative_time(user_input, options, plan)
    if not new_time:
        new_time = ConflictChoiceParser._extract_new_time(user_input, reference_date=ref_date)
    if new_time:
        entities = pending.get('entities', pending.get('task_data', {}))
        opt = options.get(plan, {})
        # 更新 proposed_actions 中的时间
        proposed = pending.get('proposed_actions', [])
        for p in proposed:
            p['new_time'] = new_time
        # 更新 options 中的 move_to
        opt['move_to'] = new_time
        options[plan] = opt

        title = _get_title(
            (opt.get('actions', [{}])[0] or {}).get('ref_id') or
            (opt.get('actions', [{}])[0] or {}).get('task_id', ''),
            entities)
        print(f'[CONFLICT] time→{new_time[:16]}')
        return {
            'needs_confirmation': True,
            'pending_action': {
                **pending,
                'stage': STAGE_WAITING_CONFIRM,
                'proposed_actions': proposed,
                'options': options,
            },
            '_confirm_message': (
                f'好的，已调整：\n'
                f'「{title}」\n'
                f'{_fmt_time(new_time)}\n\n'
                f'确认执行吗？'),
            '_skip_validator': True,
        }

    # ── 无法理解 → 询问确认, 不重置 ──
    labels = _describe_options(pending.get('options', {}))
    print('[CONFLICT] ambiguous→ask')
    return {
        'needs_confirmation': True,
        'pending_action': {**pending, 'stage': STAGE_WAITING_CONFIRM},
        '_confirm_message': f'回复「确认」执行，或指定新时间（如 "换到晚上九点"）。\n{labels}',
        '_issues': [],
        '_skip_validator': True,
    }


# ═══════════════════════════════════════════════════
# Plan execution

def _get_title(target, entities: dict) -> str:
    entities = entities or {}
    if target in entities:
        return (entities.get(target) or {}).get('title', '')
    if isinstance(target, int):
        key = str(target)
        if key in entities:
            return (entities.get(key) or {}).get('title', '')
    if isinstance(target, str) and target.isdigit():
        key = int(target)
        if key in entities:
            return (entities.get(key) or {}).get('title', '')
    return (entities.get(str(target), {}) or {}).get('title', '')


def _build_commit_actions(plan: str, options: dict, entities: dict,
                          move_to: str = '') -> list[dict]:
    """
    confirm: options[plan].actions → commit sub_tasks.
    reschedule_pending → commit_pending, update_task → update_task.
    兼容新旧 options 格式.
    """
    if plan not in options:
        return []
    opt = options[plan]
    actions = opt.get("actions", [])
    # 兼容旧格式: {"action": {"type": ..., "target": ...}}
    if not actions and "action" in opt:
        actions = [opt["action"]]
    result = []
    for a in actions:
        atype = a.get("type", "")
        if atype == RESCHEDULE_PENDING:
            ref_id = a.get("ref_id") or a.get("target", "")
            params = {"ref_id": ref_id, "title": _get_title(ref_id, entities)}
            if move_to and not a.get("preserve_time"):
                params["start_time"] = move_to
            result.append({"action": COMMIT_PENDING, "params": params})
        elif atype == RESCHEDULE_TASK:
            tid = a.get("task_id") or a.get("target", 0)
            params = {"task_id": tid, "title": _get_title(tid, entities), "_check_conflict": True}
            if move_to:
                params["start_time"] = move_to
            result.append({"action": "update_task", "params": params})
        elif atype == DELETE_TASK:
            tid = a.get("task_id") or a.get("target", 0)
            result.append({"action": "delete_task", "params": {
                "task_id": tid, "title": _get_title(tid, entities),
            }})
    return result


def _execute_plan(choice: str, options: dict, pending: dict) -> dict:
    opt = options.get(choice, {})
    entities = pending.get("entities", pending.get("task_data", {}))
    move_to = opt.get("move_to", "")
    actions = opt.get("actions", [])

    print(f'[CONFLICT] choice={choice} acts={[a.get("type","")[:8] for a in actions]}')

    if not actions:
        t = opt.get("preview", {}).get("discard", "")
        opt["confirm_reply"] = f"好的，已取消「{t}」。" if t else "好的，已取消这次安排。"
        options[choice] = opt
        return _to_confirm(choice, pending, options, proposed=[],
            summary=f'不创建「{t}」(冲突已取消)。',
            confirm_msg=f'好的，不创建「{t}」。确认吗？')

    first = actions[0]
    atype = first.get("type", "")
    target = first.get("ref_id") or first.get("task_id")
    title = _get_title(target, entities)

    # 生成 proposed: 无时间时也生成 confirm 时执行的 action
    tool_actions = []
    if atype == RESCHEDULE_PENDING:
        if move_to:
            tool_actions = [{"action": "reschedule_pending", "ref_id": target,
                             "target": title, "new_time": move_to}]
        else:
            # 无时间也生成 commit_pending (使用 PendingTask 原时间)
            tool_actions = [{"action": COMMIT_PENDING, "ref_id": target, "target": title}]
    elif atype == RESCHEDULE_TASK:
        if move_to:
            tool_actions = [{"action": "update_task", "task_id": target,
                             "target": title, "new_time": move_to}]
        else:
            tool_actions = [{"action": "update_task", "task_id": target, "target": title}]
    elif atype == DELETE_TASK:
        tool_actions = [{"action": "delete_task", "task_id": target, "target": title}]

    return _to_confirm(choice, pending, options, proposed=tool_actions,
        summary=opt.get("label", ""), confirm_msg=_build_confirm_msg(opt, move_to, entities))


def _execute_plan_with_override(choice: str, options: dict, pending: dict,
                                move_to: str, move_target: str) -> dict:
    """Fix1: RESCHEDULE_PENDING -> immediate reschedule(Redis) + proposed commit_pending"""
    opt = options.get(choice, {})
    opt['move_to'] = move_to
    options[choice] = opt
    entities = pending.get("entities", pending.get("task_data", {}))
    actions = opt.get("actions", [])

    print(f'[CONFLICT] choice={choice}+override {move_to[:16]}')

    immediate = []
    later = []
    for a in actions:
        atype = a.get("type", "")
        target = a.get("ref_id") or a.get("task_id")
        title = _get_title(target, entities)
        if atype == RESCHEDULE_PENDING:
            if a.get("preserve_time"):
                later.append({"action": COMMIT_PENDING, "ref_id": target, "target": title})
                continue
            immediate.append({"action": "reschedule_pending", "params": {
                "ref_id": target, "title": title, "new_time": move_to,
            }})
            later.append({"action": "reschedule_pending", "ref_id": target, "target": title, "new_time": move_to})
        elif atype == RESCHEDULE_TASK:
            later.append({"action": "update_task", "task_id": target, "target": title, "new_time": move_to})

    return _to_confirm_with_immediate(choice, pending, options,
        immediate_sub_tasks=immediate, proposed=later,
        summary=opt.get("label", ""), confirm_msg=_build_confirm_msg(opt, move_to, entities))


def _to_confirm_with_immediate(plan_id: str, pending: dict, options: dict,
                                immediate_sub_tasks: list, proposed: list,
                                summary: str, confirm_msg: str) -> dict:
    return {
        'intent': 'update_event',
        'sub_tasks': immediate_sub_tasks,
        'needs_confirmation': True,
        'pending_action': {
            'type': 'conflict_resolution', 'stage': STAGE_WAITING_CONFIRM,
            'selected_plan': plan_id, 'proposed_actions': proposed,
            'summary': summary, 'options': options,
            'entities': pending.get('entities', pending.get('task_data', {})),
        },
        '_confirm_message': confirm_msg, '_skip_validator': True,
    }


def _build_confirm_msg(opt: dict, move_to: str, entities: dict) -> str:
    actions = opt.get("actions", [])
    if not actions:
        return '好的。确认吗？'
    target = actions[0].get("ref_id") or actions[0].get("task_id")
    title = _get_title(target, entities)
    if move_to:
        return f'好的。\n\n已计划把「{title}」调整到：\n📅 {_fmt_time(move_to)}\n\n确认执行吗？'
    return f'已选择调整「{title}」。\n请先指定新时间，例如“换到晚上九点”。'


def _plan_target_title(opt: dict, entities: dict) -> str:
    actions = opt.get("actions", [])
    if not actions:
        return opt.get("preview", {}).get("discard", "这项日程")
    target = actions[0].get("ref_id") or actions[0].get("task_id")
    return _get_title(target, entities) or "这项日程"


def _fmt_time(iso: str) -> str:
    try:
        from datetime import datetime
        dt = datetime.fromisoformat(iso)
        return f'{dt.month}月{dt.day}日 {dt.hour:02d}:{dt.minute:02d}'
    except Exception:
        return iso[:16]

# Helpers
# ═══════════════════════════════════════════════════

async def _clear(message: str, pending_tasks: list = None,
                cancelled_title: str = "") -> dict[str, Any]:
    """终态: 清除 conflict + Redis PendingTasks + active_flow"""
    for pt in (pending_tasks or []):
        ref_id = pt.get('ref_id', pt.get('_ref_id', ''))
        if ref_id:
            from agent_service.graph.pending_task import delete_pending
            await delete_pending(ref_id)
    msg = message
    if cancelled_title:
        msg = f"好的，已取消「{cancelled_title}」。"
    return {
        'intent': 'chat',
        'sub_tasks': [],
        'needs_confirmation': True,  # 直接展示消息, 不走后续节点
        'pending_action': {},
        'pending_tasks': [],
        'active_flow': None,
        '_confirm_message': msg,
        '_skip_validator': True,
    }


def _to_confirm(plan_id: str, pending: dict, options: dict,
                proposed: list[dict], summary: str,
                confirm_msg: str) -> dict[str, Any]:
    """中间态: → waiting_confirm. 保留 task_data 供 commit 使用."""
    return {
        'intent': 'update_event',
        'sub_tasks': [],
        'needs_confirmation': True,
        'pending_action': {
            'type': 'conflict_resolution',
            'stage': STAGE_WAITING_CONFIRM,
            'selected_plan': plan_id,
            'proposed_actions': proposed,
            'summary': summary,
            'options': options,
            'entities': pending.get('entities', pending.get('task_data', {})),
        },
        '_confirm_message': confirm_msg,
        '_skip_validator': True,
    }


def _describe_options(options: dict) -> str:
    """生成可读的选项描述 (适配 ref 格式)"""
    lines = []
    for key in sorted(options.keys()):
        desc = options[key].get('description', '')
        if desc:
            lines.append(f'  [{key}] {desc}')
    return '\n'.join(lines)
