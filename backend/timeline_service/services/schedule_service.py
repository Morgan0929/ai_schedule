"""课表业务逻辑"""
from __future__ import annotations

import hashlib
import json
from datetime import date
from pathlib import Path
from typing import Iterable

from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession

from common.exceptions import BadRequestException, NotFoundException
from common.schemas.schedule import (
    ScheduleAttachmentDTO,
    ScheduleCreateDTO,
    ScheduleDTO,
    ScheduleUpdateDTO,
)
from timeline_service.models.schedule_model import ScheduleAttachmentModel, ScheduleModel, get_current_semester
from timeline_service.repository.schedule_repo import ScheduleRepository


ALLOWED_IMAGE_TYPES = {
    "image/jpeg": ".jpg",
    "image/png": ".png",
    "image/webp": ".webp",
    "image/gif": ".gif",
}
IMAGE_EXTENSIONS = {ext: content_type for content_type, ext in ALLOWED_IMAGE_TYPES.items()}
MAX_IMAGE_SIZE = 10 * 1024 * 1024


class ScheduleService:
    def __init__(self, db: AsyncSession):
        self.db = db
        self.repo = ScheduleRepository(db)

    async def list_schedules(self, user_id: int, semester: str | None, page: int, page_size: int) -> tuple[list[ScheduleDTO], int]:
        schedules, total = await self.repo.list_by_user(user_id, semester, page, page_size)
        return [await self._to_dto(schedule) for schedule in schedules], total

    async def list_by_date(self, user_id: int, target_date: date) -> list[ScheduleDTO]:
        schedules = await self.repo.find_by_date(user_id, target_date)
        return [await self._to_dto(schedule) for schedule in schedules]

    async def get_schedule(self, user_id: int, schedule_id: int) -> ScheduleDTO:
        schedule = await self.repo.find_by_id(schedule_id)
        if not schedule or schedule.user_id != user_id or not schedule.is_active:
            raise NotFoundException("课表记录", schedule_id)
        return await self._to_dto(schedule)

    async def create_schedule(self, user_id: int, dto: ScheduleCreateDTO) -> ScheduleDTO:
        self._validate_schedule_fields(dto)
        semester = dto.semester or get_current_semester()
        schedule = ScheduleModel(
            user_id=user_id,
            source=dto.source,
            course_name=dto.course_name,
            teacher=dto.teacher,
            location=dto.location,
            week_day=dto.week_day,
            start_week=dto.start_week,
            end_week=dto.end_week,
            start_time=dto.start_time,
            end_time=dto.end_time,
            start_section=dto.start_section,
            end_section=dto.end_section,
            semester=semester,
            raw_data=None if dto.raw_data is None else json.dumps(dto.raw_data, ensure_ascii=False),
            is_active=True,
        )
        await self.repo.create(schedule)
        await self.db.commit()
        return await self._to_dto(schedule)

    async def update_schedule(self, user_id: int, schedule_id: int, dto: ScheduleUpdateDTO) -> ScheduleDTO:
        schedule = await self.repo.find_by_id(schedule_id)
        if not schedule or schedule.user_id != user_id:
            raise NotFoundException("课表记录", schedule_id)

        self._validate_schedule_fields(dto, schedule)
        update_data = dto.model_dump(exclude_unset=True)
        for key, value in update_data.items():
            if key == "raw_data" and value is not None:
                value = json.dumps(value, ensure_ascii=False)
            if value is not None:
                setattr(schedule, key, value)

        await self.repo.update(schedule)
        await self.db.commit()
        return await self._to_dto(schedule)

    async def delete_schedule(self, user_id: int, schedule_id: int) -> bool:
        schedule = await self.repo.find_by_id(schedule_id)
        if not schedule or schedule.user_id != user_id:
            raise NotFoundException("课表记录", schedule_id)
        attachments = await self.repo.list_attachments(schedule.id, user_id)
        for attachment in attachments:
            try:
                Path(attachment.storage_path).unlink(missing_ok=True)
            except OSError:
                pass
        await self.repo.delete_attachments(schedule.id, user_id)
        await self.repo.delete(schedule)
        await self.db.commit()
        return True

    async def list_attachments(self, user_id: int, schedule_id: int) -> list[ScheduleAttachmentDTO]:
        await self._ensure_ownership(user_id, schedule_id)
        items = await self.repo.list_attachments(schedule_id, user_id)
        return [ScheduleAttachmentDTO.model_validate(item) for item in items]

    async def add_attachments(self, user_id: int, schedule_id: int, files: Iterable[UploadFile]) -> list[ScheduleAttachmentDTO]:
        schedule = await self._ensure_ownership(user_id, schedule_id)
        uploads = await self._store_files(user_id, schedule, files)
        attachments = [
            ScheduleAttachmentModel(
                schedule_id=schedule.id,
                user_id=user_id,
                file_name=item["file_name"],
                original_name=item["original_name"],
                content_type=item["content_type"],
                file_size=item["file_size"],
                storage_path=item["storage_path"],
                file_url=item["file_url"],
            )
            for item in uploads
        ]
        await self.repo.add_attachments(schedule.id, user_id, attachments)
        await self.db.commit()
        return [ScheduleAttachmentDTO.model_validate(item) for item in attachments]

    async def add_attachment(self, user_id: int, schedule_id: int, file: UploadFile) -> ScheduleAttachmentDTO:
        attachments = await self.add_attachments(user_id, schedule_id, [file])
        return attachments[0]

    async def delete_attachment(self, user_id: int, schedule_id: int, attachment_id: int) -> bool:
        await self._ensure_ownership(user_id, schedule_id)
        attachments = await self.repo.list_attachments(schedule_id, user_id)
        target = next((item for item in attachments if item.id == attachment_id), None)
        if not target:
            raise NotFoundException("课表附件", attachment_id)
        try:
            Path(target.storage_path).unlink(missing_ok=True)
        except OSError:
            pass
        await self.db.delete(target)
        await self.db.commit()
        return True

    async def _ensure_ownership(self, user_id: int, schedule_id: int) -> ScheduleModel:
        schedule = await self.repo.find_by_id(schedule_id)
        if not schedule or schedule.user_id != user_id:
            raise NotFoundException("课表记录", schedule_id)
        return schedule

    async def _to_dto(self, schedule: ScheduleModel) -> ScheduleDTO:
        attachments = await self.repo.list_attachments(schedule.id, schedule.user_id)
        return ScheduleDTO(
            id=schedule.id,
            user_id=schedule.user_id,
            source=schedule.source,
            course_name=schedule.course_name,
            teacher=schedule.teacher,
            location=schedule.location,
            week_day=schedule.week_day,
            start_week=schedule.start_week,
            end_week=schedule.end_week,
            start_time=schedule.start_time,
            end_time=schedule.end_time,
            start_section=schedule.start_section,
            end_section=schedule.end_section,
            semester=schedule.semester,
            raw_data=schedule.raw_data,
            is_active=schedule.is_active,
            created_at=schedule.created_at,
            updated_at=schedule.updated_at,
            attachments=[ScheduleAttachmentDTO.model_validate(item) for item in attachments],
        )

    async def _store_files(self, user_id: int, schedule: ScheduleModel, files: Iterable[UploadFile]) -> list[dict]:
        storage_dir = Path(__file__).resolve().parents[2] / "uploads" / "schedule"
        storage_dir.mkdir(parents=True, exist_ok=True)

        results: list[dict] = []
        for file in files:
            content_type = self._resolve_content_type(file)
            if content_type not in ALLOWED_IMAGE_TYPES:
                raise BadRequestException("仅支持 JPEG / PNG / WebP / GIF 图片")
            data = await file.read()
            if len(data) > MAX_IMAGE_SIZE:
                raise BadRequestException("图片大小不能超过 10MB")
            digest = hashlib.sha256(data).hexdigest()[:16]
            ext = ALLOWED_IMAGE_TYPES[content_type]
            safe_name = f"schedule-{schedule.id}-{digest}{ext}"
            path = storage_dir / safe_name
            path.write_bytes(data)
            results.append({
                "file_name": safe_name,
                "original_name": file.filename or safe_name,
                "content_type": content_type,
                "file_size": len(data),
                "storage_path": str(path),
                "file_url": f"/media/schedule/{safe_name}",
            })
        return results

    @staticmethod
    def _resolve_content_type(file: UploadFile) -> str:
        if file.content_type in ALLOWED_IMAGE_TYPES:
            return file.content_type
        ext = Path(file.filename or "").suffix.lower()
        return IMAGE_EXTENSIONS.get(ext, file.content_type or "")

    @staticmethod
    def _validate_schedule_fields(dto: ScheduleCreateDTO | ScheduleUpdateDTO, current: ScheduleModel | None = None) -> None:
        start_week = dto.start_week if dto.start_week is not None else getattr(current, "start_week", None)
        end_week = dto.end_week if dto.end_week is not None else getattr(current, "end_week", None)
        if start_week is not None and end_week is not None and end_week < start_week:
            raise BadRequestException("结束周不能早于开始周")

        start_time = dto.start_time if dto.start_time is not None else getattr(current, "start_time", None)
        end_time = dto.end_time if dto.end_time is not None else getattr(current, "end_time", None)
        if start_time is not None and end_time is not None and end_time <= start_time:
            raise BadRequestException("结束时间必须晚于开始时间")

        start_section = dto.start_section if dto.start_section is not None else getattr(current, "start_section", None)
        end_section = dto.end_section if dto.end_section is not None else getattr(current, "end_section", None)
        if start_section is not None and end_section is not None and end_section < start_section:
            raise BadRequestException("结束节次不能早于开始节次")
