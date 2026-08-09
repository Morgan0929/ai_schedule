import asyncio
import sys
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_service.graph.event_detector import _detect_event_statement
from agent_service.graph.graph import input_classifier_node
from agent_service.graph.tools import _delete_task_shared


class DeleteEventTest(unittest.TestCase):
    def test_delete_request_bypasses_query_classifier(self):
        result = asyncio.run(
            input_classifier_node({"user_input": "把明天去图书馆的日程删了"})
        )
        self.assertEqual(result, {})

    def test_delete_request_extracts_title_and_time_range(self):
        result = _detect_event_statement("把明天去图书馆的日程删了")
        task = result["sub_tasks"][0]

        self.assertEqual(result["intent"], "delete_event")
        self.assertEqual(task["action"], "delete_task")
        self.assertEqual(task["params"]["title"], "图书馆")
        self.assertIn("time_range", task["params"])

    def test_delete_task_resolves_one_title_in_time_range(self):
        class Candidate:
            id = 13
            title = "图书馆"

        candidate = Candidate()

        class FakeRepo:
            async def find_by_user_time_range(self, user_id, start, end):
                return [candidate]

        class FakeTaskService:
            def __init__(self, db):
                self.repo = FakeRepo()

        class FakeDb:
            def __init__(self):
                self.deleted = []
                self.committed = False

            async def delete(self, task):
                self.deleted.append(task)

            async def commit(self):
                self.committed = True

        db = FakeDb()

        @asynccontextmanager
        async def fake_session_factory():
            yield db

        with patch("agent_service.graph.tools.async_session_factory", fake_session_factory), patch(
            "timeline_service.services.task_service.TaskService", FakeTaskService
        ):
            result = asyncio.run(
                _delete_task_shared(
                    user_id=0,
                    title="图书馆",
                    time_range={
                        "start": "2026-08-10T00:00:00",
                        "end": "2026-08-10T23:59:59",
                    },
                )
            )

        self.assertEqual(result, {"task_id": 13, "title": "图书馆", "status": "deleted"})
        self.assertEqual(db.deleted, [candidate])
        self.assertTrue(db.committed)


if __name__ == "__main__":
    unittest.main()
