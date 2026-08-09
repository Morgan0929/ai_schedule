"""
Agent deterministic parsing tests.

Run without third-party test dependencies:
    venv\\Scripts\\python.exe tests\\test_time_resolver.py
"""
from __future__ import annotations

import asyncio
import sys
import unittest
from datetime import date
from pathlib import Path

BACKEND_DIR = Path(__file__).resolve().parents[1] / "backend"
if str(BACKEND_DIR) not in sys.path:
    sys.path.insert(0, str(BACKEND_DIR))

import agent_service.graph.event_detector as event_detector
import agent_service.graph.pending_task as pending_task
from agent_service.graph.graph import input_classifier_node, pending_conflict_detector_node, reply_node, route_after_tools
from agent_service.graph.conflict_resolver import _get_title, _hydrate_pending_move_times, conflict_resolver_node
from agent_service.graph.event_detector import _detect_event_statement
from agent_service.graph.pending_task import STAGE_WAITING_CHOICE, STAGE_WAITING_CONFIRM, pending_task_ref
from agent_service.services import time_resolver
from agent_service.services.time_resolver import resolve_time_range
from agent_service.utils.coordinator import coordinator_node

TODAY = date(2026, 8, 6)  # Thursday


class FrozenDate(date):
    @classmethod
    def today(cls):
        return TODAY


