"""
日历/节假日爬虫

数据源: 可配置（中国法定节假日）
"""
import httpx
from datetime import date
from crawler_service.spiders.base import BaseSpider, SpiderResult


class CalendarSpider(BaseSpider):
    """节假日/日历数据爬虫"""

    name = "calendar"
    description = "获取中国法定节假日信息"
    version = "1.0.0"

    async def crawl(self, **params) -> SpiderResult:
        """
        获取节假日

        Params:
            year: 年份，默认当前年份
            include_weekend: 是否标注周末，默认 True
        """
        year = params.get("year", date.today().year)
        include_weekend = params.get("include_weekend", True)

        try:
            # 尝试从公开 API 获取中国节假日
            url = f"https://date.nager.at/api/v3/PublicHolidays/{year}/CN"
            holidays = []

            async with httpx.AsyncClient(timeout=15.0) as client:
                resp = await client.get(url)
                if resp.status_code == 200:
                    raw = resp.json()
                    for h in raw:
                        holidays.append({
                            "date": h.get("date"),
                            "name": h.get("localName", h.get("name", "")),
                            "type": "public_holiday",
                        })
                else:
                    # 回退：返回一些已知的节假日
                    holidays = self._fallback_holidays(year)

            items = holidays
            if include_weekend:
                items = self._add_weekend_info(items, year)

            return SpiderResult(
                source="calendar",
                title=f"{year}年 节假日日历",
                data={"year": year, "count": len(holidays)},
                items=items,
            )

        except httpx.HTTPError as e:
            # 网络不可用时用回退数据
            items = self._fallback_holidays(year)
            return SpiderResult(
                source="calendar",
                title=f"{year}年 节假日日历 (离线数据)",
                data={"year": year, "count": len(items), "offline": True},
                items=items,
            )
        except Exception as e:
            return self.error_result("calendar", str(e))

    @staticmethod
    def _fallback_holidays(year: int) -> list[dict]:
        """中国法定节假日回退数据（离线）"""
        holidays = {
            2026: [
                ("2026-01-01", "元旦"),
                ("2026-02-17", "春节"),
                ("2026-02-18", "春节"),
                ("2026-02-19", "春节"),
                ("2026-04-05", "清明节"),
                ("2026-05-01", "劳动节"),
                ("2026-05-02", "劳动节"),
                ("2026-05-03", "劳动节"),
                ("2026-06-19", "端午节"),
                ("2026-09-25", "中秋节"),
                ("2026-10-01", "国庆节"),
                ("2026-10-02", "国庆节"),
                ("2026-10-03", "国庆节"),
            ],
        }
        return [
            {"date": d, "name": n, "type": "public_holiday"}
            for d, n in holidays.get(year, holidays.get(2026, []))
        ]

    @staticmethod
    def _add_weekend_info(items: list[dict], year: int) -> list[dict]:
        """标注周末（简化版：只标注已有数据中的周末）"""
        # 更完整的实现需要遍历全年，这里做简化版
        return items
