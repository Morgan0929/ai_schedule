"""Import course schedules from a public or already-authenticated page."""
from __future__ import annotations

import ipaddress
import json
import re
import socket
import html as html_lib
from datetime import date, datetime
from urllib.parse import urljoin, urlparse

import httpx
from bs4 import BeautifulSoup
from sqlalchemy.ext.asyncio import AsyncSession

from crawler_service.models.crawl_model import CrawlDataModel
from timeline_service.models.schedule_model import ScheduleModel, get_current_semester
from timeline_service.repository.schedule_repo import ScheduleRepository


COURSE_LINK_WORDS = ("课表", "课程表", "我的课程", "个人课表", "学生课表", "课程查询")
LOGIN_WORDS = ("登录", "统一身份认证", "用户名", "账号", "密码", "验证码")
INVALID_COURSE_NAMES = {"全部", "(全部)", "请选择", "课程", "课表", "我的课表", "全校课表"}
NON_TEACHER_WORDS = ("计算机科学与技术", "学院", "专业", "方向", "班", "校区")


class ScheduleImportService:
    def __init__(self, db: AsyncSession):
        self.db = db

    async def import_from_url(self, user_id: int, url: str) -> dict:
        await _validate_public_url(url)
        crawl_result = await crawl_schedule_page(url)

        status = crawl_result["status"]
        courses = crawl_result.get("courses", [])
        saved_count = 0
        if status == "IMPORTED" and courses:
            saved_count = await self._save_courses(user_id, courses, url)

        record = CrawlDataModel(
            user_id=user_id,
            source="schedule_url",
            source_url=url,
            raw_data={
                "menu_url": crawl_result.get("menu_url"),
                "courses": courses,
            },
            extracted_info={
                "status": status,
                "course_count": saved_count,
                "message": crawl_result["message"],
            },
            status="SUCCESS" if status == "IMPORTED" else status,
            error_message=None if status in {"IMPORTED", "LOGIN_REQUIRED"} else crawl_result["message"],
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.commit()

        return {
            "status": status,
            "message": crawl_result["message"],
            "course_count": saved_count,
            "menu_url": crawl_result.get("menu_url"),
            "record_id": record.id,
        }

    async def import_from_html(self, user_id: int, html: str, source_url: str = "") -> dict:
        if source_url:
            parsed_source = urlparse(source_url)
            if parsed_source.scheme in {"http", "https"} and parsed_source.hostname:
                await _validate_public_url(source_url)
        crawl_result = import_schedule_html(html, source_url or "webview")

        status = crawl_result["status"]
        courses = crawl_result.get("courses", [])
        saved_count = 0
        if status == "IMPORTED" and courses:
            saved_count = await self._save_courses(user_id, courses, source_url or "webview")

        record = CrawlDataModel(
            user_id=user_id,
            source="schedule_html",
            source_url=source_url or None,
            raw_data={
                "menu_url": crawl_result.get("menu_url"),
                "courses": courses,
                "html_length": len(html),
                "html_diagnostics": _html_diagnostics(html),
                "parser_diagnostics": _parser_diagnostics(html),
            },
            extracted_info={
                "status": status,
                "course_count": saved_count,
                "message": crawl_result["message"],
            },
            status="SUCCESS" if status == "IMPORTED" else status,
            error_message=None if status == "IMPORTED" else crawl_result["message"],
        )
        self.db.add(record)
        await self.db.flush()
        await self.db.commit()

        return {
            "status": status,
            "message": crawl_result["message"],
            "course_count": saved_count,
            "menu_url": crawl_result.get("menu_url"),
            "record_id": record.id,
        }

    async def _save_courses(self, user_id: int, courses: list[dict], source_url: str) -> int:
        semester = get_current_semester()
        models = []
        for course in courses:
            name = str(course.get("course_name", "")).strip()
            if not _is_valid_course(course):
                continue
            models.append(
                ScheduleModel(
                    user_id=user_id,
                    source=urlparse(source_url).hostname or "schedule_url",
                    course_name=name,
                    teacher=course.get("teacher") or None,
                    location=course.get("location") or None,
                    week_day=int(course.get("week_day") or 1),
                    start_week=int(course.get("start_week") or 1),
                    end_week=int(course.get("end_week") or 20),
                    start_time=_parse_time(course.get("start_time")),
                    end_time=_parse_time(course.get("end_time")),
                    start_section=_optional_int(course.get("start_section")),
                    end_section=_optional_int(course.get("end_section")),
                    semester=semester,
                    raw_data=json.dumps(course, ensure_ascii=False),
                )
            )

        if not models:
            return 0
        saved = await ScheduleRepository(self.db).save_batch(models)
        await self.db.flush()
        return len(saved)


async def crawl_schedule_page(url: str) -> dict:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
            "AppleWebKit/537.36 Chrome/126.0 Safari/537.36"
        )
    }
    try:
        async with httpx.AsyncClient(
            headers=headers,
            follow_redirects=True,
            timeout=httpx.Timeout(25.0),
        ) as client:
            response = await client.get(url)
            response.raise_for_status()
            html = response.text
            final_url = str(response.url)
            await _validate_public_url(final_url)
            soup = BeautifulSoup(html, "lxml")

            courses = extract_courses_from_html(html)
            if courses:
                return _imported(courses, final_url)

            candidates = find_schedule_links(soup, final_url)
            if _looks_like_login_page(soup, final_url) and not candidates:
                return {
                    "status": "LOGIN_REQUIRED",
                    "message": "该网址需要登录后才能读取课表。请先在学校教务系统完成登录，再提供可访问的课表页面地址。",
                    "courses": [],
                    "menu_url": None,
                }

            for candidate in candidates[:6]:
                await _validate_same_host(final_url, candidate)
                page = await client.get(candidate)
                page.raise_for_status()
                page_html = page.text
                page_url = str(page.url)
                await _validate_same_host(final_url, page_url)
                page_soup = BeautifulSoup(page_html, "lxml")
                if _looks_like_login_page(page_soup, page_url):
                    return {
                        "status": "LOGIN_REQUIRED",
                        "message": "已找到课表入口，但访问时跳转到了登录页。请先完成学校登录。",
                        "courses": [],
                        "menu_url": candidate,
                    }
                courses = extract_courses_from_html(page_html)
                if courses:
                    return _imported(courses, page_url)

            return {
                "status": "NOT_FOUND",
                "message": "页面可以访问，但没有识别到课表菜单或课程表格。请填写登录后的具体课表页面地址。",
                "courses": [],
                "menu_url": candidates[0] if candidates else None,
            }
    except httpx.HTTPError as exc:
        return {
            "status": "FAILED",
            "message": f"访问课表网址失败：{exc}",
            "courses": [],
            "menu_url": None,
        }


