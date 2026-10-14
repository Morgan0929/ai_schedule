"""Durable creation, leased ownership, and transactional fencing."""

import asyncio
import hashlib
import json
import uuid
from contextlib import asynccontextmanager
from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import func, or_, and_, select, update

from common.database import async_session_factory
from common.exceptions import AppException, BadRequestException, ConflictException, NotFoundException
from common.schemas.task import TaskCreateDTO
from timeline_service.models.request_record import RequestRecord
from timeline_service.models.task_model import TaskModel
from timeline_service.services.task_service import TaskService


OPERATION = "tasks.create"


class LeaseLost(ConflictException):
    def __init__(self):
        super().__init__("本次执行权已失效，请查询原请求结果")


@dataclass(frozen=True)
class CreationClaim:
    user_id: int
    request_id: str
    token: str


@dataclass
class CreationOutcome:
    status: str
    request_id: str
    result: dict | None = None
    replayed: bool = False
    response_code: int | None = None
    can_retry: bool = False


class TaskCreationService:
    def __init__(self, factory=async_session_factory, lease_seconds: int = 30):
        if lease_seconds < 3:
            raise ValueError("lease_seconds must be at least 3")
        self.factory = factory
        self.lease_seconds = lease_seconds

    @staticmethod
    def _identity(user_id, request_id):
        return (RequestRecord.user_id == user_id, RequestRecord.operation == OPERATION,
                RequestRecord.request_id == request_id)

    @staticmethod
    def _clock(db):
        return func.clock_timestamp() if db.bind.dialect.name == "postgresql" else func.current_timestamp()

    def _deadline(self, db):
        if db.bind.dialect.name == "postgresql":
            return self._clock(db) + timedelta(seconds=self.lease_seconds)
        return func.datetime("now", f"+{self.lease_seconds} seconds")

    @staticmethod
    def _payload(dto):
        payload = dto.model_dump(mode="json")
        digest = hashlib.sha256(json.dumps(payload, sort_keys=True, separators=(",", ":"),
                                            ensure_ascii=False).encode("utf-8")).hexdigest()
        return payload, digest

    @staticmethod
    def validate_key(request_id):
        if not isinstance(request_id, str) or not 1 <= len(request_id) <= 128 or any(
            not (char.isascii() and (char.isalnum() or char in "-_.:")) for char in request_id
        ):
            raise BadRequestException("请求标识须为 1 至 128 位字母 数字或 - _ . :")

    async def _read(self, db, user_id, request_id):
        return (await db.execute(select(RequestRecord).where(*self._identity(user_id, request_id)))).scalar_one_or_none()

    async def _outcome(self, db, record):
        if record.status == "SUCCEEDED":
            task = await db.get(TaskModel, record.task_id)
            if (not task or task.user_id != record.user_id
                    or (task.extra_data or {}).get("creation_request_id") != record.request_id):
                return CreationOutcome("DELETED", record.request_id, {"task_id": record.task_id}, True, 410)
            # Replay the original result, not a newly edited representation.
            return CreationOutcome("SUCCEEDED", record.request_id, record.result, True, 201)
        can_retry = bool(record.status == "FAILED" and record.response_code and record.response_code >= 500)
        if record.status == "PROCESSING":
            can_retry = bool((await db.execute(select(RequestRecord.lease_until <= self._clock(db))
                              .where(*self._identity(record.user_id, record.request_id)))).scalar_one())
        return CreationOutcome(record.status, record.request_id, record.result, True, record.response_code, can_retry)

    async def lookup(self, user_id: int, request_id: str):
        self.validate_key(request_id)
        async with self.factory() as db:
            record = await self._read(db, user_id, request_id)
            if not record:
                raise NotFoundException("创建请求")
            return await self._outcome(db, record)

    async def stored_payload(self, user_id: int, request_id: str):
        """Internal recovery for Agent confirmation after its Redis item expires."""
        async with self.factory() as db:
            record = await self._read(db, user_id, request_id)
            return record.request_payload if record else None

    async def claim(self, user_id: int, request_id: str, dto: TaskCreateDTO):
        self.validate_key(request_id)
        payload, digest = self._payload(dto)
        token = uuid.uuid4().hex
        async with self.factory() as db, db.begin():
            if db.bind.dialect.name == "postgresql":
                from sqlalchemy.dialects.postgresql import insert
            elif db.bind.dialect.name == "sqlite":
                from sqlalchemy.dialects.sqlite import insert
            else:
                raise RuntimeError("Idempotent creation requires PostgreSQL or SQLite")
            inserted = await db.execute(insert(RequestRecord).values(
                user_id=user_id, operation=OPERATION, request_id=request_id,
                request_hash=digest, request_payload=payload, status="PROCESSING",
                owner_token=token, lease_until=self._deadline(db),
            ).on_conflict_do_nothing(index_elements=["user_id", "operation", "request_id"])
              .returning(RequestRecord.owner_token))
            if inserted.scalar_one_or_none() is not None:
                return CreationClaim(user_id, request_id, token)
            record = await self._read(db, user_id, request_id)
            if record.request_hash != digest:
                raise ConflictException("请求标识已用于其他内容，请为新的创建操作使用新标识")
            if record.status == "SUCCEEDED":
                return await self._outcome(db, record)
            if record.status == "FAILED" and record.response_code and record.response_code < 500:
                return await self._outcome(db, record)
            takeover = await db.execute(update(RequestRecord).where(
                *self._identity(user_id, request_id), RequestRecord.request_hash == digest,
                or_(and_(RequestRecord.status == "PROCESSING", RequestRecord.lease_until <= self._clock(db)),
                    and_(RequestRecord.status == "FAILED", RequestRecord.response_code >= 500)),
            ).values(status="PROCESSING", owner_token=token, lease_until=self._deadline(db),
                     result=None, response_code=None)
              .returning(RequestRecord.owner_token).execution_options(synchronize_session=False))
            if takeover.scalar_one_or_none() is not None:
                return CreationClaim(user_id, request_id, token)
            return CreationOutcome("PROCESSING", request_id)

    async def renew(self, claim: CreationClaim) -> bool:
        async with self.factory() as db, db.begin():
            result = await db.execute(update(RequestRecord).where(
                *self._identity(claim.user_id, claim.request_id),
                RequestRecord.status == "PROCESSING", RequestRecord.owner_token == claim.token,
                RequestRecord.lease_until > self._clock(db),
            ).values(lease_until=self._deadline(db)).returning(RequestRecord.owner_token))
            return result.scalar_one_or_none() is not None

    @asynccontextmanager
    async def keep_alive(self, claim: CreationClaim):
        """For preparation outside a DB transaction; final writes still fence ownership."""
        async def heartbeat():
            while True:
                await asyncio.sleep(self.lease_seconds / 3)
                if not await self.renew(claim):
                    return

        task = asyncio.create_task(heartbeat())
        try:
            yield
        finally:
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)

    async def _fail(self, claim, code, message):
        async with self.factory() as db, db.begin():
            await db.execute(update(RequestRecord).where(
                *self._identity(claim.user_id, claim.request_id), RequestRecord.status == "PROCESSING",
                RequestRecord.owner_token == claim.token, RequestRecord.lease_until > self._clock(db),
            ).values(status="FAILED", response_code=code, result={"message": message}))

    async def execute(self, claim: CreationClaim):
        """Fence first, then create and mark success in exactly one transaction."""
        try:
            async with self.factory() as db, db.begin():
                fenced = await db.execute(update(RequestRecord).where(
                    *self._identity(claim.user_id, claim.request_id), RequestRecord.status == "PROCESSING",
                    RequestRecord.owner_token == claim.token, RequestRecord.lease_until > self._clock(db),
                ).values(lease_until=self._deadline(db)).returning(RequestRecord.request_payload)
                  .execution_options(synchronize_session=False))
                payload = fenced.scalar_one_or_none()
                if payload is None:
                    raise LeaseLost()
                # This row stays locked until transaction end. A takeover must
                # wait and then recheck its WHERE predicate against committed state.
                task = await TaskService(db).create_task(
                    TaskCreateDTO.model_validate(payload), claim.user_id, creation_request_id=claim.request_id,
                )
                snapshot = task.model_dump(mode="json")
                finished = await db.execute(update(RequestRecord).where(
                    *self._identity(claim.user_id, claim.request_id), RequestRecord.status == "PROCESSING",
                    RequestRecord.owner_token == claim.token, RequestRecord.lease_until > self._clock(db),
                ).values(status="SUCCEEDED", task_id=task.id, result=snapshot, response_code=201)
                  .returning(RequestRecord.task_id).execution_options(synchronize_session=False))
                if finished.scalar_one_or_none() is None:
                    raise LeaseLost()
            return CreationOutcome("SUCCEEDED", claim.request_id, snapshot, False, 201)
        except LeaseLost:
            raise
        except AppException as exc:
            await self._fail(claim, exc.code, exc.message)
            raise
        except Exception:
            await self._fail(claim, 503, "创建暂时失败，请使用原请求标识重试")
            raise
        # Cancellation/crashes leave PROCESSING, recoverable only after lease expiry.

    async def create(self, user_id, request_id, dto):
        claim = await self.claim(user_id, request_id, dto)
        if isinstance(claim, CreationOutcome):
            return claim
        try:
            return await self.execute(claim)
        except LeaseLost:
            return await self.lookup(user_id, request_id)


def get_task_creation_service():
    return TaskCreationService()
