"""
APScheduler 定时任务调度

定时自动采集数据，存入数据库供 Agent 使用
"""
import asyncio
import logging
from apscheduler.schedulers.asyncio import AsyncIOScheduler
from apscheduler.triggers.cron import CronTrigger

logger = logging.getLogger(__name__)

scheduler = AsyncIOScheduler()


# ============ 定时采集任务 ============

async def scheduled_weather_crawl():
    """每天早上 8:00 自动采集天气"""
    from common.database import async_session_factory
    from crawler_service.service.crawl_service import CrawlService
    from crawler_service.models import CrawlTriggerRequest

    async with async_session_factory() as db:
        service = CrawlService(db)
        try:
            result = await service.trigger_crawl(CrawlTriggerRequest(
                source="weather",
                params={"city": "Beijing", "days": 3},
            ))
            logger.info(f"[定时] 天气采集完成: {result.extracted_info}")
            await db.commit()
        except Exception as e:
            logger.error(f"[定时] 天气采集失败: {e}")
            await db.rollback()


async def scheduled_news_crawl():
    """每天早上 9:00 自动采集新闻"""
    from common.database import async_session_factory
    from crawler_service.service.crawl_service import CrawlService
    from crawler_service.models import CrawlTriggerRequest

    async with async_session_factory() as db:
        service = CrawlService(db)
        try:
            result = await service.trigger_crawl(CrawlTriggerRequest(
                source="news",
                params={"limit": 15},
            ))
            logger.info(f"[定时] 新闻采集完成: {result.extracted_info}")
            await db.commit()
        except Exception as e:
            logger.error(f"[定时] 新闻采集失败: {e}")
            await db.rollback()


async def scheduled_cleanup():
    """每周末凌晨 2:00 清理旧数据"""
    from common.database import async_session_factory
    from crawler_service.repository.crawl_repo import CrawlRepository

    async with async_session_factory() as db:
        repo = CrawlRepository(db)
        for source in ["weather", "news"]:
            try:
                await repo.delete_old_records(source, keep_count=100)
            except Exception as e:
                logger.warning(f"[定时] {source} 数据清理失败: {e}")
        await db.commit()
        logger.info("[定时] 数据清理完成")


# ============ 调度器管理 ============

def start_scheduler():
    """启动定时任务"""
    # 每天早上 8:00 采集天气
    scheduler.add_job(
        scheduled_weather_crawl,
        trigger=CronTrigger(hour=8, minute=0),
        id="weather_daily",
        name="每日天气采集",
        replace_existing=True,
    )
    # 每天早上 9:00 采集新闻
    scheduler.add_job(
        scheduled_news_crawl,
        trigger=CronTrigger(hour=9, minute=0),
        id="news_daily",
        name="每日新闻采集",
        replace_existing=True,
    )
    # 每周日凌晨 2:00 清理
    scheduler.add_job(
        scheduled_cleanup,
        trigger=CronTrigger(day_of_week="sun", hour=2, minute=0),
        id="weekly_cleanup",
        name="每周数据清理",
        replace_existing=True,
    )

    scheduler.start()
    logger.info("[Scheduler] 定时任务已启动 (天气 08:00 / 新闻 09:00 / 清理 周日 02:00)")


def stop_scheduler():
    """停止定时任务"""
    scheduler.shutdown(wait=False)
    logger.info("[Scheduler] 定时任务已停止")