def import_schedule_html(html: str, source_url: str = "webview") -> dict:
    normalized_html = _normalize_import_html(html)
    soup = BeautifulSoup(normalized_html, "lxml")
    courses = extract_courses_from_html(normalized_html)
    if courses:
        return _imported(courses, source_url, _parser_diagnostics(html))
    if _looks_like_login_page(soup, source_url):
        return {
            "status": "LOGIN_REQUIRED",
            "message": "当前页面仍是登录页。请先在内置浏览器完成登录，并进入课表页面后再导入。",
            "courses": [],
            "menu_url": source_url,
        }
    return {
        "status": "NOT_FOUND",
        "message": "当前页面没有识别到课程表格。请先打开课表查询结果页，再点击导入。",
        "courses": [],
        "menu_url": source_url,
    }


def find_schedule_links(soup: BeautifulSoup, base_url: str) -> list[str]:
    links = []
    for anchor in soup.find_all("a", href=True):
        text = " ".join(anchor.stripped_strings)
        title = str(anchor.get("title") or "")
        if not any(word in f"{text} {title}" for word in COURSE_LINK_WORDS):
            continue
        target = urljoin(base_url, str(anchor["href"]))
        if urlparse(target).scheme not in {"http", "https"}:
            continue
        if target not in links:
            links.append(target)
    return links


def extract_courses_from_html(html: str) -> list[dict]:
    normalized_html = _normalize_import_html(html)
    soup = BeautifulSoup(normalized_html, "lxml")
    courses = _deduplicate_courses([
        course for course in _extract_state_course_tables(soup) if _is_valid_course(course)
    ])
    if courses:
        return courses
    courses = _deduplicate_courses([
        course for course in _extract_fullcalendar_events(soup) if _is_valid_course(course)
    ])
    if courses:
        return courses
    courses = _deduplicate_courses([
        course for course in _extract_embedded_visual_course_tables(normalized_html) if _is_valid_course(course)
    ])
    if courses:
        return courses
    courses = _deduplicate_courses([
        course for course in _extract_embedded_fullcalendar_events(normalized_html) if _is_valid_course(course)
    ])
    if courses:
        return courses
    courses = _deduplicate_courses([
        course for course in _extract_visual_course_tables(soup) if _is_valid_course(course)
    ])
    if courses:
        return courses
    courses = _extract_column_tables(soup)
    courses.extend(_extract_matrix_tables(soup))
    return _deduplicate_courses([course for course in courses if _is_valid_course(course)])


