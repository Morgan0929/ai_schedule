"""HTTP authorization regressions using two users and an isolated database."""

import sys
import tempfile
import unittest
from datetime import datetime, timedelta, timezone
from pathlib import Path
from unittest.mock import AsyncMock, patch

import httpx
from jose import jwt
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from common.config import settings
from common.database import Base, get_db
from common.exceptions import ServiceUnavailableException
from common.schemas.agent import AgentChatResponse
from common.schemas.user import UserDTO
from common.utils.auth_session import store_login_session
from common.utils.jwt import create_access_token
from app_service import main as users
from agent_service import main as agent
from crawler_service import main as crawler
from timeline_service import main as timeline
from timeline_service.models.task_model import TaskModel
from timeline_service.models.schedule_model import ScheduleModel, ScheduleAttachmentModel


class FakeRedis:
    def __init__(self):
        self.values = {}

    async def get(self, key):
        return self.values.get(key)

    async def setex(self, key, seconds, value):
        self.values[key] = value

    async def delete(self, key):
        return int(self.values.pop(key, None) is not None)


class UserAuthorizationTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.redis = FakeRedis()
        self.redis_patch = patch("common.redis_client.get_redis", AsyncMock(return_value=self.redis))
        self.redis_patch.start()
        self.addCleanup(self.redis_patch.stop)
        self.engine = create_async_engine("sqlite+aiosqlite:///:memory:")
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)
        async with self.engine.begin() as connection:
            await connection.run_sync(lambda conn: Base.metadata.create_all(
                conn, tables=[TaskModel.__table__, ScheduleModel.__table__, ScheduleAttachmentModel.__table__],
            ))

        async def test_db():
            async with self.factory() as db:
                try:
                    yield db
                    await db.commit()
                except Exception:
                    await db.rollback()
                    raise

        self.clients = {}
        self.overrides = {}
        for module in (timeline, agent, crawler, users):
            self.overrides[module] = dict(module.app.dependency_overrides)
            module.app.dependency_overrides[get_db] = test_db
            self.clients[module] = httpx.AsyncClient(
                transport=httpx.ASGITransport(app=module.app), base_url="http://test",
            )
        self.headers = {}
        for user_id in (1, 2):
            await store_login_session(f"login-{user_id}", UserDTO(id=user_id, username=f"user-{user_id}"))
            self.headers[user_id] = {"Authorization": "Bearer " + create_access_token(
                user_id, f"user-{user_id}", "USER", f"login-{user_id}",
            )}
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        backend = Path(self.temp.name)
        self.media_patches = [
            patch.object(timeline, "UPLOAD_DIR", backend / "uploads"),
            patch("timeline_service.services.task_service.__file__", str(backend / "timeline_service/services/task_service.py")),
            patch("timeline_service.services.schedule_service.__file__", str(backend / "timeline_service/services/schedule_service.py")),
        ]
        for item in self.media_patches:
            item.start()
            self.addCleanup(item.stop)

    async def asyncTearDown(self):
        for module, client in self.clients.items():
            await client.aclose()
            module.app.dependency_overrides.clear()
            module.app.dependency_overrides.update(self.overrides[module])
        await self.engine.dispose()

    async def create_resource(self, kind, user_id=2):
        body = ({"title": "Private meeting", "start_time": "2026-10-08T15:00:00",
                 "end_time": "2026-10-08T16:00:00"} if kind == "tasks" else
                {"course_name": "Private course", "week_day": 4})
        response = await self.clients[timeline].post(
            f"/api/v1/{kind}", json=body, headers=self.headers[user_id],
        )
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json()["data"]["user_id"], user_id)
        return response.json()["data"]["id"]

    async def test_all_private_routes_require_authentication(self):
        for module in (timeline, agent, crawler):
            for route in module.app.routes:
                path = getattr(route, "path", "")
                private = (path.startswith(("/api/v1/tasks", "/api/v1/schedules", "/media/"))
                           if module is timeline else
                           path.startswith(("/api/v1/agent/chat", "/api/v1/agent/history", "/api/v1/todos"))
                           if module is agent else path.startswith("/api/v1/crawl/schedule/"))
                if not private:
                    continue
                path = path.replace("{task_id}", "1").replace("{schedule_id}", "1").replace("{image_id}", "1")
                path = path.replace("{todo_id}", "1").replace("{kind}", "task").replace("{filename}", "task-1-0123456789abcdef.png")
                for method in route.methods:
                    with self.subTest(path=path, method=method):
                        response = await self.clients[module].request(method, path, json={})
                        self.assertEqual(response.status_code, 401, response.text)

    async def test_owner_can_create_read_update_and_delete(self):
        for kind in ("tasks", "schedules"):
            record_id = await self.create_resource(kind)
            path = f"/api/v1/{kind}/{record_id}"
            response = await self.clients[timeline].get(path, headers=self.headers[2])
            self.assertEqual(response.status_code, 200, response.text)
            body = {"title" if kind == "tasks" else "course_name": "Updated"}
            response = await self.clients[timeline].put(path, json=body, headers=self.headers[2])
            self.assertEqual(response.status_code, 200, response.text)
            response = await self.clients[timeline].delete(path, headers=self.headers[2])
            self.assertEqual(response.status_code, 200, response.text)

    async def test_other_users_cannot_read_update_or_delete_records(self):
        for kind in ("tasks", "schedules"):
            record_id = await self.create_resource(kind)
            path = f"/api/v1/{kind}/{record_id}"
            for method in ("GET", "PUT", "DELETE"):
                with self.subTest(kind=kind, method=method):
                    response = await self.clients[timeline].request(method, path, json={}, headers=self.headers[1])
                    self.assertEqual(response.status_code, 404, response.text)
            response = await self.clients[timeline].get(path, headers=self.headers[2])
            self.assertEqual(response.status_code, 200)

    async def test_list_is_scoped_and_forged_query_ids_are_rejected(self):
        for kind in ("tasks", "schedules"):
            await self.create_resource(kind)
            response = await self.clients[timeline].get(f"/api/v1/{kind}", headers=self.headers[1])
            self.assertEqual(response.json()["data"]["items"], [])
            for query in ("user_id=2", "user_id=1&user_id=2", "user_id=invalid"):
                response = await self.clients[timeline].get(f"/api/v1/{kind}?{query}", headers=self.headers[1])
                self.assertEqual(response.status_code, 403, response.text)
            response = await self.clients[timeline].get(f"/api/v1/{kind}?user_id=2", headers=self.headers[2])
            self.assertEqual(response.status_code, 200)

    async def test_logout_revokes_token_for_all_private_entry_points(self):
        response = await self.clients[users].post("/api/v1/auth/logout", headers=self.headers[1])
        self.assertEqual(response.status_code, 200)
        for module, path in ((timeline, "/api/v1/tasks"), (agent, "/api/v1/todos"),
                             (crawler, "/api/v1/crawl/schedule/status"), (users, "/api/v1/users/me")):
            response = await self.clients[module].get(path, headers=self.headers[1])
            self.assertEqual(response.status_code, 401, response.text)

    async def test_expired_invalid_and_mismatched_tokens_are_rejected(self):
        expired = jwt.encode({"sub": "1", "sid": "login-1", "exp": datetime.now(timezone.utc) - timedelta(seconds=1)},
                             settings.JWT_SECRET_KEY, algorithm=settings.JWT_ALGORITHM)
        mismatched = create_access_token(2, "user-2", "USER", "login-1")
        for token in ("invalid", expired, mismatched):
            response = await self.clients[timeline].get("/api/v1/tasks", headers={"Authorization": "Bearer " + token})
            self.assertEqual(response.status_code, 401, response.text)

    async def test_redis_failure_does_not_fall_back_to_trusting_jwt(self):
        with patch("common.utils.authentication.get_login_session", AsyncMock(side_effect=ServiceUnavailableException("Redis"))):
            response = await self.clients[timeline].get("/api/v1/tasks", headers=self.headers[1])
        self.assertEqual(response.status_code, 503)

    async def test_agent_cannot_select_another_user_or_conversation(self):
        for path in ("/api/v1/agent/chat", "/api/v1/agent/chat/stream"):
            for body in ({"message": "delete meeting", "user_id": 2},
                         {"message": "continue", "session_id": "u2:conversation"}):
                with patch.object(agent.AgentService, "chat", AsyncMock()) as chat:
                    response = await self.clients[agent].post(path, json=body, headers=self.headers[1])
                self.assertEqual(response.status_code, 403, response.text)
                chat.assert_not_called()
        response = await self.clients[agent].get("/api/v1/agent/history?user_id=2", headers=self.headers[1])
        self.assertEqual(response.status_code, 403)

    async def test_agent_uses_authenticated_identity_and_scoped_session(self):
        async def chat(request):
            self.assertEqual(request.user_id, 1)
            self.assertEqual(request.session_id, "u1:conversation")
            return AgentChatResponse(reply="ok", session_id=request.session_id)

        with patch.object(agent.AgentService, "chat", chat):
            response = await self.clients[agent].post("/api/v1/agent/chat", json={
                "message": "hello", "session_id": "conversation",
            }, headers=self.headers[1])
        self.assertEqual(response.status_code, 200, response.text)

    async def test_imports_reject_forged_body_identity_before_writing(self):
        for suffix, body in (("from-url", {"url": "https://example.edu/schedule"}),
                             ("from-html", {"html": "<html>private timetable</html>"}),
                             ("refresh", {"courses": []})):
            response = await self.clients[crawler].post(f"/api/v1/crawl/schedule/{suffix}",
                json={**body, "user_id": 2}, headers=self.headers[1])
            self.assertEqual(response.status_code, 403, response.text)

    async def test_import_uses_authenticated_identity_without_body_user_id(self):
        with patch("crawler_service.services.schedule_import_service.ScheduleImportService.import_from_html",
                   AsyncMock(return_value={"status": "IMPORTED"})) as importer:
            response = await self.clients[crawler].post("/api/v1/crawl/schedule/from-html",
                json={"html": "<html>private timetable</html>"}, headers=self.headers[1])
        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(importer.await_args.kwargs["user_id"], 1)

    async def test_private_images_cannot_be_read_or_uploaded_by_another_user(self):
        for kind in ("tasks", "schedules"):
            record_id = await self.create_resource(kind)
            path = f"/api/v1/{kind}/{record_id}/images"
            response = await self.clients[timeline].post(path, files={"file": ("test.png", b"private-image", "image/png")},
                                                        headers=self.headers[1])
            self.assertEqual(response.status_code, 404, response.text)
            response = await self.clients[timeline].post(path, files={"file": ("test.png", b"private-image", "image/png")},
                                                        headers=self.headers[2])
            self.assertEqual(response.status_code, 200, response.text)
            url = response.json()["data"]["file_url"]
            for headers, status in (({}, 401), (self.headers[1], 404), (self.headers[2], 200)):
                response = await self.clients[timeline].get(url, headers=headers)
                self.assertEqual(response.status_code, status, response.text)
            self.assertEqual(response.content, b"private-image")
            self.assertEqual(response.headers["cache-control"], "private, no-store")


if __name__ == "__main__":
    unittest.main()
