import asyncio
import sys
import types
import unittest
from contextlib import asynccontextmanager
from pathlib import Path
from unittest.mock import patch

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from agent_service.graph.graph import (
    conflict_check_node,
    check_pending_action,
    reply_node,
    route_after_pending_detector,
    route_after_tools,
    should_check_conflicts,
)
from agent_service.graph.conflict_resolver import _build_commit_actions
from agent_service.utils.coordinator import coordinator_node


class ConflictRecheckTest(unittest.TestCase):
    def test_reply_prioritizes_new_conflict_over_completed_action(self):
        result = asyncio.run(
            reply_node(
                {
                    "intent": "update_event",
                    "actions_taken": ["Created Library"],
                    "conflicts_found": [{
                        "existing_task": {"id": 1, "title": "Breakfast", "time": "2026-08-10T07:00"},
                        "new_task": {"id": 2, "title": "Library", "time": "2026-08-10T07:00"},
                    }],
                    "suggestions": [{"plan_id": "A", "title": "Move Library"}],
                }
            )
        )

        self.assertIn("Breakfast", result["final_reply"])
        self.assertIn("Move Library", result["final_reply"])
        self.assertNotIn("Created Library", result["final_reply"])

    def test_persisted_second_conflict_uses_task_actions(self):
        result = asyncio.run(
            coordinator_node(
                {
                    "conflicts_found": [{
                        "existing_task": {"id": 1, "title": "Breakfast", "time": "2026-08-10T07:00"},
                        "new_task": {"id": 2, "title": "Gym", "time": "2026-08-10T07:00"},
                    }]
                }
            )
        )
        options = result["pending_action"]["options"]

        self.assertEqual(options["A"]["actions"], [{"type": "update_task", "task_id": 2}])
        self.assertEqual(options["B"]["actions"], [{"type": "update_task", "task_id": 1}])
        self.assertEqual(options["C"]["actions"], [{"type": "delete_task", "task_id": 2}])
        self.assertEqual(
            _build_commit_actions("C", options, result["pending_action"]["entities"]),
            [{"action": "delete_task", "params": {"task_id": 2, "title": "Gym"}}],
        )

    def test_conflict_routes_recheck_after_task_mutation(self):
        state = {
            "tasks_created": [42],
            "tasks_updated": [{"id": 7, "title": "Library", "new_time": "2026-08-06T07:00:00"}],
            "conflicts_found": [],
        }

        self.assertEqual(route_after_tools(state), "conflict_check")
        self.assertEqual(route_after_pending_detector(state), "conflict_check")
        self.assertEqual(should_check_conflicts(state), "conflict_check")

    def test_update_event_interrupts_conflict_flow(self):
        route = check_pending_action({
            "active_flow": "conflict_resolution",
            "pending_action": {"stage": "waiting_choice", "options": {}},
            "user_input": "把明天去面试的日程换到后天早上八点吧",
        })

        self.assertEqual(route, "input_classifier")

    def test_conflict_check_node_runs_for_updated_tasks(self):
        calls = {"repo": 0}

        class FakeTaskRepository:
            def __init__(self, db):
                self.db = db

            async def find_by_user_time_range(self, user_id, start, end):
                calls["repo"] += 1
                return [object(), object()]

        class FakeConflict:
            task_a_id = 1
            task_a_title = "Breakfast"
            task_b_id = 2
            task_b_title = "Library"
            overlap_start = "2026-08-06T07:30:00"
            severity = types.SimpleNamespace(value="HARD")
            reason = "overlap"

        class FakeReport:
            conflicts = [FakeConflict()]

        class FakeConflictDetector:
            def detect(self, tasks):
                return FakeReport()

        @asynccontextmanager
        async def fake_session_factory():
            yield object()

        fake_conflict_module = types.ModuleType("timeline_service.utils.conflict_detector")
        fake_conflict_module.ConflictDetector = FakeConflictDetector
        fake_conflict_module.DetectedConflict = object

        fake_task_repo_module = types.ModuleType("timeline_service.repository.task_repo")
        fake_task_repo_module.TaskRepository = FakeTaskRepository

        fake_db_module = types.ModuleType("common.database")
        fake_db_module.async_session_factory = fake_session_factory

        with patch.dict(sys.modules, {
            "timeline_service.utils.conflict_detector": fake_conflict_module,
            "timeline_service.repository.task_repo": fake_task_repo_module,
            "common.database": fake_db_module,
        }):
            result = asyncio.run(
                conflict_check_node(
                    {
                        "user_id": 1,
                        "calendar_events": [],
                        "conflicts_found": [],
                        "tasks_created": [],
                        "tasks_updated": [
                            {"id": 9, "title": "Library", "new_time": "2026-08-06T07:00:00"}
                        ],
                    }
                )
            )

        self.assertEqual(calls["repo"], 1)
        self.assertEqual(result["conflict_count"], 1)
        self.assertEqual(result["conflicts_found"][0]["reason"], "overlap")


if __name__ == "__main__":
    unittest.main()