def _normalize_import_html(html: str) -> str:
    text = str(html or "")
    candidates = [text]
    for _ in range(2):
        current = candidates[-1].strip()
        if not current or not (
            (current.startswith('"') and current.endswith('"'))
            or (current.startswith("'") and current.endswith("'"))
        ):
            break
        try:
            decoded = json.loads(current)
        except (TypeError, ValueError):
            break
        if not isinstance(decoded, str) or decoded == candidates[-1]:
            break
        candidates.append(decoded)

    current = candidates[-1]
    replacements = {
        r"\u003c": "<",
        r"\u003C": "<",
        r"\u003e": ">",
        r"\u003E": ">",
        r"\u0026": "&",
        r"\u0022": '"',
        r"\u0027": "'",
    }
    for escaped, value in replacements.items():
        current = current.replace(escaped, value)
    current = current.replace(r'\"', '"').replace(r"\'", "'")
    current = current.replace(r"\/", "/")
    return current


def _extract_state_course_tables(soup: BeautifulSoup) -> list[dict]:
    courses = []
    for table in soup.find_all("table", attrs={"data-codex-state-courses": "true"}):
        courses.extend(_extract_column_courses_from_table(table))
    return courses


def _extract_fullcalendar_events(soup: BeautifulSoup) -> list[dict]:
    courses = []
    entries = []
    visual_headers = _extract_visual_headers(soup)
    for node in _fullcalendar_event_nodes(soup):
        title_node = node.select_one(".fc-event-title")
        if title_node is None:
            continue
        raw_lines = [
            _repair_text(item.get_text(" ", strip=True))
            for item in title_node.find_all("div", recursive=False)
        ]
        lines = [line for line in raw_lines if line and line.lower() != "null"]
        if not lines:
            continue
        section_text = ""
        time_node = node.select_one(".fc-event-time")
        if time_node is not None:
            section_text = _repair_text(time_node.get_text(" ", strip=True))
        start_section, end_section = _parse_range(section_text, None)
        target = node
        left = _style_number(target.get("style"), "left")
        top = _style_number(target.get("style"), "top")
        parent = node.parent
        while (left is None or top is None) and parent is not None:
            left = left if left is not None else _style_number(parent.get("style"), "left")
            top = top if top is not None else _style_number(parent.get("style"), "top")
            parent = parent.parent
        entries.append({
            "left": int(left or 0),
            "top": int(top or 0),
            "lines": lines,
            "start_section": start_section,
            "end_section": end_section,
        })
    if not entries:
        return []
    left_to_day = _visual_left_to_day(
        [{"left": entry["left"], "width": 0} for entry in entries],
        visual_headers,
    )
    top_to_section = _visual_top_to_section([
        {"top": entry["top"]} for entry in entries
    ])
    for entry in entries:
        section_start = entry["start_section"] or top_to_section[entry["top"]]
        section_end = entry["end_section"] or section_start
        courses.extend(_courses_from_matrix_lines(
            entry["lines"],
            week_day=left_to_day[entry["left"]],
            section_start=section_start,
            section_end=section_end,
        ))
    return courses


def _fullcalendar_event_nodes(soup: BeautifulSoup) -> list:
    event_nodes = list(soup.select(".fc-event"))
    event_nodes.extend(
        node for node in soup.select(".fc-event-inner")
        if node.find_parent(class_="fc-event") is None
    )
    return event_nodes


def _extract_embedded_fullcalendar_events(html: str) -> list[dict]:
    fragments = _embedded_fullcalendar_fragments(html)
    if not fragments:
        return []
    soup = BeautifulSoup("\n".join(fragments), "lxml")
    return _extract_fullcalendar_events(soup)


def _extract_embedded_visual_course_tables(html: str) -> list[dict]:
    tables = _embedded_codex_tables(html, ("data-codex-visual-courses", "data-codex-visual-headers"))
    if not tables:
        return []
    return _extract_visual_course_tables(BeautifulSoup("\n".join(tables), "lxml"))


def _embedded_codex_tables(html: str, markers: tuple[str, ...]) -> list[str]:
    text = html_lib.unescape(str(html or ""))
    tables = []
    seen = set()
    for match in re.finditer(r"<table\b[^>]*>.*?</table>", text, re.I | re.S):
        table = match.group(0)
        if not any(marker in table for marker in markers):
            continue
        if table in seen:
            continue
        seen.add(table)
        tables.append(table)
    return tables


