"""
新闻爬虫 — BeautifulSoup HTML 解析

数据源: HackerNews / 可配置其他 HTML 新闻源
技术栈: requests + BeautifulSoup4 (lxml 解析器)
"""
import httpx
from datetime import datetime
from bs4 import BeautifulSoup
from crawler_service.spiders.base import BaseSpider, SpiderResult
from common.utils.http_client import get_response


class NewsSpider(BaseSpider):
    """新闻爬虫 — 使用 BeautifulSoup 解析 HTML 页面"""

    name = "news"
    description = "从 HackerNews HTML 页面解析热门新闻 (BeautifulSoup + lxml)"
    version = "1.1.0"

    HN_URL = "https://news.ycombinator.com/"

    async def crawl(self, **params) -> SpiderResult:
        """
        爬取 HackerNews 首页，用 BeautifulSoup 提取新闻列表

        Params:
            limit: 获取条数，默认 15
        """
        limit = params.get("limit", 15)

        try:
            resp = await get_response(
                "news",
                self.HN_URL,
                timeout=15.0,
                follow_redirects=True,
                headers={"User-Agent": "Mozilla/5.0 (compatible; AI-Schedule-Agent/1.0)"},
            )
            html = resp.text

            # === BeautifulSoup 解析 HTML ===
            soup = BeautifulSoup(html, "lxml")  # 使用 lxml 解析器

            items = []
            # HackerNews 结构: <tr class="athing"> 包含每条新闻
            rows = soup.find_all("tr", class_="athing")

            for row in rows[:limit]:
                # 提取标题行 <span class="titleline"><a href="...">标题</a></span>
                titleline = row.find("span", class_="titleline")
                if not titleline:
                    continue

                link = titleline.find("a")
                if not link:
                    continue

                title = link.get_text(strip=True)
                url = link.get("href", "")

                # 提取元数据（分数/作者/评论数）在下一行 <tr>
                metadata_row = row.find_next_sibling("tr")
                score = 0
                author = ""
                comments = 0

                if metadata_row:
                    # 分数: <span class="score">123 points</span>
                    score_span = metadata_row.find("span", class_="score")
                    if score_span:
                        score_text = score_span.get_text(strip=True)
                        try:
                            score = int(score_text.split()[0])
                        except (ValueError, IndexError):
                            pass

                    # 作者: <a class="hnuser" href="user?id=...">username</a>
                    user_link = metadata_row.find("a", class_="hnuser")
                    if user_link:
                        author = user_link.get_text(strip=True)

                    # 评论数: 最后一个 <a> 包含 "comments"
                    all_links = metadata_row.find_all("a")
                    for a in all_links:
                        text = a.get_text(strip=True)
                        if "comment" in text:
                            try:
                                comments = int(text.split()[0])
                            except (ValueError, IndexError):
                                pass

                items.append({
                    "title": title,
                    "url": url,
                    "score": score,
                    "author": author,
                    "comments": comments,
                    "source": "hackernews",
                    "crawled_at": datetime.now().isoformat(),
                })

            # 同时提取页面标题
            page_title_tag = soup.find("title")
            page_title = page_title_tag.get_text(strip=True) if page_title_tag else "Hacker News"

            return SpiderResult(
                source="news",
                title=f"{page_title} — 前{len(items)}条",
                data={
                    "count": len(items),
                    "source": "hackernews_html",
                    "parser": "BeautifulSoup4 + lxml",
                    "crawled_at": datetime.now().isoformat(),
                },
                items=items,
            )

        except httpx.HTTPError as e:
            return self.error_result("news", f"HTTP 请求失败: {e}")
        except Exception as e:
            return self.error_result("news", f"HTML 解析失败: {e}")
