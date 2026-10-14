"""Crash recovery and HTTP replay tests against isolated, independent DB connections."""

import asyncio
import sys
import tempfile
import unittest
from datetime import datetime, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from fastapi import Request
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database_support import create_test_database, close_test_database
from common.database import Base, get_db
from common.exceptions import BadRequestException
from common.schemas.task import TaskCreateDTO
from common.utils.authentication import get_authenticated_user_id
from timeline_service import main as timeline
from timeline_service.models.request_record import RequestRecord
from timeline_service.models.task_model import TaskModel
from timeline_service.repository.task_repo import TaskRepository
from timeline_service.services.task_service import TaskService
from timeline_service.services.task_creation import (
    CreationClaim, CreationOutcome, LeaseLost, TaskCreationService, get_task_creation_service,
)


class TaskIdempotencyTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = (Path(self.temp.name) / "requests.db").as_posix()
        self.engine, self.database_cleanup = await create_test_database(path)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        self.service = TaskCreationService(self.factory)
        async with self.engine.begin() as conn:
            await conn.run_sync(lambda connection: Base.metadata.create_all(connection, tables=[
                TaskModel.__table__, RequestRecord.__table__,
            ]))
        self.dto = TaskCreateDTO(title="Meeting", start_time=datetime(2026, 10, 15, 15),
                                 end_time=datetime(2026, 10, 15, 16), location="Library")
        self.original_overrides = dict(timeline.app.dependency_overrides)

        async def test_user(request: Request):
            return int(request.headers.get("X-Test-User", "7"))

        async def test_db():
            async with self.factory() as db, db.begin():
                yield db

        timeline.app.dependency_overrides[get_authenticated_user_id] = test_user
        timeline.app.dependency_overrides[get_task_creation_service] = lambda: self.service
        timeline.app.dependency_overrides[get_db] = test_db
        self.client = httpx.AsyncClient(transport=httpx.ASGITransport(app=timeline.app), base_url="http://test")

    async def asyncTearDown(self):
        await self.client.aclose()
        timeline.app.dependency_overrides.clear()
        timeline.app.dependency_overrides.update(self.original_overrides)
        await close_test_database(self.engine, self.database_cleanup)

    async def post(self, key="request-1", body=None, user=7):
        return await self.client.post("/api/v1/tasks", json=body or self.dto.model_dump(mode="json"),
                                      headers={"Idempotency-Key": key, "X-Test-User": str(user)})

    async def count_tasks(self):
        async with self.factory() as db:
            return (await db.execute(select(func.count()).select_from(TaskModel))).scalar_one()

    async def expire(self, key="request-1"):
        async with self.factory() as db, db.begin():
            await db.execute(update(RequestRecord).where(RequestRecord.request_id == key)
                             .values(lease_until=datetime(2000, 1, 1, tzinfo=timezone.utc)))

    async def test_replay_returns_original_result_once(self):
        first = await self.post()
        second = await self.post()
        self.assertEqual(first.status_code, 201, first.text)
        self.assertEqual(second.status_code, 201, second.text)
        self.assertEqual(first.json(), second.json())
        self.assertEqual(second.headers["Idempotency-Replayed"], "true")
        self.assertEqual(await self.count_tasks(), 1)

    async def test_same_key_with_different_payload_is_rejected(self):
        await self.post()
        response = await self.post(body={**self.dto.model_dump(mode="json"), "title": "Different"})
        self.assertEqual(response.status_code, 409, response.text)
        self.assertEqual(await self.count_tasks(), 1)

    async def test_duplicate_during_processing_returns_status_without_executing(self):
        claim = await self.service.claim(7, "request-1", self.dto)
        with patch.object(TaskService, "create_task", AsyncMock()) as create:
            response = await self.post()
        self.assertEqual(response.status_code, 202, response.text)
        self.assertEqual(response.headers["Retry-After"], "1")
        create.assert_not_called()
        status = await self.client.get(response.headers["Location"])
        self.assertEqual(status.json()["data"]["status"], "PROCESSING")
        await self.service.execute(claim)
        status = await self.client.get(response.headers["Location"])
        self.assertEqual(status.json()["data"]["status"], "SUCCEEDED")

    async def test_concurrent_http_requests_do_not_duplicate_creation(self):
        responses = await asyncio.gather(self.post(), self.post(), self.post())
        self.assertTrue(all(response.status_code in (201, 202) for response in responses),
                        [response.text for response in responses])
        replay = await self.post()
        self.assertEqual(replay.status_code, 201, replay.text)
        self.assertEqual(await self.count_tasks(), 1)

    async def test_users_are_isolated_even_with_the_same_key(self):
        first, second = await self.post(user=7), await self.post(user=8)
        self.assertEqual(first.status_code, 201)
        self.assertEqual(second.status_code, 201)
        self.assertNotEqual(first.json()["data"]["id"], second.json()["data"]["id"])
        response = await self.client.get("/api/v1/task-requests/request-1", headers={"X-Test-User": "9"})
        self.assertEqual(response.status_code, 404)

    async def test_deleted_task_is_not_resurrected_and_history_survives(self):
        created = await self.post()
        task_id = created.json()["data"]["id"]
        async with self.factory() as db, db.begin():
            task = await db.get(TaskModel, task_id)
            await db.delete(task)
        response = await self.post()
        self.assertEqual(response.status_code, 410, response.text)
        self.assertEqual(await self.count_tasks(), 0)
        # Even SQLite reusing a deleted primary key must not confuse request history.
        new = await self.post(key="request-new")
        self.assertEqual(new.status_code, 201, new.text)
        response = await self.post()
        self.assertEqual(response.status_code, 410, response.text)
        self.assertEqual(await self.count_tasks(), 1)

    async def test_replay_uses_snapshot_not_latest_edited_fields(self):
        first = await self.post()
        task_id = first.json()["data"]["id"]
        async with self.factory() as db, db.begin():
            await TaskRepository(db).update_if_version(task_id, 7, 1, {"location": "New room"})
        replay = await self.post()
        self.assertEqual(replay.json(), first.json())
        async with self.factory() as db:
            self.assertEqual((await db.get(TaskModel, task_id)).location, "New room")

    async def test_expired_claim_can_be_taken_over_but_old_worker_cannot_write(self):
        old = await self.service.claim(7, "request-1", self.dto)
        await self.expire()
        status = await self.client.get("/api/v1/task-requests/request-1")
        self.assertTrue(status.json()["data"]["can_retry"])
        self.assertFalse(await self.service.renew(old))
        new = await self.service.claim(7, "request-1", self.dto)
        self.assertIsInstance(new, CreationClaim)
        self.assertNotEqual(new.token, old.token)
        with self.assertRaises(LeaseLost):
            await self.service.execute(old)
        self.assertEqual(await self.count_tasks(), 0)
        await self.service.execute(new)
        with self.assertRaises(LeaseLost):
            await self.service.execute(old)
        self.assertEqual(await self.count_tasks(), 1)

    async def test_competing_takeovers_only_one_gets_execution_rights(self):
        await self.service.claim(7, "request-1", self.dto)
        await self.expire()
        results = await asyncio.gather(*(self.service.claim(7, "request-1", self.dto) for _ in range(3)))
        claims = [result for result in results if isinstance(result, CreationClaim)]
        self.assertEqual(len(claims), 1)
        await self.service.execute(claims[0])
        self.assertEqual(await self.count_tasks(), 1)

    async def test_failure_after_insert_rolls_back_task_and_allows_safe_retry(self):
        original = TaskService.create_task

        async def fail_after_insert(service, *args, **kwargs):
            await original(service, *args, **kwargs)
            raise RuntimeError("simulated worker failure after task insert")

        with patch.object(TaskService, "create_task", fail_after_insert):
            with self.assertRaises(RuntimeError):
                await self.service.create(7, "request-1", self.dto)
        self.assertEqual(await self.count_tasks(), 0)
        self.assertEqual((await self.service.lookup(7, "request-1")).status, "FAILED")
        recovered = await self.service.create(7, "request-1", self.dto)
        self.assertEqual(recovered.status, "SUCCEEDED")
        self.assertEqual(await self.count_tasks(), 1)

    async def test_final_fence_failure_rolls_back_even_already_flushed_task(self):
        original = TaskService.create_task

        async def lose_lease(service, *args, **kwargs):
            result = await original(service, *args, **kwargs)
            await service.repo.db.execute(update(RequestRecord).values(lease_until=datetime(2000, 1, 1, tzinfo=timezone.utc)))
            return result

        claim = await self.service.claim(7, "request-1", self.dto)
        with patch.object(TaskService, "create_task", lose_lease):
            with self.assertRaises(LeaseLost):
                await self.service.execute(claim)
        self.assertEqual(await self.count_tasks(), 0)
        self.assertEqual((await self.service.lookup(7, "request-1")).status, "PROCESSING")

    async def test_cancelled_execution_rolls_back_and_waits_for_expiry_before_recovery(self):
        original = TaskService.create_task

        async def cancelled(service, *args, **kwargs):
            await original(service, *args, **kwargs)
            raise asyncio.CancelledError()

        claim = await self.service.claim(7, "request-1", self.dto)
        with patch.object(TaskService, "create_task", cancelled):
            with self.assertRaises(asyncio.CancelledError):
                await self.service.execute(claim)
        self.assertEqual(await self.count_tasks(), 0)
        still_running = await self.service.claim(7, "request-1", self.dto)
        self.assertIsInstance(still_running, CreationOutcome)
        await self.expire()
        recovered = await self.service.create(7, "request-1", self.dto)
        self.assertEqual(recovered.status, "SUCCEEDED")
        self.assertEqual(await self.count_tasks(), 1)

    async def test_stale_failure_cannot_overwrite_new_owners_success(self):
        old = await self.service.claim(7, "request-1", self.dto)
        await self.expire()
        new = await self.service.claim(7, "request-1", self.dto)
        await self.service.execute(new)
        await self.service._fail(old, 503, "stale failure")
        self.assertEqual((await self.service.lookup(7, "request-1")).status, "SUCCEEDED")

    async def test_renewal_is_owner_checked_and_background_heartbeat_stops(self):
        self.service.lease_seconds = 3
        claim = await self.service.claim(7, "request-1", self.dto)
        self.assertTrue(await self.service.renew(claim))
        wrong = CreationClaim(7, "request-1", "wrong-owner")
        self.assertFalse(await self.service.renew(wrong))
        renewed = asyncio.Event()

        async def renew(claim):
            renewed.set()
            return False

        with patch.object(self.service, "renew", renew):
            async with self.service.keep_alive(claim):
                await asyncio.wait_for(renewed.wait(), timeout=2)

    async def test_business_failure_is_replayed_without_a_second_execution(self):
        invalid = self.dto.model_copy(update={"end_time": self.dto.start_time})
        with self.assertRaises(BadRequestException):
            await self.service.create(7, "request-1", invalid)
        with patch.object(TaskService, "create_task", AsyncMock()) as create:
            outcome = await self.service.create(7, "request-1", invalid)
        self.assertEqual(outcome.status, "FAILED")
        self.assertEqual(outcome.response_code, 400)
        create.assert_not_called()
        self.assertEqual(await self.count_tasks(), 0)

    async def test_missing_invalid_keys_and_unknown_status(self):
        response = await self.client.post("/api/v1/tasks", json=self.dto.model_dump(mode="json"))
        self.assertEqual(response.status_code, 422)
        response = await self.post(key="not valid")
        self.assertEqual(response.status_code, 400)
        response = await self.client.get("/api/v1/task-requests/unknown")
        self.assertEqual(response.status_code, 404)

    async def test_agent_confirmation_can_replay_after_redis_cleanup(self):
        from agent_service.graph import pending_task

        pending = {"title": "Meeting", "ref_id": "pending-test", "start_time": "2026-10-15T15:00:00",
                   "end_time": "2026-10-15T16:00:00"}
        with patch("common.database.async_session_factory", self.factory), \
             patch.object(pending_task, "get_pending", AsyncMock(side_effect=[pending, None])), \
             patch.object(pending_task, "delete_pending", AsyncMock()) as delete:
            first = await pending_task.commit_pending("pending-test", 7)
            second = await pending_task.commit_pending("pending-test", 7)
        self.assertEqual(first["status"], "created", first)
        self.assertEqual(second["status"], "already_exists", second)
        self.assertEqual(first["id"], second["id"])
        self.assertEqual(delete.await_count, 2)
        self.assertEqual(await self.count_tasks(), 1)

    async def test_agent_failure_does_not_remove_pending_intent(self):
        from agent_service.graph import pending_task

        pending = {"title": "Meeting", "ref_id": "pending-test", "start_time": "2026-10-15T15:00:00",
                   "end_time": "2026-10-15T16:00:00"}
        with patch("common.database.async_session_factory", self.factory), \
             patch.object(TaskCreationService, "create", AsyncMock(side_effect=RuntimeError("crash"))), \
             patch.object(pending_task, "delete_pending", AsyncMock()) as delete:
            result = await pending_task._commit_pending_payload(pending, "pending-test", 7)
        self.assertEqual(result["status"], "commit_failed")
        delete.assert_not_called()


if __name__ == "__main__":
    unittest.main()