def _embedded_fullcalendar_fragments(html: str) -> list[str]:
    text = html_lib.unescape(str(html or ""))
    starts = [
        match.start()
        for match in re.finditer(
            r"<div\b(?=[^>]*\bclass\s*=\s*(?:\"[^\"]*(?<![\w-])fc-event(?:-inner)?(?![\w-])[^\"]*\"|'[^']*(?<![\w-])fc-event(?:-inner)?(?![\w-])[^']*'))[^>]*>",
            text,
            re.I,
        )
    ]
    fragments = []
    seen = set()
    seen_ranges = []
    for start in starts:
        if any(range_start <= start < range_end for range_start, range_end in seen_ranges):
            continue
        fragment = _balanced_div_fragment(text, start)
        if not fragment or "fc-event-title" not in fragment:
            continue
        if fragment in seen:
            continue
        seen.add(fragment)
        seen_ranges.append((start, start + len(fragment)))
        fragments.append(fragment)
    return fragments


def _balanced_div_fragment(text: str, start: int) -> str:
    depth = 0
    for match in re.finditer(r"</?div\b[^>]*>", text[start:], re.I):
        tag = match.group(0)
        if tag.startswith("</"):
            depth -= 1
        else:
            depth += 1
        if depth == 0:
            return text[start:start + match.end()]
    return ""


def _style_number(style: str | None, name: str) -> float | None:
    if not style:
        return None
    match = re.search(rf"{re.escape(name)}\s*:\s*(-?\d+(?:\.\d+)?)px", style)
    return float(match.group(1)) if match else None


def _extract_visual_course_tables(soup: BeautifulSoup) -> list[dict]:
    courses = []
    for table in soup.find_all("table", attrs={"data-codex-visual-courses": "true"}):
        rows = table.find_all("tr")[1:]
        visual_headers = _extract_visual_headers(soup)
        entries = []
        for row in rows:
            values = [cell.get_text("\n", strip=True) for cell in row.find_all(["th", "td"])]
            if len(values) < 3:
                continue
            try:
                top = int(float(values[0]))
                left = int(float(values[1]))
                width = int(float(values[2])) if len(values) >= 5 else 0
                height = int(float(values[3])) if len(values) >= 5 else 0
            except ValueError:
                continue
            text = _repair_text(values[4] if len(values) >= 5 else values[2])
            lines = _visual_course_lines(text)
            if not lines:
                continue
            if not _looks_like_course_name(lines[0]) or not _matrix_location(lines):
                continue
            entries.append({"top": top, "left": left, "width": width, "height": height, "lines": lines})
        if not entries:
            continue

        left_to_day = _visual_left_to_day(entries, visual_headers)
        top_to_section = _visual_top_to_section(entries)
        for entry in entries:
            section_start = top_to_section[entry["top"]]
            courses.extend(_courses_from_matrix_lines(
                entry["lines"],
                week_day=left_to_day[entry["left"]],
                section_start=section_start,
                section_end=section_start + 1,
            ))
    return courses


def _extract_visual_headers(soup: BeautifulSoup) -> list[dict]:
    headers = []
    for table in soup.find_all("table", attrs={"data-codex-visual-headers": "true"}):
        for row in table.find_all("tr")[1:]:
            values = [_repair_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
            if len(values) < 5:
                continue
            try:
                top = int(float(values[0]))
                left = int(float(values[1]))
                width = int(float(values[2]))
            except ValueError:
                continue
            weekday = _parse_weekday(values[4])
            if weekday is None:
                parsed = _parse_month_day_header(values[4], _parse_schedule_year(soup.get_text(" ", strip=True)))
                weekday = parsed.weekday() + 1 if parsed else None
            if weekday is None:
                continue
            headers.append({"top": top, "left": left, "width": width, "weekday": weekday})
    return headers


def _visual_left_to_day(entries: list[dict], headers: list[dict]) -> dict[int, int]:
    if headers:
        result = {}
        for entry in entries:
            entry_center = entry["left"] + max(entry.get("width") or 0, 1) / 2
            header = min(
                headers,
                key=lambda item: abs(entry_center - (item["left"] + max(item.get("width") or 0, 1) / 2)),
            )
            result[entry["left"]] = header["weekday"]
        return result
    clustered = _cluster_positions(entry["left"] for entry in entries)
    return {
        entry["left"]: _nearest_index(entry["left"], clustered) + 1
        for entry in entries
    }


def _visual_top_to_section(entries: list[dict]) -> dict[int, int]:
    clustered = _cluster_positions((entry["top"] for entry in entries), tolerance=24)
    return {
        entry["top"]: _nearest_index(entry["top"], clustered) * 2 + 1
        for entry in entries
    }


def _cluster_positions(values, tolerance: int = 18) -> list[int]:
    clusters: list[list[int]] = []
    for value in sorted(int(v) for v in values):
        if clusters and abs(value - round(sum(clusters[-1]) / len(clusters[-1]))) <= tolerance:
            clusters[-1].append(value)
        else:
            clusters.append([value])
    return [round(sum(cluster) / len(cluster)) for cluster in clusters]


def _nearest_index(value: int, positions: list[int]) -> int:
    return min(range(len(positions)), key=lambda index: abs(value - positions[index]))


def _visual_course_lines(text: str) -> list[str]:
    text = _repair_text(text)
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) > 1:
        return lines
    value = re.sub(r"\s+", " ", text or "").strip()
    if not value:
        return []
    classroom = re.search(r"(教\s*-?\s*\d+|[A-Z]\d{2,}|实验\S*|\d+\s*室|\S*楼|\S*馆|\S*校区)", value)
    if not classroom:
        return [value]
    before = value[:classroom.start()].strip()
    location = classroom.group(1).strip()
    tokens = [token.strip() for token in re.split(r"\s+", before) if token.strip()]
    return [*tokens, location] if tokens else [location]


