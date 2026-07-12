"""
动态页面爬虫 — Playwright JS 渲染

用于需要 JavaScript 执行才能加载内容的页面
技术栈: Playwright (Chromium headless)
"""
import asyncio
import logging
from datetime import datetime
from typing import Any
from crawler_service.spiders.base import BaseSpider, SpiderResult

logger = logging.getLogger(__name__)


class DynamicSpider(BaseSpider):
    """
    动态页面爬虫 — 使用 Playwright 渲染 JavaScript

    适用场景:
    - SPA 单页应用
    - AJAX 异步加载内容
    - 需要点击/滚动/等待的交互页面
    - 验证码截图
    """

    name = "dynamic"
    description = "Playwright JS 渲染爬虫 — 抓取需要 JavaScript 的动态页面"
    version = "1.0.0"

    async def crawl(self, **params) -> SpiderResult:
        """
        使用 Playwright 渲染并提取页面内容

        Params:
            url:         目标 URL (必填)
            action:      操作类型
                - "extract"  : 提取渲染后的文本和链接 (默认)
                - "screenshot": 截图保存
                - "wait"     : 等待特定元素出现后提取
            wait_for:    等待的选择器 (action=wait 时必填)
            wait_ms:     额外等待毫秒数 (默认 2000)
            extract_links: 是否提取链接 (默认 True)
        """
        url = params.get("url", "")
        if not url:
            return self.error_result("dynamic", "缺少 url 参数")

        action = params.get("action", "extract")
        wait_for = params.get("wait_for", "")
        wait_ms = params.get("wait_ms", 2000)
        extract_links = params.get("extract_links", True)

        from playwright.async_api import async_playwright

        async with async_playwright() as p:
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={"width": 1366, "height": 768},
                user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) Chrome/120.0.0.0",
            )
            page = await context.new_page()

            try:
                # 访问页面
                await page.goto(url, wait_until="networkidle", timeout=30000)

                # 等待 JS 渲染完成
                if wait_for:
                    try:
                        await page.wait_for_selector(wait_for, timeout=10000)
                        logger.info(f"Playwright: 元素 {wait_for} 已出现")
                    except Exception as e:
                        logger.warning(f"Playwright: 等待 {wait_for} 超时: {e}")

                await asyncio.sleep(wait_ms / 1000)

                # === 提取页面数据 ===
                page_title = await page.title()
                body_text = await page.inner_text("body")

                items = []

                if action == "screenshot":
                    import base64
                    screenshot = await page.screenshot(full_page=True)
                    items.append({
                        "type": "screenshot",
                        "format": "png",
                        "size_bytes": len(screenshot),
                        "encoding": "base64",
                        "data": base64.b64encode(screenshot).decode()[:200] + "...",
                    })

                # 提取链接
                if extract_links:
                    links = await page.evaluate("""
                        () => {
                            const anchors = document.querySelectorAll('a[href]');
                            return Array.from(anchors).slice(0, 50).map(a => ({
                                text: a.innerText.trim().substring(0, 100),
                                href: a.href.substring(0, 200)
                            }));
                        }
                    """)
                    for link in links[:30]:
                        if link["text"]:
                            items.append({
                                "type": "link",
                                "text": link["text"],
                                "href": link["href"],
                            })

                # 提取主要文本内容
                text_preview = body_text[:2000].strip()

                return SpiderResult(
                    source="dynamic",
                    title=page_title,
                    data={
                        "url": url,
                        "title": page_title,
                        "text_length": len(body_text),
                        "text_preview": text_preview[:500],
                        "links_found": len(items),
                        "rendered_by": "Playwright (Chromium headless)",
                        "crawled_at": datetime.now().isoformat(),
                    },
                    items=items,
                )

            except Exception as e:
                return self.error_result("dynamic", f"Playwright 错误: {e}")
            finally:
                await browser.close()
