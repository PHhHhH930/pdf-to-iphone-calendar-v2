"""Real PDF → native extractor → parser → ICS tests (macOS only)."""
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from datetime import date

from pdf_to_iphone_calendar import extract_pdf_lines, add_locations, build_ics
from timetable_parser import parse_timetable

ROOT = Path(__file__).resolve().parents[1]


@unittest.skipUnless(sys.platform == "darwin", "PDFKit requires macOS")
class NativePDFTests(unittest.TestCase):
    def test_real_pdfs(self):
        fixtures = sorted((ROOT / "tests" / "fixtures").glob("*.pdf"))
        self.assertEqual(len(fixtures), 4, "Missing anonymous integration PDFs")
        for path in fixtures:
            with self.subTest(path=path.name):
                courses, times = parse_timetable(extract_pdf_lines(path))
                self.assertEqual(len(courses), 7)
                self.assertEqual([c["name"] for c in courses], [f"2026测试课程{d}节能原理" for d in range(7)])
                self.assertEqual([c["weekday"] for c in courses], list(range(7)))
                self.assertTrue(all(c["weeks"] == [3,5,7] for c in courses))
                self.assertTrue(all(c["place"] == "09-0102" for c in courses))
                self.assertTrue(all(c["teacher"] == "测试教师" for c in courses))
                self.assertEqual(times, {1:("08:10","08:55"),2:("09:05","09:50")})
                ics, count = build_ics(add_locations(courses,"西南大学",""), date(2026,8,31),
                                       "匿名课表", path, 8, None, None, times)
                self.assertEqual(count, 21)
                self.assertIn("DTSTART:20260914T001000Z", ics)

    def test_cli_and_overwrite_protection(self):
        source = ROOT / "tests" / "fixtures" / "anonymous-normal.pdf"
        with tempfile.TemporaryDirectory() as temporary:
            target = Path(temporary) / "result.ics"
            cmd = [sys.executable, str(ROOT / "pdf_to_iphone_calendar.py"), str(source),
                   "--week1", "2026-08-31", "-o", str(target)]
            first = subprocess.run(cmd, capture_output=True, text=True)
            self.assertEqual(first.returncode, 0, first.stderr)
            before = target.read_bytes()
            second = subprocess.run(cmd, capture_output=True, text=True)
            self.assertNotEqual(second.returncode, 0)
            self.assertIn("已存在", second.stderr)
            self.assertEqual(before, target.read_bytes())
            self.assertEqual(subprocess.run(cmd + ["--force"], capture_output=True).returncode, 0)

    def test_pdf_cannot_be_output(self):
        source = ROOT / "tests" / "fixtures" / "anonymous-normal.pdf"
        before = source.read_bytes()
        result = subprocess.run([sys.executable, str(ROOT / "pdf_to_iphone_calendar.py"), str(source),
                                 "--week1", "2026-08-31", "-o", str(source), "--force"], capture_output=True)
        self.assertNotEqual(result.returncode, 0)
        self.assertEqual(source.read_bytes(), before)
