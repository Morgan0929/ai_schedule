import asyncio
import sys
import unittest
from datetime import date
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from bs4 import BeautifulSoup

from crawler_service.services.schedule_import_service import (
    _parser_diagnostics,
    _validate_public_url,
    extract_courses_from_html,
    find_schedule_links,
    import_schedule_html,
)
from timeline_service.models.schedule_model import SEMESTER_FALL, get_semester_week


COURSE = "\u6570\u636e\u5e93\u57fa\u7840"
COURSE_2 = "\u8f6f\u4ef6\u5de5\u7a0b"
MATH = "\u9ad8\u7b49\u6570\u5b66"
TEACHER = "\u5de6\u4e9a\u5c0f"
TEACHER_2 = "\u5f20\u8001\u5e08"
ROOM = "A116"
ROOM_2 = "A117"


class ScheduleImportTest(unittest.TestCase):
    def test_finds_schedule_menu_link(self):
        html = '<nav><a href="/student/schedule">\u6211\u7684\u8bfe\u8868</a></nav>'
        soup = BeautifulSoup(html, "lxml")

        links = find_schedule_links(soup, "https://example.edu.cn/home")

        self.assertEqual(links, ["https://example.edu.cn/student/schedule"])

    def test_extracts_column_schedule_table(self):
        html = f"""
        <table>
          <tr><th>\u8bfe\u7a0b\u540d\u79f0</th><th>\u6559\u5e08</th><th>\u661f\u671f</th><th>\u8282\u6b21</th><th>\u5468\u6b21</th><th>\u6559\u5ba4</th></tr>
          <tr><td>{MATH}</td><td>\u6797\u8001\u5e08</td><td>\u661f\u671f\u4e00</td><td>1-2\u8282</td><td>1-16\u5468</td><td>A301</td></tr>
        </table>
        """

        courses = extract_courses_from_html(html)

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["course_name"], MATH)
        self.assertEqual(courses[0]["teacher"], "\u6797\u8001\u5e08")
        self.assertEqual(courses[0]["location"], "A301")
        self.assertEqual(courses[0]["week_day"], 1)
        self.assertEqual(courses[0]["start_section"], 1)
        self.assertEqual(courses[0]["end_section"], 2)
        self.assertEqual(courses[0]["start_week"], 1)
        self.assertEqual(courses[0]["end_week"], 16)

    def test_rejects_local_urls(self):
        with self.assertRaises(ValueError):
            asyncio.run(_validate_public_url("http://127.0.0.1:8000/health"))

    def test_imports_webview_matrix_html(self):
        html = f"""
        <table>
          <tr><th></th><th>\u4e00</th><th>\u4e8c</th><th>\u4e09</th><th>\u56db</th></tr>
          <tr><td>1-2</td><td></td><td></td><td>{COURSE}<br>{ROOM}</td><td>{COURSE_2}<br>{ROOM_2}</td></tr>
        </table>
        """

        result = import_schedule_html(html, "https://jxfw.gdut.edu.cn/login!welcome.action")

        self.assertEqual(result["status"], "IMPORTED")
        self.assertEqual(len(result["courses"]), 2)
        self.assertEqual(result["courses"][0]["course_name"], COURSE)
        self.assertEqual(result["courses"][0]["location"], ROOM)
        self.assertEqual(result["courses"][0]["week_day"], 3)

    def test_extracts_visual_cards_with_header_weekday_mapping(self):
        html = f"""
        <table data-codex-visual-headers="true">
          <tr><th>top</th><th>left</th><th>width</th><th>height</th><th>text</th></tr>
          <tr><td>280</td><td>190</td><td>140</td><td>24</td><td>\u4e09 9/2</td></tr>
          <tr><td>280</td><td>338</td><td>140</td><td>24</td><td>\u56db 9/3</td></tr>
        </table>
        <table data-codex-visual-courses="true">
          <tr><th>top</th><th>left</th><th>width</th><th>height</th><th>course</th></tr>
          <tr><td>388</td><td>191</td><td>140</td><td>80</td><td>{COURSE}\n{TEACHER}\n{ROOM}</td></tr>
          <tr><td>508</td><td>339</td><td>140</td><td>80</td><td>{COURSE_2}\n{TEACHER_2}\n{ROOM_2}</td></tr>
        </table>
        """

        courses = extract_courses_from_html(html)

        self.assertEqual(len(courses), 2)
        self.assertEqual(courses[0]["course_name"], COURSE)
        self.assertEqual(courses[0]["week_day"], 3)
        self.assertEqual(courses[0]["start_section"], 1)
        self.assertEqual(courses[1]["course_name"], COURSE_2)
        self.assertEqual(courses[1]["week_day"], 4)
        self.assertEqual(courses[1]["start_section"], 3)

    def test_extracts_visual_cards_from_embedded_html_text(self):
        html = f'''
        <script type="text/plain">
          <table data-codex-visual-headers="true">
            <tr><th>top</th><th>left</th><th>width</th><th>height</th><th>text</th></tr>
            <tr><td>280</td><td>190</td><td>140</td><td>24</td><td>\u4e09 9/2</td></tr>
            <tr><td>280</td><td>338</td><td>140</td><td>24</td><td>\u56db 9/3</td></tr>
          </table>
          <table data-codex-visual-courses="true">
            <tr><th>top</th><th>left</th><th>width</th><th>height</th><th>course</th></tr>
            <tr><td>388</td><td>191</td><td>140</td><td>80</td><td>{COURSE}\n{TEACHER}\n{ROOM}</td></tr>
            <tr><td>508</td><td>339</td><td>140</td><td>80</td><td>{COURSE_2}\n{TEACHER_2}\n{ROOM_2}</td></tr>
          </table>
        </script>
        '''

        courses = extract_courses_from_html(html)
        diagnostics = _parser_diagnostics(html)

        self.assertEqual(len(courses), 2)
        self.assertEqual(courses[0]["week_day"], 3)
        self.assertEqual(courses[1]["week_day"], 4)
        self.assertEqual(diagnostics["embedded_visual_table_count"], 2)
        self.assertEqual(diagnostics["valid_embedded_visual_courses"], 2)

    def test_extracts_state_courses_before_visual_or_hidden_tables(self):
        html = f"""
        <table>
          <tr><th></th><th>\u4e09</th></tr>
          <tr><td>1-2</td><td>\u9690\u85cf\u8bfe\u7a0b<br>A999</td></tr>
        </table>
        <table data-codex-state-courses="true">
          <tr><th>\u8bfe\u7a0b\u540d\u79f0</th><th>\u6559\u5e08</th><th>\u661f\u671f</th><th>\u8282\u6b21</th><th>\u5468\u6b21</th><th>\u6559\u5ba4</th><th>source</th></tr>
          <tr><td>{COURSE}</td><td>{TEACHER}</td><td>3</td><td>1-2</td><td>1-13</td><td>{ROOM}</td><td>network</td></tr>
        </table>
        <table data-codex-visual-courses="true">
          <tr><th>top</th><th>left</th><th>width</th><th>height</th><th>course</th></tr>
          <tr><td>388</td><td>191</td><td>140</td><td>80</td><td>{COURSE_2}\n{ROOM_2}</td></tr>
        </table>
        """

        courses = extract_courses_from_html(html)

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["course_name"], COURSE)
        self.assertEqual(courses[0]["teacher"], TEACHER)
        self.assertEqual(courses[0]["week_day"], 3)
        self.assertEqual(courses[0]["end_week"], 13)

    def test_extracts_fullcalendar_event_courses(self):
        html = f"""
        <div class="fc-event" style="left: 200px; top: 90px;">
          <div class="fc-event-inner">
            <div class="fc-event-time" style="display: none;">01 - 03</div>
            <div class="fc-event-title">
              <div>{COURSE}</div>
              <div>{ROOM}</div>
            </div>
          </div>
        </div>
        """

        courses = extract_courses_from_html(html)

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["course_name"], COURSE)
        self.assertEqual(courses[0]["location"], ROOM)
        self.assertEqual(courses[0]["start_section"], 1)
        self.assertEqual(courses[0]["end_section"], 3)

    def test_extracts_fullcalendar_event_courses_from_escaped_attributes(self):
        html = r'''
        <div class=\"fc-event\" style=\"left: 200px; top: 90px;\">
          <div class=\"fc-event-inner\">
            <div class=\"fc-event-time\" style=\"display: none;\">01 - 03</div>
            <div class=\"fc-event-title\">
              <div>__COURSE__</div>
              <div>__ROOM__</div>
            </div>
          </div>
        </div>
        '''.replace("__COURSE__", COURSE).replace("__ROOM__", ROOM)

        courses = extract_courses_from_html(html)
        diagnostics = _parser_diagnostics(html)

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["course_name"], COURSE)
        self.assertEqual(courses[0]["location"], ROOM)
        self.assertEqual(courses[0]["start_section"], 1)
        self.assertEqual(courses[0]["end_section"], 3)
        self.assertTrue(diagnostics["normalized"])
        self.assertEqual(diagnostics["fc_title_count"], 1)
        self.assertEqual(diagnostics["valid_fullcalendar_courses"], 1)

    def test_extracts_fullcalendar_event_courses_from_embedded_html_text(self):
        html = f'''
        <html><body>
          <script type="text/plain">
            <div class="fc-event" style="left: 200px; top: 90px;">
              <div class="fc-event-inner">
                <div class="fc-event-time" style="display: none;">01 - 03</div>
                <div class="fc-event-title"><div>{COURSE}</div><div>{ROOM}</div></div>
              </div>
            </div>
          </script>
        </body></html>
        '''

        courses = extract_courses_from_html(html)
        diagnostics = _parser_diagnostics(html)

        self.assertEqual(len(courses), 1)
        self.assertEqual(courses[0]["course_name"], COURSE)
        self.assertEqual(courses[0]["location"], ROOM)
        self.assertEqual(diagnostics["fc_title_count"], 0)
        self.assertEqual(diagnostics["embedded_fullcalendar_fragments"], 1)
        self.assertEqual(diagnostics["valid_embedded_fullcalendar_courses"], 1)

    def test_embedded_fullcalendar_preserves_relative_day_and_sections(self):
        html = f'''
        <script type="text/plain">
          <div class="fc-event" style="left: 100px; top: 90px;">
            <div class="fc-event-inner">
              <div class="fc-event-time">01 - 03</div>
              <div class="fc-event-title"><div>{COURSE}</div><div>{ROOM}</div></div>
            </div>
          </div>
          <div class="fc-event" style="left: 250px; top: 180px;">
            <div class="fc-event-inner">
              <div class="fc-event-time">03 - 05</div>
              <div class="fc-event-title"><div>{COURSE_2}</div><div>{ROOM_2}</div></div>
            </div>
          </div>
        </script>
        '''

        courses = extract_courses_from_html(html)

        self.assertEqual(len(courses), 2)
        self.assertEqual(courses[0]["course_name"], COURSE)
        self.assertEqual(courses[0]["week_day"], 1)
        self.assertEqual(courses[0]["start_section"], 1)
        self.assertEqual(courses[0]["end_section"], 3)
        self.assertEqual(courses[1]["course_name"], COURSE_2)
        self.assertEqual(courses[1]["week_day"], 2)
        self.assertEqual(courses[1]["start_section"], 3)
        self.assertEqual(courses[1]["end_section"], 5)

    def test_fall_semester_week_filters_before_first_week(self):
        semester = f"2026\u5e74{SEMESTER_FALL}"

        self.assertIsNone(get_semester_week(date(2026, 8, 13), semester))
        self.assertEqual(get_semester_week(date(2026, 8, 31), semester), 1)
        self.assertEqual(get_semester_week(date(2026, 9, 6), semester), 1)
        self.assertEqual(get_semester_week(date(2026, 9, 7), semester), 2)


if __name__ == "__main__":
    unittest.main()