def _extract_column_tables(soup: BeautifulSoup) -> list[dict]:
    courses = []
    for table in soup.find_all("table"):
        courses.extend(_extract_column_courses_from_table(table))
    return courses


def _extract_column_courses_from_table(table) -> list[dict]:
    courses = []
    rows = table.find_all("tr")
    if len(rows) < 2:
        return []
    headers = [_repair_text(cell.get_text(" ", strip=True)) for cell in rows[0].find_all(["th", "td"])]
    name_index = _header_index(headers, ("课程名称", "课程名", "课程", "科目"))
    if name_index is None:
        return []
    for row in rows[1:]:
        values = [_repair_text(cell.get_text(" ", strip=True)) for cell in row.find_all(["th", "td"])]
        if name_index >= len(values) or not values[name_index]:
            continue
        course = {
            "course_name": values[name_index],
            "teacher": _value_for(headers, values, ("教师", "老师", "授课教师")),
            "location": _value_for(headers, values, ("教室", "地点", "上课地点")),
        }
        weekday_text = _value_for(headers, values, ("星期", "周几", "上课星期"))
        section_text = _value_for(headers, values, ("节次", "上课节次"))
        week_text = _value_for(headers, values, ("周次", "上课周次"))
        time_text = _value_for(headers, values, ("上课时间", "时间"))
        course.update(_parse_course_timing(weekday_text, section_text, week_text, time_text))
        if course.get("week_day"):
            courses.append(course)
    return courses


def _extract_matrix_tables(soup: BeautifulSoup) -> list[dict]:
    courses = []
    page_text = soup.get_text(" ", strip=True)
    for table in soup.find_all("table"):
        rows = table.find_all("tr")
        if len(rows) < 2:
            continue
        headers = [_repair_text(cell.get_text(" ", strip=True)) for cell in rows[0].find_all(["th", "td"])]
        weekdays = _parse_header_weekdays(headers, page_text)
        if sum(day is not None for day in weekdays) < 2:
            continue
        for row_number, row in enumerate(rows[1:], start=1):
            cells = row.find_all(["th", "td"])
            if not cells:
                continue
            section_text = cells[0].get_text(" ", strip=True)
            section_start, section_end = _parse_range(section_text, row_number)
            for index, cell in enumerate(cells):
                if index >= len(weekdays) or weekdays[index] is None:
                    continue
                text = _repair_text(cell.get_text("\n", strip=True))
                if not text or text in {"-", "无"}:
                    continue
                lines = [line.strip() for line in text.splitlines() if line.strip()]
                if not lines:
                    continue
                courses.extend(_courses_from_matrix_lines(
                    lines,
                    week_day=weekdays[index],
                    section_start=section_start,
                    section_end=section_end,
                ))
    return courses


def _courses_from_matrix_lines(
    lines: list[str], week_day: int, section_start: int | None, section_end: int | None
) -> list[dict]:
    blocks = _split_course_blocks(lines)
    courses = []
    for block in blocks:
        if not block:
            continue
        courses.append({
            "course_name": _clean_matrix_course_name(block[0]),
            "teacher": _matrix_teacher(block),
            "location": _matrix_location(block),
            "week_day": week_day,
            "start_section": section_start,
            "end_section": section_end,
            **_parse_matrix_weeks("\n".join(block)),
        })
    return courses


def _split_course_blocks(lines: list[str]) -> list[list[str]]:
    blocks: list[list[str]] = []
    current: list[str] = []
    for line in [line.strip() for line in lines if line.strip()]:
        if current and _looks_like_course_name(line) and _matrix_location(current):
            blocks.append(current)
            current = [line]
        else:
            current.append(line)
    if current:
        blocks.append(current)
    return blocks


