"""
动态页面爬虫 — Playwright JS 渲染

用于需要 JavaScript 执行才能加载内容的页面
技术栈: Playwright (Chromium headless)
定位方式: XPath (不使用 CSS selector)
"""
import asyncio
import logging
from datetime import datetime
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

    所有元素定位使用 XPath
    """

    name = "dynamic"
    description = "Playwright JS 渲染爬虫 (XPath 定位)"
    version = "1.1.0"

    async def crawl(self, **params) -> SpiderResult:
        """
        使用 Playwright 渲染并提取页面内容

        Params:
            url:          目标 URL (必填)
            action:       操作类型
                - "extract"   : 提取渲染后的文本和链接 (默认)
                - "screenshot": 截图保存
                - "wait"      : 等待特定 XPath 元素出现后提取
            wait_for_xpath: 等待的 XPath 表达式 (action=wait 时必填)
                例: "//div[@id='content']" "//span[contains(@class,'title')]"
            wait_ms:       额外等待毫秒数 (默认 2000)
            extract_links: 是否提取链接 (默认 True)
        """
        url = params.get("url", "")
        if not url:
            return self.error_result("dynamic", "缺少 url 参数")

        action = params.get("action", "extract")
        wait_for_xpath = params.get("wait_for_xpath", "")
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

                # 等待 JS 渲染完成（XPath）
                if wait_for_xpath:
                    try:
                        await page.wait_for_selector(
                            f"xpath={wait_for_xpath}", timeout=10000
                        )
                        logger.info(f"Playwright: XPath {wait_for_xpath} 已匹配")
                    except Exception as e:
                        logger.warning(f"Playwright: 等待 XPath {wait_for_xpath} 超时: {e}")

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

                # 提取链接 (XPath)
                if extract_links:
                    links = await page.evaluate("""
                        () => {
                            const anchors = document.evaluate(
                                '//a[@href]', document, null,
                                XPathResult.ORDERED_NODE_SNAPSHOT_TYPE, null
                            );
                            const result = [];
                            const limit = Math.min(anchors.snapshotLength, 50);
                            for (let i = 0; i < limit; i++) {
                                const a = anchors.snapshotItem(i);
                                result.push({
                                    text: (a.innerText || '').trim().substring(0, 100),
                                    href: (a.href || '').substring(0, 200)
                                });
                            }
                            return result;
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
                        "rendered_by": "Playwright (Chromium headless) + XPath",
                        "crawled_at": datetime.now().isoformat(),
                    },
                    items=items,
                )

            except Exception as e:
                return self.error_result("dynamic", f"Playwright 错误: {e}")
            finally:
                await browser.close()
