import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_service.graph.conflict_resolver import _handle_confirm


class ConflictConfirmTest(unittest.TestCase):
    def test_common_yes_words_confirm_selected_discard_plan(self):
        pending = {
            "selected_plan": "C",
            "options": {
                "C": {
                    "actions": [],
                    "confirm_reply": "好的，已取消「吃饭」。",
                }
            },
            "summary": "不创建吃饭",
        }

        for word in ("yes", "好的", "同意", "确认"):
            with self.subTest(word=word):
                result = _handle_confirm(pending, word)

                self.assertEqual(result["active_flow"], None)
                self.assertEqual(result["pending_action"], {})
                self.assertEqual(result["_confirm_message"], "好的，已取消「吃饭」。")

    def test_requires_time_plan_cannot_confirm_without_new_time(self):
        pending = {
            "selected_plan": "A",
            "options": {
                "A": {
                    "actions": [{"type": "reschedule_task", "task_id": 7}],
                    "requires_time": True,
                }
            },
            "entities": {"7": {"title": "打游戏"}},
            "summary": "保留已有，调整打游戏",
        }

        result = _handle_confirm(pending, "同意")

        self.assertTrue(result["needs_confirmation"])
        self.assertEqual(result["intent"], "update_event")
        self.assertEqual(result["sub_tasks"], [])
        self.assertEqual(result["active_flow"], "conflict_resolution")
        self.assertEqual(result["pending_action"]["stage"], "waiting_confirm")
        self.assertIn("请先指定「打游戏」的新时间", result["_confirm_message"])

    def test_bare_time_reply_updates_selected_plan_time(self):
        pending = {
            "selected_plan": "B",
            "options": {
                "B": {
                    "actions": [
                        {"type": "reschedule_task", "task_id": 7},
                        {"type": "reschedule_pending", "ref_id": "pending-1", "preserve_time": True},
                    ],
                    "requires_time": True,
                    "move_time": "2026-08-18T08:00:00",
                }
            },
            "entities": {"7": {"title": "吃早餐"}},
            "summary": "保留起床，调整吃早餐",
        }

        result = _handle_confirm(pending, "那就早上九点吧")

        self.assertTrue(result["needs_confirmation"])
        self.assertEqual(
            result["pending_action"]["options"]["B"]["move_to"],
            "2026-08-18T09:00:00",
        )
        self.assertIn("8月18日 09:00", result["_confirm_message"])


if __name__ == "__main__":
    unittest.main()