TIME_CASES = [
    ("今天", "RANGE", "2026-08-06T00:00:00", "2026-08-06T23:59:59"),
    ("明天", "RANGE", "2026-08-07T00:00:00", "2026-08-07T23:59:59"),
    ("后天", "RANGE", "2026-08-08T00:00:00", "2026-08-08T23:59:59"),
    ("周四", "RANGE", "2026-08-06T00:00:00", "2026-08-06T23:59:59"),
    ("周五", "RANGE", "2026-08-07T00:00:00", "2026-08-07T23:59:59"),
    ("周六", "RANGE", "2026-08-08T00:00:00", "2026-08-08T23:59:59"),
    ("周日", "RANGE", "2026-08-09T00:00:00", "2026-08-09T23:59:59"),
    ("周一", "RANGE", "2026-08-10T00:00:00", "2026-08-10T23:59:59"),
    ("周二", "RANGE", "2026-08-11T00:00:00", "2026-08-11T23:59:59"),
    ("周三", "RANGE", "2026-08-12T00:00:00", "2026-08-12T23:59:59"),
    ("下周", "RANGE", "2026-08-10T00:00:00", "2026-08-10T23:59:59"),
    ("下周一", "RANGE", "2026-08-10T00:00:00", "2026-08-10T23:59:59"),
    ("下周二", "RANGE", "2026-08-11T00:00:00", "2026-08-11T23:59:59"),
    ("下周三", "RANGE", "2026-08-12T00:00:00", "2026-08-12T23:59:59"),
    ("下周四", "RANGE", "2026-08-13T00:00:00", "2026-08-13T23:59:59"),
    ("下周五", "RANGE", "2026-08-14T00:00:00", "2026-08-14T23:59:59"),
    ("下周六", "RANGE", "2026-08-15T00:00:00", "2026-08-15T23:59:59"),
    ("下周日", "RANGE", "2026-08-16T00:00:00", "2026-08-16T23:59:59"),
    ("这周五", "RANGE", "2026-08-07T00:00:00", "2026-08-07T23:59:59"),
    ("本周三", "RANGE", "2026-08-05T00:00:00", "2026-08-05T23:59:59"),
    ("下个月", "RANGE", "2026-09-01T00:00:00", "2026-09-01T23:59:59"),
    ("月底", "RANGE", "2026-08-31T00:00:00", "2026-08-31T23:59:59"),
    ("月末", "RANGE", "2026-08-31T00:00:00", "2026-08-31T23:59:59"),
    ("今天上午", "RANGE", "2026-08-06T08:00:00", "2026-08-06T12:00:00"),
    ("今天早上", "RANGE", "2026-08-06T07:00:00", "2026-08-06T12:00:00"),
    ("今天早晨", "RANGE", "2026-08-06T07:00:00", "2026-08-06T12:00:00"),
    ("今天中午", "RANGE", "2026-08-06T12:00:00", "2026-08-06T14:00:00"),
    ("今天下午", "RANGE", "2026-08-06T13:00:00", "2026-08-06T18:00:00"),
    ("今天傍晚", "RANGE", "2026-08-06T17:00:00", "2026-08-06T20:00:00"),
    ("今天晚上", "RANGE", "2026-08-06T18:00:00", "2026-08-06T23:00:00"),
    ("明天上午", "RANGE", "2026-08-07T08:00:00", "2026-08-07T12:00:00"),
    ("明天早上", "RANGE", "2026-08-07T07:00:00", "2026-08-07T12:00:00"),
    ("明天中午", "RANGE", "2026-08-07T12:00:00", "2026-08-07T14:00:00"),
    ("明天下午", "RANGE", "2026-08-07T13:00:00", "2026-08-07T18:00:00"),
    ("明天傍晚", "RANGE", "2026-08-07T17:00:00", "2026-08-07T20:00:00"),
    ("明天晚上", "RANGE", "2026-08-07T18:00:00", "2026-08-07T23:00:00"),
    ("后天上午", "RANGE", "2026-08-08T08:00:00", "2026-08-08T12:00:00"),
    ("后天下午", "RANGE", "2026-08-08T13:00:00", "2026-08-08T18:00:00"),
    ("后天晚上", "RANGE", "2026-08-08T18:00:00", "2026-08-08T23:00:00"),
    ("周五上午", "RANGE", "2026-08-07T08:00:00", "2026-08-07T12:00:00"),
    ("周五下午", "RANGE", "2026-08-07T13:00:00", "2026-08-07T18:00:00"),
    ("周五晚上", "RANGE", "2026-08-07T18:00:00", "2026-08-07T23:00:00"),
    ("周六早上", "RANGE", "2026-08-08T07:00:00", "2026-08-08T12:00:00"),
    ("周六中午", "RANGE", "2026-08-08T12:00:00", "2026-08-08T14:00:00"),
    ("周日傍晚", "RANGE", "2026-08-09T17:00:00", "2026-08-09T20:00:00"),
    ("下周一上午", "RANGE", "2026-08-10T08:00:00", "2026-08-10T12:00:00"),
    ("下周一下午", "RANGE", "2026-08-10T13:00:00", "2026-08-10T18:00:00"),
    ("下周五晚上", "RANGE", "2026-08-14T18:00:00", "2026-08-14T23:00:00"),
    ("下个月上午", "RANGE", "2026-09-01T08:00:00", "2026-09-01T12:00:00"),
    ("月底下午", "RANGE", "2026-08-31T13:00:00", "2026-08-31T18:00:00"),
    ("明早", "RANGE", "2026-08-07T07:00:00", "2026-08-07T12:00:00"),
    ("今晚", "RANGE", "2026-08-06T18:00:00", "2026-08-06T23:00:00"),
    ("明晚", "RANGE", "2026-08-07T18:00:00", "2026-08-07T23:00:00"),
    ("今天8点", "POINT", "2026-08-06T08:00:00", "2026-08-06T09:00:00"),
    ("明天8点", "POINT", "2026-08-07T08:00:00", "2026-08-07T09:00:00"),
    ("后天9点", "POINT", "2026-08-08T09:00:00", "2026-08-08T10:00:00"),
    ("下周一8点", "POINT", "2026-08-10T08:00:00", "2026-08-10T09:00:00"),
    ("周五3点", "POINT", "2026-08-07T03:00:00", "2026-08-07T04:00:00"),
    ("3点", "POINT", "2026-08-06T03:00:00", "2026-08-06T04:00:00"),
    ("三点", "POINT", "2026-08-06T03:00:00", "2026-08-06T04:00:00"),
    ("三点半", "POINT", "2026-08-06T03:30:00", "2026-08-06T04:30:00"),
    ("8点30分", "POINT", "2026-08-06T08:30:00", "2026-08-06T09:30:00"),
    ("上午8点", "POINT", "2026-08-06T08:00:00", "2026-08-06T09:00:00"),
    ("早上8点", "POINT", "2026-08-06T08:00:00", "2026-08-06T09:00:00"),
    ("早晨七点", "POINT", "2026-08-06T07:00:00", "2026-08-06T08:00:00"),
    ("中午12点", "POINT", "2026-08-06T12:00:00", "2026-08-06T13:00:00"),
    ("下午三点", "POINT", "2026-08-06T15:00:00", "2026-08-06T16:00:00"),
    ("下午三点半", "POINT", "2026-08-06T15:30:00", "2026-08-06T16:30:00"),
    ("下午3点", "POINT", "2026-08-06T15:00:00", "2026-08-06T16:00:00"),
    ("下午3点30分", "POINT", "2026-08-06T15:30:00", "2026-08-06T16:30:00"),
    ("傍晚六点", "POINT", "2026-08-06T18:00:00", "2026-08-06T19:00:00"),
    ("晚上八点", "POINT", "2026-08-06T20:00:00", "2026-08-06T21:00:00"),
    ("晚上8点30分", "POINT", "2026-08-06T20:30:00", "2026-08-06T21:30:00"),
    ("明天上午10点", "POINT", "2026-08-07T10:00:00", "2026-08-07T11:00:00"),
    ("明天早上8点", "POINT", "2026-08-07T08:00:00", "2026-08-07T09:00:00"),
    ("明天下午三点", "POINT", "2026-08-07T15:00:00", "2026-08-07T16:00:00"),
    ("明天下午3点", "POINT", "2026-08-07T15:00:00", "2026-08-07T16:00:00"),
    ("明天下午三点半", "POINT", "2026-08-07T15:30:00", "2026-08-07T16:30:00"),
    ("明天晚上8点", "POINT", "2026-08-07T20:00:00", "2026-08-07T21:00:00"),
    ("后天上午九点", "POINT", "2026-08-08T09:00:00", "2026-08-08T10:00:00"),
    ("后天下午2点", "POINT", "2026-08-08T14:00:00", "2026-08-08T15:00:00"),
    ("后天晚上十点", "POINT", "2026-08-08T22:00:00", "2026-08-08T23:00:00"),
    ("周五下午3点", "POINT", "2026-08-07T15:00:00", "2026-08-07T16:00:00"),
    ("周五晚上七点", "POINT", "2026-08-07T19:00:00", "2026-08-07T20:00:00"),
    ("周六上午十点", "POINT", "2026-08-08T10:00:00", "2026-08-08T11:00:00"),
    ("周日晚上8点30分", "POINT", "2026-08-09T20:30:00", "2026-08-09T21:30:00"),
    ("下周一下午三点", "POINT", "2026-08-10T15:00:00", "2026-08-10T16:00:00"),
    ("下周三上午九点", "POINT", "2026-08-12T09:00:00", "2026-08-12T10:00:00"),
    ("下周五晚上七点半", "POINT", "2026-08-14T19:30:00", "2026-08-14T20:30:00"),
    ("下个月下午三点", "POINT", "2026-09-01T15:00:00", "2026-09-01T16:00:00"),
    ("月底下午三点", "POINT", "2026-08-31T15:00:00", "2026-08-31T16:00:00"),
    ("查周五日程", "RANGE", "2026-08-07T00:00:00", "2026-08-07T23:59:59"),
    ("看看明天有什么安排", "RANGE", "2026-08-07T00:00:00", "2026-08-07T23:59:59"),
    ("明天下午三点打游戏", "POINT", "2026-08-07T15:00:00", "2026-08-07T16:00:00"),
    ("周五下午数学考试", "RANGE", "2026-08-07T13:00:00", "2026-08-07T18:00:00"),
    ("下个月去上海旅游", "RANGE", "2026-09-01T00:00:00", "2026-09-01T23:59:59"),
    ("后天上午十点客户沟通", "POINT", "2026-08-08T10:00:00", "2026-08-08T11:00:00"),
    ("下周一下午三点拜访客户", "POINT", "2026-08-10T15:00:00", "2026-08-10T16:00:00"),
    ("明早八点我要睡觉", "POINT", "2026-08-07T08:00:00", "2026-08-07T09:00:00"),
    ("下午三点客户沟通", "POINT", "2026-08-06T15:00:00", "2026-08-06T16:00:00"),
    ("周六参加婚礼", "RANGE", "2026-08-08T00:00:00", "2026-08-08T23:59:59"),
    ("月底交论文", "RANGE", "2026-08-31T00:00:00", "2026-08-31T23:59:59"),
    ("晚上提醒我买牛奶", "RANGE", "2026-08-06T18:00:00", "2026-08-06T23:00:00"),
    ("后天和朋友吃饭", "RANGE", "2026-08-08T00:00:00", "2026-08-08T23:59:59"),
    ("明天考试", "RANGE", "2026-08-07T00:00:00", "2026-08-07T23:59:59"),
]

