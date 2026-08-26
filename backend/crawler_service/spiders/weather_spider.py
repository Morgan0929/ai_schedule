"""
天气预报爬虫

数据源: wttr.in (免费，无需 API Key)
格式: JSON
"""
import httpx
from crawler_service.spiders.base import BaseSpider, SpiderResult
from common.utils.http_client import get_json


class WeatherSpider(BaseSpider):
    """天气预报爬虫"""

    name = "weather"
    description = "获取指定城市的天气预报（数据源: wttr.in）"
    version = "1.0.0"

    async def crawl(self, **params) -> SpiderResult:
        """
        获取天气预报

        Params:
            city: 城市名（中文或英文），默认 Beijing
            days: 预报天数 1-3，默认 2
        """
        city = params.get("city", "Beijing")
        days = params.get("days", 2)

        url = f"https://wttr.in/{city}?format=j1&days={days}"

        try:
            raw = await get_json("weather", url, timeout=15.0, follow_redirects=True)

            # 提取关键信息
            weather_data = self._extract_weather(raw, city)

            return SpiderResult(
                source="weather",
                title=f"{city} 天气预报",
                data=weather_data,
                items=weather_data.get("daily", []),
            )

        except httpx.HTTPError as e:
            return self.error_result("weather", f"HTTP 请求失败: {e}")
        except Exception as e:
            return self.error_result("weather", f"解析失败: {e}")

    def _extract_weather(self, raw: dict, city: str) -> dict:
        """从 wttr.in 原始 JSON 中提取结构化数据"""
        try:
            current = raw.get("current_condition", [{}])[0]
            forecasts = raw.get("weather", [])

            daily = []
            for f in forecasts[:3]:
                daily.append({
                    "date": f.get("date", ""),
                    "high": f"{f.get('maxtempC', '?')}°C",
                    "low": f"{f.get('mintempC', '?')}°C",
                    "description": self._translate(
                        f.get("hourly", [{}])[4].get("weatherDesc", [{}])[0].get("value", "")),
                    "chance_of_rain": f"{f.get('hourly', [{}])[4].get('chanceofrain', '0')}%",
                })

            return {
                "city": city,
                "current_temp": f"{current.get('temp_C', '?')}°C",
                "current_desc": current.get("weatherDesc", [{}])[0].get("value", ""),
                "humidity": f"{current.get('humidity', '?')}%",
                "wind_speed": f"{current.get('windspeedKmph', '?')} km/h",
                "daily": daily,
            }
        except Exception:
            return {"city": city, "raw": raw, "parse_error": True}

    @staticmethod
    def _translate(text: str) -> str:
        """简单的英文→中文天气描述映射"""
        mapping = {
            "Sunny": "晴", "Clear": "晴",
            "Partly cloudy": "多云", "Partly Cloudy": "多云",
            "Cloudy": "阴", "Overcast": "阴",
            "Mist": "薄雾", "Fog": "雾",
            "Light rain": "小雨", "Light Rain": "小雨",
            "Moderate rain": "中雨", "Moderate Rain": "中雨",
            "Heavy rain": "大雨", "Heavy Rain": "大雨",
            "Light snow": "小雪", "Light Snow": "小雪",
            "Patchy rain possible": "可能有零星降雨",
        }
        return mapping.get(text, text)
