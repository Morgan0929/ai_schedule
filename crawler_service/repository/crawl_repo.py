"""
爬虫数据访问层
"""
from sqlalchemy import select, func
from sqlalchemy.ext.asyncio import AsyncSession
from crawler_service.models import CrawlDataModel


class CrawlRepository:
    """爬虫数据 Repository"""

    def __init__(self, db: AsyncSession):
        self.db = db

    async def save(self, record: CrawlDataModel) -> CrawlDataModel:
        """保存爬取记录"""
        self.db.add(record)
        await self.db.flush()
        await self.db.refresh(record)
        return record

    async def find_by_id(self, record_id: int) -> CrawlDataModel | None:
        """按 ID 查询"""
        result = await self.db.execute(
            select(CrawlDataModel).where(CrawlDataModel.id == record_id)
        )
        return result.scalar_one_or_none()

    async def list_by_source(
        self, source: str = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[CrawlDataModel], int]:
        """按数据源分页查询"""
        query = select(CrawlDataModel)

        if source:
            query = query.where(CrawlDataModel.source == source)

        # 总数
        count_result = await self.db.execute(
            select(func.count()).select_from(query.subquery())
        )
        total = count_result.scalar() or 0

        # 分页
        query = (
            query
            .order_by(CrawlDataModel.crawled_at.desc())
            .offset((page - 1) * page_size)
            .limit(page_size)
        )
        result = await self.db.execute(query)
        records = list(result.scalars().all())

        return records, total

    async def get_latest_by_source(self, source: str) -> CrawlDataModel | None:
        """获取指定数据源的最新一条记录"""
        result = await self.db.execute(
            select(CrawlDataModel)
            .where(CrawlDataModel.source == source, CrawlDataModel.status == "SUCCESS")
            .order_by(CrawlDataModel.crawled_at.desc())
            .limit(1)
        )
        return result.scalar_one_or_none()

    async def delete_old_records(self, source: str, keep_count: int = 100):
        """清理旧数据，保留最近 N 条"""
        subquery = (
            select(CrawlDataModel.id)
            .where(CrawlDataModel.source == source)
            .order_by(CrawlDataModel.crawled_at.desc())
            .limit(keep_count)
            .subquery()
        )
        await self.db.execute(
            select(CrawlDataModel)
            .where(CrawlDataModel.source == source)
            .where(CrawlDataModel.id.not_in(select(subquery.c.id)))
        )