A_CREATE_CASES = [
    ("明天早上8点上课", "上课", "POINT", "2026-08-07T08:00:00"),
    ("周五下午数学考试", "数学考试", "RANGE", "2026-08-07T13:00:00"),
    ("晚上提醒我买牛奶", "买牛奶", "RANGE", "2026-08-06T18:00:00"),
    ("下个月去上海旅游", "上海旅游", "RANGE", "2026-09-01T00:00:00"),
    ("后天和朋友吃饭", "朋友吃饭", "RANGE", "2026-08-08T00:00:00"),
    ("明天下午三点打游戏", "打游戏", "POINT", "2026-08-07T15:00:00"),
    ("后天上午十点客户沟通", "客户沟通", "POINT", "2026-08-08T10:00:00"),
    ("下周一下午三点拜访客户", "拜访客户", "POINT", "2026-08-10T15:00:00"),
    ("明天晚上看电影", "看电影", "RANGE", "2026-08-07T18:00:00"),
    ("今天晚上聚餐", "聚餐", "RANGE", "2026-08-06T18:00:00"),
    ("下周一出差上海", "出差上海", "RANGE", "2026-08-10T00:00:00"),
    ("明天下午三点半做PPT", "做PPT", "POINT", "2026-08-07T15:30:00"),
    ("周五晚上七点健身", "健身", "POINT", "2026-08-07T19:00:00"),
    ("周六上午十点学车", "学车", "POINT", "2026-08-08T10:00:00"),
    ("明天考试", "考试", "RANGE", "2026-08-07T00:00:00"),
    ("晚上十点提醒睡觉", "睡觉", "POINT", "2026-08-06T22:00:00"),
    ("月底交论文", "交论文", "RANGE", "2026-08-31T00:00:00"),
    ("明早八点我要睡觉", "睡觉", "POINT", "2026-08-07T08:00:00"),
    ("下午三点客户沟通", "客户沟通", "POINT", "2026-08-06T15:00:00"),
    ("周六参加婚礼", "参加婚礼", "RANGE", "2026-08-08T00:00:00"),
]


class TimeResolverAgentTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        time_resolver.date = FrozenDate
        event_detector.date = FrozenDate

        async def noop_save_pending(_pending):
            return None

        pending_task.save_pending = noop_save_pending

    def assert_time(self, text, expected_type, expected_start, expected_end):
        result = resolve_time_range(text, TODAY)
        time_range = result.get("time_range") or {}
        self.assertEqual(result["type"], expected_type, text)
        self.assertEqual(time_range.get("start"), expected_start, text)
        self.assertEqual(time_range.get("end"), expected_end, text)

    def test_time_resolver_100_real_inputs(self):
        self.assertGreaterEqual(len(TIME_CASES), 100)
        for case in TIME_CASES:
            with self.subTest(text=case[0]):
                self.assert_time(*case)

    def test_a_natural_create_intent_title_time_type(self):
        self.assertEqual(len(A_CREATE_CASES), 20)
        for text, expected_title, expected_type, expected_start in A_CREATE_CASES:
            with self.subTest(text=text):
                result = _detect_event_statement(text)
                event = result["_pending_event"]
                time_range = event["time_range"] or {}
                self.assertEqual(result["intent"], "create_event")
                self.assertIs(result["_skip_planner"], True)
                self.assertEqual(event["title"], expected_title)
                self.assertEqual(event["type"], expected_type)
                self.assertEqual(time_range.get("start"), expected_start)

    def test_b_implicit_create_expressions(self):
        cases = [
            ("明早八点我要睡觉", "睡觉", "POINT", "2026-08-07T08:00:00"),
            ("下午三点客户沟通", "客户沟通", "POINT", "2026-08-06T15:00:00"),
            ("周六参加婚礼", "参加婚礼", "RANGE", "2026-08-08T00:00:00"),
            ("月底交论文", "交论文", "RANGE", "2026-08-31T00:00:00"),
        ]
        for text, expected_title, expected_type, expected_start in cases:
            with self.subTest(text=text):
                result = _detect_event_statement(text)
                event = result["_pending_event"]
                self.assertEqual(result["intent"], "create_event")
                self.assertEqual(event["title"], expected_title)
                self.assertEqual(event["type"], expected_type)
                self.assertEqual((event["time_range"] or {}).get("start"), expected_start)

    def test_create_event_exposes_tool_start_and_end_time(self):
        result = _detect_event_statement("我明天九点想去喝早茶")
        event = result["_pending_event"]
        check_params = result["sub_tasks"][0]["params"]

        self.assertEqual(event["start_time"], "2026-08-07T09:00:00")
        self.assertEqual(event["end_time"], "2026-08-07T10:00:00")
        self.assertEqual(check_params["start_time"], "2026-08-07T09:00:00")
        self.assertEqual(check_params["end_time"], "2026-08-07T10:00:00")

    def test_create_event_without_go_keyword_still_detects_drink_event(self):
        result = _detect_event_statement("明天八点我要喝早茶")
        event = result["_pending_event"]

        self.assertEqual(result["intent"], "create_event")
        self.assertEqual(event["title"], "喝早茶")
        self.assertEqual(event["start_time"], "2026-08-07T08:00:00")

    def test_create_event_at_existing_time_enters_conflict_flow(self):
        parsed = _detect_event_statement("我明天九点想去喝早茶")
        detected = asyncio.run(pending_conflict_detector_node({
            "user_id": 0,
            "_pending_event": parsed["_pending_event"],
            "calendar_events": [
                {
                    "id": 27,
                    "title": "数学考试",
                    "start_time": "2026-08-07T09:00:00",
                    "end_time": "2026-08-07T10:00:00",
                }
            ],
            "pending_tasks": [],
        }))

        self.assertEqual(detected["conflict_count"], 1)
        self.assertEqual(detected["conflicts_found"][0]["existing_task"]["title"], "数学考试")
        self.assertEqual(detected["conflicts_found"][0]["pending_task"]["title"], "喝早茶")

    def test_create_event_tools_result_routes_to_pending_conflict_detector(self):
        parsed = _detect_event_statement("我明天九点想去喝早茶")
        self.assertEqual(route_after_tools({
            "intent": "create_event",
            "calendar_events": [
                {
                    "id": 27,
                    "title": "数学考试",
                    "start_time": "2026-08-07T09:00:00",
                    "end_time": "2026-08-07T10:00:00",
                }
            ],
            "_pending_event": parsed["_pending_event"],
        }), "pending_conflict_detector")

    def test_c_update_and_cancel_are_update_event(self):
        cases = [
            ("把下午的学习改到晚上", "update_task", "学习", "RANGE", "2026-08-06T18:00:00"),
            ("取消明天的会议", "delete_task", "会议", "RANGE", "2026-08-07T00:00:00"),
            ("客户沟通延后半小时", "update_task", "客户沟通", "UNKNOWN", None),
        ]
        for text, expected_action, expected_title, expected_type, expected_start in cases:
            with self.subTest(text=text):
                result = _detect_event_statement(text)
                task = result["sub_tasks"][0]
                params = task["params"]
                self.assertEqual(result["intent"], "update_event")
                self.assertEqual(task["action"], expected_action)
                self.assertEqual(params["title"], expected_title)
                self.assertEqual(params.get("type", "UNKNOWN"), expected_type)
                if expected_start:
                    self.assertEqual(params["time_range"]["start"], expected_start)

    def test_query_reply_uses_requested_date_label(self):
        classified = asyncio.run(input_classifier_node({"user_input": "查周日安排"}))
        self.assertEqual(classified["query_date_label"], "周日")
        self.assertEqual(classified["sub_tasks"][0]["params"], {
            "start_time": "2026-08-09T00:00:00",
            "end_time": "2026-08-09T23:59:59",
        })

        reply = asyncio.run(reply_node({
            "intent": "query_schedule",
            "user_input": "查周日安排",
            "calendar_events": [],
            "pending_tasks": [],
            "query_date_label": classified["query_date_label"],
        }))
        self.assertEqual(reply["final_reply"], "周日暂无已确认安排。")

    def test_d_conflict_coordination_builds_abc_options(self):
        result = asyncio.run(coordinator_node(_conflict_state()))
        options = result["pending_action"]["options"]
        self.assertEqual(result["active_flow"], "conflict_resolution")
        self.assertEqual(result["pending_action"]["stage"], STAGE_WAITING_CHOICE)
        self.assertEqual(options["A"]["label"], "保留「客户沟通」, 调整「学习」")
        self.assertEqual(options["A"]["actions"][0]["type"], "reschedule_pending")
        self.assertEqual(options["B"]["label"], "保留「学习」, 调整「客户沟通」")
        self.assertEqual(options["B"]["actions"][0]["type"], "update_task")
        self.assertEqual(options["C"]["label"], "取消「学习」")
        self.assertEqual(options["C"]["actions"], [])

    def test_pending_task_ref_keeps_start_time_for_relative_reschedule(self):
        ref = pending_task_ref({
            "ref_id": "pending_tea",
            "title": "喝早茶",
            "start_time": "2026-08-07T08:00:00",
            "end_time": "2026-08-07T09:00:00",
        })
        self.assertEqual(ref["time"], "2026-08-07T08:00:00")
        self.assertEqual(ref["start_time"], "2026-08-07T08:00:00")

    def test_d_conflict_options_accept_legacy_pending_time_field(self):
        result = asyncio.run(coordinator_node({
            "conflicts_found": [
                {
                    "existing_task": {
                        "id": 1,
                        "title": "考试",
                        "time": "2026-08-07T08:00",
                        "source": "database",
                    },
                    "pending_ref": "pending_tea",
                    "pending_task": {
                        "id": None,
                        "title": "喝早茶",
                        "time": "2026-08-07T08:00:00",
                        "source": "pending",
                        "ref_id": "pending_tea",
                    },
                    "level": "HARD",
                }
            ]
        }))
        self.assertEqual(result["pending_action"]["options"]["A"]["move_time"], "2026-08-07T08:00:00")

    def test_legacy_conflict_state_hydrates_move_time_from_pending_tasks(self):
        pending = {
            "options": {
                "A": {
                    "actions": [{"type": "reschedule_pending", "ref_id": "pending_tea"}],
                }
            }
        }
        _hydrate_pending_move_times(pending, [{
            "ref_id": "pending_tea",
            "title": "喝早茶",
            "time": "2026-08-07T08:00:00",
        }])
        self.assertEqual(pending["options"]["A"]["move_time"], "2026-08-07T08:00:00")

    def test_get_title_accepts_stringified_keys(self):
        entities = {"3": {"title": "喝早茶"}, 21: {"title": "客户沟通"}}
        self.assertEqual(_get_title(3, entities), "喝早茶")
        self.assertEqual(_get_title("21", entities), "客户沟通")

    def test_e_continuous_conflict_dialog_restores_pending_action_and_commits(self):
        first = asyncio.run(coordinator_node(_conflict_state()))
        pending_action = first["pending_action"]
        second = asyncio.run(conflict_resolver_node({
            "user_input": "调整客户沟通，换到晚上",
            "active_flow": "conflict_resolution",
            "pending_action": pending_action,
            "pending_tasks": [
                {"ref_id": "pending_learning", "title": "学习", "start_time": "2026-08-07T15:00:00"}
            ],
        }))

        self.assertEqual(second["pending_action"]["stage"], STAGE_WAITING_CONFIRM)
        self.assertEqual(second["pending_action"]["selected_plan"], "B")
        self.assertEqual(second["pending_action"]["options"]["B"]["move_to"], "2026-08-07T20:00:00")

        committed = asyncio.run(conflict_resolver_node({
            "user_input": "确认",
            "pending_action": second["pending_action"],
        }))
        self.assertIsNone(committed["active_flow"])
        self.assertEqual(committed["pending_action"], {})
        self.assertEqual(committed["sub_tasks"], [
            {
                "action": "update_task",
                "params": {
                    "task_id": 21,
                    "title": "客户沟通",
                    "_check_conflict": True,
                    "start_time": "2026-08-07T20:00:00",
                },
            },
            {
                "action": "commit_pending",
                "params": {
                    "ref_id": "pending_learning",
                    "title": "\u5b66\u4e60",
                },
            },
        ])

    def test_e_a_plan_relative_delay_commits_pending_at_new_time(self):
        first = asyncio.run(coordinator_node(_conflict_state()))
        pending_action = first["pending_action"]
        selected = asyncio.run(conflict_resolver_node({
            "user_input": "A方案 延后一小时吧",
            "active_flow": "conflict_resolution",
            "pending_action": pending_action,
            "pending_tasks": [
                {"ref_id": "pending_learning", "title": "学习", "start_time": "2026-08-07T15:00:00"}
            ],
        }))

        self.assertEqual(selected["pending_action"]["stage"], STAGE_WAITING_CONFIRM)
        self.assertEqual(selected["pending_action"]["selected_plan"], "A")
        self.assertEqual(selected["pending_action"]["options"]["A"]["move_to"], "2026-08-07T16:00:00")
        self.assertEqual(selected["sub_tasks"], [
            {
                "action": "reschedule_pending",
                "params": {
                    "ref_id": "pending_learning",
                    "title": "学习",
                    "new_time": "2026-08-07T16:00:00",
                },
            }
        ])

        committed = asyncio.run(conflict_resolver_node({
            "user_input": "确认",
            "pending_action": selected["pending_action"],
        }))
        self.assertEqual(committed["sub_tasks"], [
            {
                "action": "commit_pending",
                "params": {
                    "ref_id": "pending_learning",
                    "title": "学习",
                    "start_time": "2026-08-07T16:00:00",
                },
            }
        ])

    def test_e_confirm_stage_relative_time_uses_selected_plan_base(self):
        first = asyncio.run(coordinator_node(_conflict_state()))
        pending_action = first["pending_action"]
        selected = asyncio.run(conflict_resolver_node({
            "user_input": "A\u65b9\u6848 \u4e0a\u8bfe\u63d0\u524d\u4e00\u4e2a\u949f",
            "active_flow": "conflict_resolution",
            "pending_action": pending_action,
            "pending_tasks": [
                {"ref_id": "pending_learning", "title": "\u4e0a\u8bfe", "start_time": "2026-08-07T15:00:00"}
            ],
        }))

        self.assertEqual(selected["pending_action"]["stage"], STAGE_WAITING_CONFIRM)
        followup = asyncio.run(conflict_resolver_node({
            "user_input": "\u63d0\u524d\u4e00\u4e2a\u949f",
            "active_flow": "conflict_resolution",
            "pending_action": selected["pending_action"],
            "pending_tasks": [
                {"ref_id": "pending_learning", "title": "\u4e0a\u8bfe", "start_time": "2026-08-07T15:00:00"}
            ],
        }))

        self.assertEqual(followup["pending_action"]["stage"], STAGE_WAITING_CONFIRM)
        self.assertEqual(followup["pending_action"]["options"]["A"]["move_to"], "2026-08-07T13:00:00")


def _conflict_state():
    return {
        "conflicts_found": [
            {
                "existing_task": {
                    "id": 21,
                    "title": "客户沟通",
                    "time": "2026-08-07T15:00:00",
                    "source": "database",
                },
                "pending_ref": "pending_learning",
                "pending_task": {
                    "ref_id": "pending_learning",
                    "title": "学习",
                    "start_time": "2026-08-07T15:00:00",
                    "end_time": "2026-08-07T16:00:00",
                    "source": "pending",
                },
                "level": "HARD",
            }
        ]
    }


if __name__ == "__main__":
    unittest.main(verbosity=2)
