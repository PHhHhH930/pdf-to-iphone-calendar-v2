import copy
import random
import unittest
from datetime import date
from pathlib import Path

from factories import fixture_rows
from timetable_parser import TimetableError, parse_timetable, parse_weeks
from pdf_to_iphone_calendar import add_locations, build_ics, escape_ics, format_location, validate_times


class WeekParsingTests(unittest.TestCase):
    def test_supported_specs(self):
        examples = {"1-12周": list(range(1,13)), "13-15周(单),16周": [13,15,16],
                    "第11周": [11], "2-8周(单)": [3,5,7], "1-8周(双)": [2,4,6,8],
                    "第１－８周（双周）": [2,4,6,8], "1、3、5周": [1,3,5],
                    "1-4,7-8周": [1,2,3,4,7,8], "1,2,3周(单)": [1,3]}
        for spec, expected in examples.items():
            with self.subTest(spec=spec):
                self.assertEqual(parse_weeks(spec), expected)

    def test_invalid_specs_fail_instead_of_partial_success(self):
        for spec in ["", "0周", "8-2周", "1-54周", "1-8周(未知)", "1周,待定", "1-8周除3周", "2周(单)"]:
            with self.subTest(spec=spec), self.assertRaises(TimetableError):
                parse_weeks(spec)


class LayoutTests(unittest.TestCase):
    def test_varied_scale_offset_orientation_and_object_order(self):
        for scale in [.6, 1, 1.7]:
            for angle in [0, 90, 180, 270]:
                with self.subTest(scale=scale, angle=angle):
                    rows = fixture_rows(scale, angle, 75)
                    random.Random(42).shuffle(rows)
                    courses, times = parse_timetable(rows)
                    self.assertEqual(len(courses), 7)
                    self.assertEqual([c["weekday"] for c in courses], list(range(7)))
                    self.assertTrue(all(c["weeks"] == [3,5,7] for c in courses))
                    self.assertEqual(courses[0]["name"], "2026测试课程0节能原理")
                    self.assertEqual(courses[6]["place"], "09-0102")
                    self.assertEqual(times, {1:("08:10","08:55"),2:("09:05","09:50")})

    def test_missing_day_fails(self):
        rows = [r for r in fixture_rows() if not (r["type"] == "weekday" and r["text"] == "星期三")]
        with self.assertRaisesRegex(TimetableError, "表头不完整"):
            parse_timetable(rows)

    def test_no_header_fails(self):
        with self.assertRaisesRegex(TimetableError, "缺少星期表头"):
            parse_timetable(fixture_rows(headers=False))

    def test_blank_or_scanned_page_fails(self):
        with self.assertRaisesRegex(TimetableError, "没有可提取文字"):
            parse_timetable([r for r in fixture_rows() if r["type"] != "char"])

    def test_invalid_course_stops_whole_file(self):
        rows = fixture_rows()
        for r in rows:
            if r["type"] == "char" and r["text"] == "单":
                r["text"] = "错"
                break
        with self.assertRaisesRegex(TimetableError, "周次"):
            parse_timetable(rows)

    def test_missing_icon_stops_whole_file(self):
        rows = fixture_rows()
        for r in rows:
            if r["text"] == "◇":
                r["text"] = ""
                break
        with self.assertRaisesRegex(TimetableError, "无法归属"):
            parse_timetable(rows)

    def test_changed_continuation_geometry_rejected(self):
        rows = fixture_rows() + fixture_rows(scale=2, page=2, headers=False)
        with self.assertRaisesRegex(TimetableError, "不能安全沿用"):
            parse_timetable(rows)

    def test_repeated_header_page(self):
        courses, _ = parse_timetable(fixture_rows() + fixture_rows(scale=.8, page=2))
        self.assertEqual(len(courses), 14)


class CalendarTests(unittest.TestCase):
    def setUp(self):
        self.courses, self.times = parse_timetable(fixture_rows())
        self.courses = add_locations(self.courses, "西南大学", "重庆市北碚区天生路2号")

    def export(self, courses=None, start=date(2026,8,31), path="one.pdf", times=None):
        return build_ics(self.courses if courses is None else courses, start, "测试课表",
                         Path(path), 8, 29.82324, 106.41835,
                         self.times if times is None else times)

    def test_calendar_bytes_dates_locations(self):
        ics, count = self.export()
        self.assertEqual(count, 21)
        self.assertIn("DTSTART:20260914T001000Z", ics)
        self.assertIn("DTEND:20260914T015000Z", ics)
        unfolded = ics.replace("\r\n ", "")
        self.assertIn("LOCATION:西南大学南区第9教学楼0102教室", unfolded)
        self.assertTrue(ics.endswith("END:VCALENDAR\r\n"))
        self.assertTrue(all(len(l.encode()) <= 75 for l in ics.split("\r\n")))
        self.assertNotIn("\n", ics.replace("\r\n", ""))

    def test_uid_stable_across_path_and_order_but_not_semester(self):
        def ids(result):
            return {l for l in result[0].splitlines() if l.startswith("UID:")}
        self.assertEqual(ids(self.export()), ids(self.export(list(reversed(self.courses)), path="moved.pdf")))
        self.assertTrue(ids(self.export()).isdisjoint(ids(self.export(start=date(2027,8,30)))))

    def test_identical_events_deduplicated(self):
        self.assertEqual(self.export(self.courses * 2)[1], 21)

    def test_missing_period_times_fail(self):
        with self.assertRaisesRegex(TimetableError, "缺少"):
            self.export(times={1:self.times[1]})

    def test_invalid_course_fields_fail(self):
        for field, value in [("weeks", [0]), ("weeks", []), ("weekday", 7), ("periods", (2,1))]:
            c = copy.deepcopy(self.courses)
            c[0][field] = value
            with self.subTest(field=field, value=value), self.assertRaises(TimetableError):
                self.export(c)

    def test_invalid_time_tables_fail(self):
        for times in [{1:["08:50","08:00"]}, {1:["25:00","25:45"]}, {1:["08:00","09:00"],2:["08:50","10:00"]}]:
            with self.subTest(times=times), self.assertRaises(TimetableError):
                validate_times(times)

    def test_escape(self):
        self.assertEqual(escape_ics("a,b;c\\d\r\ne\rf"), "a\\,b\\;c\\\\d\\ne\\nf")

    def test_monday_required(self):
        with self.assertRaisesRegex(TimetableError, "周一"):
            self.export(start=date(2026,9,1))

    def test_location_unknown_and_ground(self):
        self.assertEqual(format_location("西南大学","北区","未排地点",""), "西南大学北区（地点待定）")
        self.assertEqual(format_location("西南大学","南","第一运动场",""), "西南大学南区第一运动场")


if __name__ == "__main__":
    unittest.main()