def _looks_like_course_name(value: str) -> bool:
    value = _repair_text(value)
    value = _clean_matrix_course_name(value)
    if not value or value in INVALID_COURSE_NAMES:
        return False
    if _looks_like_schedule_header(value):
        return False
    if _looks_like_classroom(value):
        return False
    return bool(re.search(r"[\u4e00-\u9fff]", value)) and not any(word in value for word in NON_TEACHER_WORDS)


def _looks_like_schedule_header(value: str) -> bool:
    compact = re.sub(r"\s+", " ", value or "").strip()
    if not compact:
        return False
    if re.fullmatch(r"(?:[一二三四五六日天]|周[一二三四五六日天]|星期[一二三四五六日天])\s*\d{1,2}\s*[/-]\s*\d{1,2}", compact):
        return True
    if re.fullmatch(r"\d{1,2}\s*[/-]\s*\d{1,2}", compact):
        return True
    return bool(re.fullmatch(r"(?:第?\d{1,2}(?:-\d{1,2})?节|周次|第\d{1,2}周)", compact))


def _clean_matrix_course_name(value: str) -> str:
    value = _repair_text(value)
    return re.sub(r"[★*]\s*\d+\s*-\s*\d+.*$", "", value or "").strip()


def _parse_matrix_weeks(value: str) -> dict:
    match = re.search(r"[★*]?\s*(\d{1,2})\s*-\s*(\d{1,2})", value or "")
    if not match:
        return {"start_week": 1, "end_week": 20}
    return {"start_week": int(match.group(1)), "end_week": int(match.group(2))}


def _matrix_location(lines: list[str]) -> str:
    for line in lines[1:]:
        if _looks_like_classroom(line):
            return _normalize_location(line)
    return ""


def _matrix_teacher(lines: list[str]) -> str:
    location = _matrix_location(lines)
    if location:
        loc_index = next((index for index, line in enumerate(lines) if line.strip() == location), -1)
        for line in reversed(lines[1:loc_index if loc_index > 0 else len(lines)]):
            stripped = line.strip()
            if stripped and not any(word in stripped for word in NON_TEACHER_WORDS):
                return stripped
    for line in lines[1:]:
        stripped = line.strip()
        if stripped and stripped != location and not any(word in stripped for word in NON_TEACHER_WORDS):
            return stripped
    return ""


def _looks_like_classroom(value: str) -> bool:
    value = _repair_text(value)
    value = value.strip()
    return bool(re.search(r"((?:教|æ)\s*-?\s*\d+|[A-Z]\d{2,}|实验|\d+\s*室|楼|馆|校区)", value))


def _normalize_location(value: str) -> str:
    value = _repair_text(value).strip()
    match = re.fullmatch(r"æ\s*-?\s*(\d+)", value)
    if match:
        return f"教-{match.group(1)}"
    return value


def _is_valid_course(course: dict) -> bool:
    name = _clean_matrix_course_name(str(course.get("course_name", "")).strip())
    location = _repair_text(str(course.get("location") or "").strip())
    if not _looks_like_course_name(name):
        return False
    if re.fullmatch(r"[\d\s:：/.-]+", name):
        return False
    if location and not _looks_like_classroom(location):
        course["location"] = ""
    elif location:
        course["location"] = _normalize_location(location)
    return bool(course.get("week_day"))


def _parse_course_timing(weekday: str, section: str, week: str, time_text: str) -> dict:
    start_section, end_section = _parse_range(section, None)
    start_week, end_week = _parse_range(week, 1)
    times = re.findall(r"(?:[01]?\d|2[0-3]):[0-5]\d", time_text or "")
    return {
        "week_day": _parse_weekday(weekday),
        "start_section": start_section,
        "end_section": end_section,
        "start_week": start_week or 1,
        "end_week": end_week or start_week or 20,
        "start_time": times[0] if times else None,
        "end_time": times[1] if len(times) > 1 else None,
    }


def _parse_weekday(value: str) -> int | None:
    value = _repair_text(value or "")
    mapping = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "日": 7, "天": 7}
    match = re.search(r"(?:星期|周)?([一二三四五六日天1-7])", value)
    if not match:
        return None
    token = match.group(1)
    return int(token) if token.isdigit() else mapping[token]


def _parse_header_weekdays(headers: list[str], page_text: str = "") -> list[int | None]:
    year = _parse_schedule_year(page_text)
    weekdays: list[int | None] = []
    has_date_header = False
    for header in headers:
        parsed = _parse_month_day_header(header, year)
        if parsed:
            weekdays.append(parsed.weekday() + 1)
            has_date_header = True
        else:
            weekdays.append(_parse_weekday(header))
    if has_date_header:
        return weekdays

    weekdays = [_parse_weekday(header) for header in headers]
    if any(day is not None for day in weekdays):
        return weekdays

    date_indexes: list[tuple[int, date]] = []
    for index, header in enumerate(headers):
        parsed = _parse_month_day_header(header, year)
        if parsed:
            date_indexes.append((index, parsed))
    for index, parsed in date_indexes:
        weekdays[index] = parsed.weekday() + 1
    return weekdays


