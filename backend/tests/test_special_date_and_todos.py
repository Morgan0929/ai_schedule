import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_service.graph.event_detector import _detect_event_statement


class SpecialDateAndTodoTest(unittest.TestCase):
    def test_birthday_numeric_date_skips_llm(self):
        result = _detect_event_statement("9.29我生日")

        self.assertEqual(result["intent"], "create_event")
        self.assertTrue(result["_skip_planner"])
        self.assertEqual(result["_pending_event"]["title"], "我的生日")
        self.assertTrue(result["_pending_event"]["start_time"].endswith("T09:00:00"))

    def test_todo_query_accepts_common_typo(self):
        result = _detect_event_statement("目前我有什么代办的吗")

        self.assertEqual(result["intent"], "query_todos")
        self.assertEqual(result["sub_tasks"][0]["action"], "list_todos")


if __name__ == "__main__":
    unittest.main()
