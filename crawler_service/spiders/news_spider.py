"""
新闻爬虫

数据源: 可配置（默认使用公开 API）
"""
import httpx
from datetime import datetime
from crawler_service.spiders.base import BaseSpider, SpiderResult


class NewsSpider(BaseSpider):
    """新闻摘要爬虫"""

    name = "news"
    description = "获取最新新闻摘要"
    version = "1.0.0"

    # 使用公开的 hackernews API 作为示例
    # 后续可替换为国内新闻源
    TOP_STORIES_URL = "https://hacker-news.firebaseio.com/v0/topstories.json"
    ITEM_URL = "https://hacker-news.firebaseio.com/v0/item/{}.json"

    async def crawl(self, **params) -> SpiderResult:
        """
        获取最新新闻

        Params:
            limit: 获取条数，默认 10
            category: 分类（预留）
        """
        limit = params.get("limit", 10)

        try:
            async with httpx.AsyncClient(timeout=15.0) as client:
                # 获取热门新闻 ID 列表
                resp = await client.get(self.TOP_STORIES_URL)
                resp.raise_for_status()
                story_ids = resp.json()[:limit]

                # 获取每篇新闻的详情
                items = []
                for sid in story_ids:
                    try:
                        r = await client.get(self.ITEM_URL.format(sid))
                        r.raise_for_status()
                        story = r.json()
                        items.append({
                            "id": story.get("id"),
                            "title": story.get("title", ""),
                            "url": story.get("url", ""),
                            "score": story.get("score", 0),
                            "by": story.get("by", ""),
                            "time": datetime.fromtimestamp(
                                story.get("time", 0)
                            ).isoformat() if story.get("time") else "",
                        })
                    except Exception:
                        continue  # 单条失败不影响整体

            return SpiderResult(
                source="news",
                title=f"最新 {len(items)} 条新闻",
                data={"count": len(items), "source": "hackernews"},
                items=items,
            )

        except httpx.HTTPError as e:
            return self.error_result("news", f"HTTP 请求失败: {e}")
        except Exception as e:
            return self.error_result("news", f"解析失败: {e}")
