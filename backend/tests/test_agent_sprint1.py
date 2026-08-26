"""
Sprint 1 Agent 测试集 — 50 条
覆盖: event_detector / planner / normalize_intent
"""
import sys
sys.path.insert(0, '.')

from agent_service.graph.schemas import normalize_intent, Intent
from agent_service.graph.event_detector import _detect_event_statement, extract_event_title


# ═══════════════════ 1. Intent 归一化 (15 条) ═══════════════════

def test_normalize_intent():
    cases = [
        # (raw, expected)
        ("create_task", "create_event"),
        ("create_todo", "create_event"),
        ("create_reminder", "create_event"),
        ("create_event", "create_event"),
        ("update_task", "update_event"),
        ("update_event", "update_event"),
        ("delete_task", "delete_event"),
        ("delete_event", "delete_event"),
        ("query_calendar", "query_schedule"),
        ("query_schedule", "query_schedule"),
        ("query_weather", "query_weather"),
        ("chat", "chat"),
        ("casual_chat", "chat"),
        ("arrange_trip", "create_event"),
        ("conflict_negotiation", "create_event"),
    ]
    passed = 0
    for raw, expected in cases:
        result = normalize_intent(raw).value
        ok = result == expected
        if ok: passed += 1
        print(f"  {'OK' if ok else 'FAIL'} | {raw} → {result} (expected {expected})")
    print(f"  [{passed}/{len(cases)}] normalize_intent")
    return passed == len(cases)


# ═══════════════════ 2. Event Detector — 创建事件 (15 条) ═══════════════════

def test_event_detector_create():
    cases = [
        # (input, expected_intent, should_skip)
        ("明天下午三点打游戏", "create_event", True),
        ("后天上午十点客户沟通", "create_event", True),
        ("周五下午开会", "create_event", True),
        ("下周一下午三点拜访客户", "create_event", True),
        ("明天晚上看电影", "create_event", True),
        ("下午三点开会讨论项目", "create_event", True),
        ("明天8点起床", "create_event", True),
        ("今天晚上聚餐", "create_event", True),
        ("下周一出差上海", "create_event", True),
        ("明天下午三点半做PPT", "create_event", True),
        ("后天中午和朋友吃饭", "create_event", True),
        ("周五晚上七点健身", "create_event", True),
        ("周六上午十点学车", "create_event", True),
        ("明天考试", "create_event", True),
        ("晚上十点提醒睡觉", "create_event", True),
    ]
    passed = 0
    for text, exp_intent, exp_skip in cases:
        r = _detect_event_statement(text)
        ok = r['intent'] == exp_intent and r['_skip_planner'] == exp_skip
        if ok: passed += 1
        print(f"  {'OK' if ok else 'FAIL'} | {text} → intent={r['intent']} skip={r['_skip_planner']}")
    print(f"  [{passed}/{len(cases)}] event_detector create")
    return passed == len(cases)


# ═══════════════════ 3. Event Detector — 查询 (5 条) ═══════════════════

def test_event_detector_query():
    cases = [
        ("明天有什么安排", "query_schedule", True),
        ("查一下明天的日程", "query_schedule", True),
        ("这周有什么安排", "query_schedule", True),
        ("周五有事吗", "query_schedule", True),
        ("下午有会议吗", "query_schedule", True),
    ]
    passed = 0
    for text, exp_intent, exp_skip in cases:
        r = _detect_event_statement(text)
        ok = r['intent'] == exp_intent and r['_skip_planner'] == exp_skip
        if ok: passed += 1
        print(f"  {'OK' if ok else 'FAIL'} | {text} → intent={r['intent']}")
    print(f"  [{passed}/{len(cases)}] event_detector query")
    return passed == len(cases)


# ═══════════════════ 4. Event Detector — 非事件/chat (10 条) ═══════════════════

def test_event_detector_chat():
    cases = [
        ("今天心情真好", False),
        ("你好", False),
        ("帮我写代码", True),
        ("帮我写一段关于二分查找的代码", True),
        ("什么是机器学习", True),
        ("讲个笑话", True),
        ("今天天气不错", False),
        ("推荐一部电影", True),
        ("怎么学好英语", True),
        ("明天下午", False),      # only time, no verb → not event
        ("三点半", False),        # only time, no verb
    ]
    passed = 0
    for text, expect_skip in cases:
        r = _detect_event_statement(text)
        # 普通闲聊走 planner；明确越界请求直接拒绝，避免误建待办。
        ok = r['_skip_planner'] == expect_skip and not r.get('sub_tasks')
        if ok: passed += 1
        print(f"  {'OK' if ok else 'FAIL'} | {text} → skip={r['_skip_planner']} (expected {expect_skip})")
    print(f"  [{passed}/{len(cases)}] event_detector chat")
    return passed == len(cases)


# ═══════════════════ 5. extract_event_title (5 条) ═══════════════════

def test_extract_title():
    cases = [
        ("明天下午三点打游戏", "打游戏"),
        ("后天上午十点客户沟通", "客户沟通"),
        ("帮我安排周五晚上的会议", "会议"),
        ("晚上八点提醒我开会", "开会"),
        ("下周一下午三点拜访客户", "拜访客户"),
    ]
    passed = 0
    for text, expected in cases:
        result = extract_event_title(text)
        ok = result == expected
        if ok: passed += 1
        print(f"  {'OK' if ok else 'FAIL'} | {text} → '{result}' (expected '{expected}')")
    print(f"  [{passed}/{len(cases)}] extract_event_title")
    return passed == len(cases)


# ═══════════════════ RUN ALL ═══════════════════

if __name__ == "__main__":
    print("=== Sprint 1 Agent Test Suite (50 cases) ===\n")

    results = {
        "normalize_intent (15)": test_normalize_intent(),
        "event_detector create (15)": test_event_detector_create(),
        "event_detector query (5)": test_event_detector_query(),
        "event_detector chat (10)": test_event_detector_chat(),
        "extract_event_title (5)": test_extract_title(),
    }

    print(f"\n=== RESULTS ===")
    passed = sum(1 for v in results.values() if v)
    total = len(results)
    for name, ok in results.items():
        print(f"  {'PASS' if ok else 'FAIL'} | {name}")
    print(f"\n{passed}/{total} test groups passed")
