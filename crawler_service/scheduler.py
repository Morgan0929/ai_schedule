"""
APScheduler 定时任务调度
"""
from apscheduler.schedulers.asyncio import AsyncIOScheduler

scheduler = AsyncIOScheduler()


def start_scheduler():
    """启动定时任务"""
    # TODO: 添加定时爬取任务
    # scheduler.add_job(crawl_weather, 'cron', hour=8, minute=0)
    scheduler.start()
    print("[Scheduler] 定时任务已启动")


def stop_scheduler():
    """停止定时任务"""
    scheduler.shutdown()
    print("[Scheduler] 定时任务已停止")
