import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_service.graph.graph import _build_schedule_reply, _extract_query_label


class ScheduleReplyTest(unittest.TestCase):
    def test_combines_course_and_task_items(self):
        reply = _build_schedule_reply(
            [
                {
                    "title": "线性代数",
                    "start_time": "2026-08-31T08:30:00",
                    "end_time": "2026-08-31T09:15:00",
                    "location": "A101",
                    "source": "course",
                    "section_label": "第1节",
                },
                {
                    "title": "项目评审",
                    "start_time": "2026-08-31T15:00:00",
                    "end_time": "2026-08-31T16:00:00",
                    "location": "会议室",
                    "source": "task",
                },
            ],
            [],
            "月底31号",
        )["final_reply"]

        self.assertIn("月底31号", reply)
        self.assertIn("课程｜第1节 线性代数", reply)
        self.assertIn("项目评审", reply)
        self.assertIn("A101", reply)

    def test_query_label_keeps_month_end_phrasing(self):
        self.assertEqual(_extract_query_label("我这月底31号有什么安排"), "月底31号")


if __name__ == "__main__":
    unittest.main()
