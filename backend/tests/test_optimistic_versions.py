"""Independent transactions must not both update the same record version."""

import asyncio
import sys
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from sqlalchemy import text
from sqlalchemy.ext.asyncio import async_sessionmaker, create_async_engine

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from database_support import create_test_database, close_test_database
from common.database import Base, ensure_schedule_versions
from common.exceptions import ConflictException
from timeline_service.models.task_model import TaskModel
from timeline_service.models.schedule_model import ScheduleModel, ScheduleAttachmentModel
from timeline_service.repository.task_repo import TaskRepository
from timeline_service.repository.schedule_repo import ScheduleRepository


class OptimisticVersionTests(unittest.IsolatedAsyncioTestCase):
    async def asyncSetUp(self):
        self.temp = tempfile.TemporaryDirectory()
        self.addCleanup(self.temp.cleanup)
        path = (Path(self.temp.name) / "test.db").as_posix()
        self.engine, self.database_cleanup = await create_test_database(path)
        self.factory = async_sessionmaker(self.engine, expire_on_commit=False)

    async def asyncTearDown(self):
        await close_test_database(self.engine, self.database_cleanup)

    async def create_tables(self):
        async with self.engine.begin() as conn:
            await conn.run_sync(lambda connection: Base.metadata.create_all(connection, tables=[
                TaskModel.__table__, ScheduleModel.__table__, ScheduleAttachmentModel.__table__,
            ]))

    async def seed(self, model):
        async with self.factory() as db:
            record = (TaskModel(user_id=7, title="Meeting", start_time=datetime(2026, 10, 8, 15),
                                end_time=datetime(2026, 10, 8, 16)) if model is TaskModel else
                      ScheduleModel(user_id=7, course_name="Course", week_day=4, semester="2026年秋季"))
            db.add(record)
            await db.commit()
            return record.id

    async def test_two_independent_writers_only_one_can_update_version_one(self):
        await self.create_tables()
        for model, repo_type in ((TaskModel, TaskRepository), (ScheduleModel, ScheduleRepository)):
            record_id = await self.seed(model)
            ready = asyncio.Event()

            async def writer(location):
                async with self.factory() as db:
                    await ready.wait()
                    result = await repo_type(db).update_if_version(record_id, 7, 1, {"location": location})
                    await db.commit()
                    return result is not None

            first = asyncio.create_task(writer("A"))
            second = asyncio.create_task(writer("B"))
            ready.set()
            results = await asyncio.gather(first, second)
            self.assertEqual(sorted(results), [False, True])
            async with self.factory() as db:
                record = await db.get(model, record_id)
                self.assertEqual(record.version, 2)
                self.assertEqual(record.location, "A" if results[0] else "B")

    async def test_stale_orm_metadata_write_cannot_overwrite_newer_task(self):
        await self.create_tables()
        record_id = await self.seed(TaskModel)
        async with self.factory() as first:
            stale = await first.get(TaskModel, record_id)
            async with self.factory() as second:
                await TaskRepository(second).update_if_version(record_id, 7, 1, {"location": "New"})
                await second.commit()
            stale.extra_data = {"attachments": []}
            with self.assertRaises(ConflictException):
                await TaskRepository(first).update(stale)
            await first.rollback()
        async with self.factory() as db:
            current = await db.get(TaskModel, record_id)
            self.assertEqual(current.location, "New")
            self.assertEqual(current.version, 2)

    async def test_database_predicate_also_checks_user_ownership(self):
        await self.create_tables()
        for model, repo_type in ((TaskModel, TaskRepository), (ScheduleModel, ScheduleRepository)):
            record_id = await self.seed(model)
            async with self.factory() as db:
                result = await repo_type(db).update_if_version(record_id, 8, 1, {"location": "Wrong user"})
                self.assertIsNone(result)
                await db.commit()
                current = await db.get(model, record_id)
                self.assertEqual(current.version, 1)
                self.assertIsNone(current.location)

    async def test_legacy_database_migration_preserves_rows_and_is_repeatable(self):
        async with self.engine.begin() as conn:
            for table in ("task", "schedule"):
                await conn.execute(text(f"CREATE TABLE {table} (id INTEGER PRIMARY KEY, title TEXT)"))
                await conn.execute(text(f"INSERT INTO {table} (id, title) VALUES (1, 'existing')"))
            await ensure_schedule_versions(conn)
            await ensure_schedule_versions(conn)
            for table in ("task", "schedule"):
                row = (await conn.execute(text(f"SELECT title, version FROM {table} WHERE id=1"))).one()
                self.assertEqual(tuple(row), ("existing", 1))
                await conn.execute(text(f"INSERT INTO {table} (id, title) VALUES (2, 'new')"))
                version = (await conn.execute(text(f"SELECT version FROM {table} WHERE id=2"))).scalar_one()
                self.assertEqual(version, 1)


if __name__ == "__main__":
    unittest.main()