def _parse_schedule_year(page_text: str) -> int:
    match = re.search(r"(20\d{2})\s*(?:秋季|春季|学年|年)", page_text or "")
    if match:
        return int(match.group(1))
    return date.today().year


def _parse_month_day_header(value: str, year: int) -> date | None:
    match = re.search(r"(?<!\d)(\d{1,2})\s*[/-]\s*(\d{1,2})(?!\d)", value or "")
    if not match:
        return None
    month = int(match.group(1))
    day = int(match.group(2))
    try:
        return date(year, month, day)
    except ValueError:
        return None


def _parse_range(value: str, default: int | None) -> tuple[int | None, int | None]:
    numbers = [int(number) for number in re.findall(r"\d+", value or "")]
    if not numbers:
        return default, default
    return numbers[0], numbers[1] if len(numbers) > 1 else numbers[0]


def _header_index(headers: list[str], names: tuple[str, ...]) -> int | None:
    for index, header in enumerate(headers):
        if any(name in header for name in names):
            return index
    return None


def _value_for(headers: list[str], values: list[str], names: tuple[str, ...]) -> str:
    index = _header_index(headers, names)
    return values[index] if index is not None and index < len(values) else ""


def _deduplicate_courses(courses: list[dict]) -> list[dict]:
    result = []
    seen = set()
    for course in courses:
        key = (
            course.get("course_name"),
            course.get("week_day"),
            course.get("start_section"),
            course.get("location"),
        )
        if key in seen:
            continue
        seen.add(key)
        result.append(course)
    return result


def _repair_text(value: str) -> str:
    """Repair common UTF-8-as-Latin-1 mojibake from WebView HTML dumps."""
    if value is None:
        return ""
    text = str(value)
    candidates = [text]
    for encoding in ("latin1", "cp1252"):
        try:
            candidates.append(text.encode(encoding).decode("utf-8"))
        except UnicodeError:
            pass

    def score(candidate: str) -> int:
        cjk = len(re.findall(r"[\u4e00-\u9fff]", candidate))
        useful = sum(word in candidate for word in ("教", "课程", "课表", "星期", "周", "节"))
        mojibake = len(re.findall(r"[æåèçð]|�", candidate))
        return cjk * 4 + useful * 3 - mojibake * 2

    return max(candidates, key=score)


def _html_diagnostics(html: str) -> dict:
    normalized_html = _normalize_import_html(html)
    soup = BeautifulSoup(normalized_html or "", "lxml")
    text = soup.get_text(" ", strip=True)
    markers = {
        "state_courses": "data-codex-state-courses" in normalized_html,
        "visual_courses": "data-codex-visual-courses" in normalized_html,
        "visual_headers": "data-codex-visual-headers" in normalized_html,
        "clickable_controls": "data-codex-clickable-controls" in normalized_html,
        "visible_text": "data-codex-visible-text" in normalized_html,
    }
    keywords = ["数据库基础", "软件工程", "智能芯片", "教-116", "教-117", "教-109", "课程", "课表"]
    keyword_hits = [word for word in keywords if word in normalized_html or word in text]
    snippets = []
    for word in keyword_hits[:5]:
        index = normalized_html.find(word)
        if index >= 0:
            start = max(index - 120, 0)
            end = min(index + 240, len(normalized_html))
            snippets.append(re.sub(r"\s+", " ", normalized_html[start:end])[:500])
    return {
        "length": len(html or ""),
        "normalized": normalized_html != str(html or ""),
        "normalized_length": len(normalized_html or ""),
        "table_count": len(soup.find_all("table")),
        "iframe_count": len(soup.find_all(["iframe", "frame"])),
        "pre_count": len(soup.find_all("pre")),
        "markers": markers,
        "keyword_hits": keyword_hits,
        "text_sample": text[:800],
        "snippets": snippets,
    }


def _looks_like_login_page(soup: BeautifulSoup, url: str) -> bool:
    if soup.find("input", attrs={"type": re.compile("password", re.I)}):
        return True
    title = soup.title.get_text(" ", strip=True) if soup.title else ""
    visible = soup.get_text(" ", strip=True)[:2000]
    path = urlparse(url).path.lower()
    content = f"{title} {visible}"
    if any(word in content for word in COURSE_LINK_WORDS):
        return False
    login_signal_count = sum(word in content for word in LOGIN_WORDS)
    return login_signal_count >= 2 or ("login" in path and login_signal_count >= 1)


