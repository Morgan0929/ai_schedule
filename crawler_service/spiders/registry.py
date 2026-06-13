"""
爬虫注册表 — 名称到爬虫类的映射

添加新爬虫只需:
1. 创建 spider 类继承 BaseSpider
2. 在 SPIDER_REGISTRY 中注册
"""
from crawler_service.spiders.base import BaseSpider
from crawler_service.spiders.weather_spider import WeatherSpider
from crawler_service.spiders.news_spider import NewsSpider
from crawler_service.spiders.calendar_spider import CalendarSpider

# 所有已注册的爬虫
SPIDER_REGISTRY: dict[str, BaseSpider] = {
    "weather": WeatherSpider(),
    "news": NewsSpider(),
    "calendar": CalendarSpider(),
}


def get_spider(name: str) -> BaseSpider | None:
    """按名称获取爬虫实例"""
    return SPIDER_REGISTRY.get(name)


def list_spiders() -> list[dict[str, str]]:
    """列出所有已注册的爬虫"""
    return [spider.get_info() for spider in SPIDER_REGISTRY.values()]
