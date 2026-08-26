import sys
import unittest
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_service.graph.event_detector import _detect_event_statement, extract_event_title


class EventTitleConnectorTest(unittest.TestCase):
    def test_keeps_person_connector_after_time(self):
        self.assertEqual(
            extract_event_title("明天早上八点和女神吃早餐"),
            "和女神吃早餐",
        )
        self.assertEqual(
            extract_event_title("后天中午跟朋友吃饭"),
            "跟朋友吃饭",
        )
        self.assertEqual(
            extract_event_title("周五晚上七点与客户沟通"),
            "与客户沟通",
        )

    def test_create_event_uses_connector_title(self):
        result = _detect_event_statement("明天早上八点和女神吃早餐")

        self.assertEqual(result["intent"], "create_event")
        self.assertEqual(result["_pending_event"]["title"], "和女神吃早餐")


if __name__ == "__main__":
    unittest.main()