def _parser_diagnostics(html: str) -> dict:
    normalized_html = _normalize_import_html(html)
    soup = BeautifulSoup(normalized_html or "", "lxml")
    state_courses = _extract_state_course_tables(soup)
    fullcalendar_courses = _extract_fullcalendar_events(soup)
    embedded_fullcalendar_courses = _extract_embedded_fullcalendar_events(normalized_html)
    embedded_fullcalendar_fragments = _embedded_fullcalendar_fragments(normalized_html)
    embedded_visual_courses = _extract_embedded_visual_course_tables(normalized_html)
    embedded_visual_tables = _embedded_codex_tables(
        normalized_html,
        ("data-codex-visual-courses", "data-codex-visual-headers"),
    )
    visual_courses = _extract_visual_course_tables(soup)
    column_courses = _extract_column_tables(soup)
    matrix_courses = _extract_matrix_tables(soup)
    fullcalendar_event_nodes = _fullcalendar_event_nodes(soup)
    return {
        "state_table_count": len(soup.find_all("table", attrs={"data-codex-state-courses": "true"})),
        "visual_table_count": len(soup.find_all("table", attrs={"data-codex-visual-courses": "true"})),
        "fc_event_count": len(fullcalendar_event_nodes),
        "fc_title_count": len(soup.select(".fc-event-title")),
        "raw_fc_title_count": len(re.findall(r"fc-event-title", html or "")),
        "raw_fc_time_count": len(re.findall(r"fc-event-time", html or "")),
        "normalized": normalized_html != str(html or ""),
        "normalized_fc_title_count": len(re.findall(r"fc-event-title", normalized_html or "")),
        "normalized_fc_time_count": len(re.findall(r"fc-event-time", normalized_html or "")),
        "embedded_fullcalendar_fragments": len(embedded_fullcalendar_fragments),
        "embedded_visual_table_count": len(embedded_visual_tables),
        "state_courses": len(state_courses),
        "fullcalendar_courses": len(fullcalendar_courses),
        "embedded_fullcalendar_courses": len(embedded_fullcalendar_courses),
        "embedded_visual_courses": len(embedded_visual_courses),
        "visual_courses": len(visual_courses),
        "column_courses": len(column_courses),
        "matrix_courses": len(matrix_courses),
        "valid_state_courses": len([course for course in state_courses if _is_valid_course(course)]),
        "valid_fullcalendar_courses": len([course for course in fullcalendar_courses if _is_valid_course(course)]),
        "valid_embedded_fullcalendar_courses": len([course for course in embedded_fullcalendar_courses if _is_valid_course(course)]),
        "valid_embedded_visual_courses": len([course for course in embedded_visual_courses if _is_valid_course(course)]),
        "valid_visual_courses": len([course for course in visual_courses if _is_valid_course(course)]),
        "valid_column_courses": len([course for course in column_courses if _is_valid_course(course)]),
        "valid_matrix_courses": len([course for course in matrix_courses if _is_valid_course(course)]),
    }


def _imported(courses: list[dict], menu_url: str, diagnostics: dict | None = None) -> dict:
    return {
        "status": "IMPORTED",
        "message": f"课表采集完成，共识别 {len(courses)} 门课程。",
        "courses": courses,
        "menu_url": menu_url,
        "diagnostics": diagnostics or {},
    }


async def _validate_public_url(url: str) -> None:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("只支持完整的 HTTP/HTTPS 网址")
    addresses = await _resolve_host(parsed.hostname, parsed.port or (443 if parsed.scheme == "https" else 80))
    for address in addresses:
        ip = ipaddress.ip_address(address)
        if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved or ip.is_multicast:
            raise ValueError("不允许采集本机或内网地址")


async def _validate_same_host(source_url: str, target_url: str) -> None:
    if urlparse(source_url).hostname != urlparse(target_url).hostname:
        raise ValueError("课表菜单跳转到了其他域名，已停止采集")
    await _validate_public_url(target_url)


async def _resolve_host(host: str, port: int) -> set[str]:
    import asyncio

    loop = asyncio.get_running_loop()
    try:
        infos = await loop.run_in_executor(
            None, socket.getaddrinfo, host, port, 0, socket.SOCK_STREAM
        )
    except OSError as exc:
        raise ValueError(f"无法解析网址域名：{host}") from exc
    return {info[4][0] for info in infos}


def _parse_time(value: str | None):
    if not value:
        return None
    try:
        return datetime.strptime(value, "%H:%M").time()
    except ValueError:
        return None


def _optional_int(value) -> int | None:
    try:
        return int(value) if value is not None else None
    except (TypeError, ValueError):
        return None
