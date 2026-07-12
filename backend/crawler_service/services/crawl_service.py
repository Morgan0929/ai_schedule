"""
爬虫业务逻辑层
"""
import logging
from sqlalchemy.ext.asyncio import AsyncSession
from crawler_service.models.crawl_model import CrawlDataModel, CrawlDataDTO, CrawlTriggerRequest
from crawler_service.repository.crawl_repo import CrawlRepository
from crawler_service.spiders.registry import get_spider, list_spiders

logger = logging.getLogger(__name__)


class CrawlService:
    """爬虫服务"""

    def __init__(self, db: AsyncSession):
        self.repo = CrawlRepository(db)

    async def trigger_crawl(self, request: CrawlTriggerRequest) -> CrawlDataModel:
        """
        触发一次爬取

        1. 查找匹配的爬虫
        2. 执行爬取
        3. 存储结果
        """
        spider = get_spider(request.source)
        if not spider:
            raise ValueError(f"未知数据源: {request.source}，可用: {[s['name'] for s in list_spiders()]}")

        # 执行爬取
        logger.info(f"开始爬取: {request.source} params={request.params}")
        result = await spider.crawl(**request.params)

        # 存储
        record = CrawlDataModel(
            user_id=request.user_id,
            source=result.source,
            source_url=None,
            raw_data={
                "title": result.title,
                "data": result.data,
                "items": result.items,
            },
            extracted_info={
                "item_count": len(result.items),
                "success": result.success,
            },
            status="SUCCESS" if result.success else "FAILED",
            error_message=result.error if not result.success else None,
        )
        record = await self.repo.save(record)
        logger.info(f"爬取完成: {request.source} success={result.success} items={len(result.items)}")

        return record

    async def get_record(self, record_id: int) -> CrawlDataDTO:
        """获取单条爬取记录"""
        record = await self.repo.find_by_id(record_id)
        if not record:
            raise ValueError(f"记录不存在: {record_id}")
        return CrawlDataDTO.model_validate(record)

    async def list_records(
        self, source: str = None, page: int = 1, page_size: int = 20
    ) -> tuple[list[CrawlDataDTO], int]:
        """分页查询爬取记录"""
        records, total = await self.repo.list_by_source(source, page, page_size)
        return [CrawlDataDTO.model_validate(r) for r in records], total

    async def get_latest(self, source: str) -> CrawlDataDTO | None:
        """获取指定数据源最新数据"""
        record = await self.repo.get_latest_by_source(source)
        if not record:
            return None
        return CrawlDataDTO.model_validate(record)

    @staticmethod
    def get_available_spiders() -> list[dict[str, str]]:
        """获取所有可用爬虫列表"""
        return list_spiders()
