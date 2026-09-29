#!/usr/bin/env python3
"""Local macOS text timetable PDF to iCalendar converter."""
from __future__ import annotations

import argparse
import hashlib
import json
import re
import shutil
import subprocess
import sys
import tempfile
from datetime import date, datetime, timedelta, timezone
from pathlib import Path

from timetable_parser import TimetableError, parse_timetable, parse_weeks

DEFAULT_CAMPUS_LAT = 29.82324
DEFAULT_CAMPUS_LON = 106.41835


def ensure_pdfkit_helper():
    if sys.platform != "darwin":
        raise TimetableError("PDF 识别目前需要 macOS；Windows/Linux 尚未支持。")
    source = Path(__file__).resolve().with_name("pdfkit_lines.m")
    if not source.is_file():
        raise TimetableError("程序旁边缺少 pdfkit_lines.m。")
    # Private cache with content-versioned binary; independent of file timestamps.
    cache = Path(tempfile.gettempdir()) / ("timetable-pdfkit-" + str(__import__("os").getuid()))
    cache.mkdir(mode=0o700, exist_ok=True)
    version = hashlib.sha256(source.read_bytes()).hexdigest()[:16]
    helper = cache / version
    if not helper.exists():
        clang = shutil.which("clang")
        if not clang:
            raise TimetableError("请先安装 Xcode Command Line Tools（xcode-select --install）。")
        with tempfile.TemporaryDirectory(dir=cache) as build:
            binary = Path(build) / "pdfkit"
            try:
                subprocess.run([clang, "-framework", "Foundation", "-framework", "PDFKit",
                                str(source), "-o", str(binary)], check=True,
                               capture_output=True, text=True, timeout=90)
            except subprocess.CalledProcessError as error:
                raise TimetableError("无法编译 PDF 识别组件：" + error.stderr.strip()) from error
            binary.replace(helper)
    return helper


def extract_pdf_lines(pdf_path):
    helper = ensure_pdfkit_helper()
    try:
        result = subprocess.run([str(helper), str(pdf_path)], check=True,
                                capture_output=True, text=True, timeout=90)
    except subprocess.CalledProcessError as error:
        raise TimetableError("读取 PDF 失败（可能加密或损坏）：" + error.stderr.strip()) from error
    try:
        return [json.loads(line) for line in result.stdout.splitlines() if line.strip()]
    except json.JSONDecodeError as error:
        raise TimetableError("PDF 提取结果损坏，已停止转换。") from error


def format_location(university, campus_area, raw_place, campus_address):
    area = campus_area.strip()
    if area in {"南", "北"}:
        area += "区"
    prefix = university.strip() + area
    place = raw_place.strip()
    if not place or "未排" in place or "待定" in place:
        detail = "（地点待定）"
    else:
        match = re.fullmatch(r"\s*0*(\d+)\s*[-－–—]\s*(\d+)\s*", place)
        detail = "第{}教学楼{}教室".format(int(match[1]), match[2]) if match else place
    return prefix + detail + ("，" + campus_address.strip() if campus_address.strip() else "")


def parse_course_blocks(rows, university="西南大学", campus_address="重庆市北碚区天生路2号"):
    courses, _ = parse_timetable(rows)
    return add_locations(courses, university, campus_address)


def add_locations(courses, university, campus_address):
    return [dict(c, location=format_location(university, c["campus"], c["place"], campus_address)) for c in courses]


def validate_times(times):
    validated = {}
    for period, clocks in times.items():
        try:
            period = int(period)
            if not isinstance(clocks, (list, tuple)) or len(clocks) != 2:
                raise ValueError
            start, end = [datetime.strptime(c, "%H:%M").time() for c in clocks]
            if not 1 <= period <= 30 or start >= end:
                raise ValueError
        except (TypeError, ValueError):
            raise TimetableError(f"第{period}节时间无效：{clocks}") from None
        validated[period] = (start.strftime("%H:%M"), end.strftime("%H:%M"))
    ordered = sorted(validated)
    for a, b in zip(ordered, ordered[1:]):
        if validated[a][1] > validated[b][0]:
            raise TimetableError(f"第{a}节与第{b}节的时间重叠或顺序错误。")
    return validated


def escape_ics(value):
    return value.replace("\\", "\\\\").replace(";", "\\;").replace(",", "\\,").replace("\r\n", "\n").replace("\r", "\n").replace("\n", "\\n")


def fold_ics_line(line):
    chunks, part, size = [], "", 0
    for char in line:
        width = len(char.encode("utf-8"))
        limit = 75 if not chunks else 74
        if size + width > limit:
            chunks.append(part)
            part, size = "", 0
        part += char
        size += width
    chunks.append(part)
    return "\r\n ".join(chunks)


def to_utc_stamp(day, clock, utc_offset_hours):
    local = datetime.combine(day, datetime.strptime(clock, "%H:%M").time())
    return local.replace(tzinfo=timezone(timedelta(hours=utc_offset_hours))).astimezone(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def build_ics(courses, week1, calendar_name, source_path, utc_offset_hours,
              campus_lat, campus_lon, period_times):
    # source_path is retained for API compatibility, but never enters the UID.
    if week1.weekday() != 0:
        raise TimetableError("第一周日期必须是周一。")
    if not -12 <= utc_offset_hours <= 14:
        raise TimetableError("UTC 时差应在 -12 至 +14 小时之间。")
    if (campus_lat is None) != (campus_lon is None):
        raise TimetableError("经纬度必须一起填写。")
    if campus_lat is not None and not (-90 <= campus_lat <= 90 and -180 <= campus_lon <= 180):
        raise TimetableError("校区经纬度超出有效范围。")
    times = validate_times(period_times)
    stamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    lines = ["BEGIN:VCALENDAR", "VERSION:2.0", "PRODID:-//PDF to iPhone Calendar//CN",
             "CALSCALE:GREGORIAN", "X-WR-CALNAME:" + escape_ics(calendar_name)]
    seen = set()
    for course in courses:
        first, last = course["periods"]
        if not 1 <= first <= last <= 30 or not 0 <= course["weekday"] <= 6 or not course["weeks"]:
            raise TimetableError("课程节次、星期或周次无效。")
        missing = set(range(first, last + 1)) - times.keys()
        if missing:
            raise TimetableError(f"{course['name']}缺少第{sorted(missing)}节的时间，请提供 --period-times JSON。")
        for week in course["weeks"]:
            if not isinstance(week, int) or not 1 <= week <= 53:
                raise TimetableError("周次必须在 1 至 53 之间。")
            event_day = week1 + timedelta(days=(week - 1) * 7 + course["weekday"])
            start = to_utc_stamp(event_day, times[first][0], utc_offset_hours)
            end = to_utc_stamp(event_day, times[last][1], utc_offset_hours)
            identity = [week1.isoformat(), course["name"], course["weekday"], first, last,
                        week, course["location"], course["teacher"], course["kind"], start, end]
            uid = hashlib.sha256(json.dumps(identity, ensure_ascii=False).encode()).hexdigest()[:32] + "@pdf-to-iphone-calendar.local"
            if uid in seen:
                continue
            seen.add(uid)
            description = f"第{week}周；第{first}-{last}节；{course['kind']}；教师：{course['teacher']}；原课表周次：{course['week_spec']}"
            lines.extend(["BEGIN:VEVENT", "UID:" + uid, "DTSTAMP:" + stamp, "DTSTART:" + start,
                          "DTEND:" + end, "SUMMARY:" + escape_ics(course["name"]),
                          "LOCATION:" + escape_ics(course["location"])])
            if campus_lat is not None:
                lines.append(f"GEO:{campus_lat:.5f};{campus_lon:.5f}")
            lines.extend(["DESCRIPTION:" + escape_ics(description), "END:VEVENT"])
    if not seen:
        raise TimetableError("没有日程，未生成空日历。")
    lines.append("END:VCALENDAR")
    return "\r\n".join(fold_ics_line(line) for line in lines) + "\r\n", len(seen)


def parse_args():
    parser = argparse.ArgumentParser(description="本地识别文本型教务课表 PDF，导出 Apple 日历 ICS。")
    parser.add_argument("pdf", type=Path)
    parser.add_argument("--week1", required=True, type=date.fromisoformat, help="第1周周一 YYYY-MM-DD")
    parser.add_argument("-o", "--output", type=Path)
    parser.add_argument("--force", action="store_true", help="允许覆盖已有 ICS")
    parser.add_argument("--period-times", type=Path, help='显式时间表 JSON，例如 {"1":["08:00","08:45"]}')
    parser.add_argument("--calendar-name", default="课程表")
    parser.add_argument("--university", default="西南大学")
    parser.add_argument("--campus-address")
    parser.add_argument("--campus-lat", type=float)
    parser.add_argument("--campus-lon", type=float)
    parser.add_argument("--utc-offset", type=int, default=8)
    return parser.parse_args()


def main():
    args = parse_args()
    try:
        pdf_path = args.pdf.expanduser().resolve()
        if not pdf_path.is_file() or pdf_path.suffix.lower() != ".pdf":
            raise TimetableError("输入必须是现有的 PDF 文件。")
        if args.week1.weekday() != 0:
            raise TimetableError("--week1 必须填写第一周的周一。")
        output = (args.output or pdf_path.with_suffix(".ics")).expanduser().resolve()
        if output.suffix.lower() != ".ics" or output == pdf_path:
            raise TimetableError("输出必须为独立的 .ics 文件，不能覆盖 PDF。")
        if output.exists() and not args.force:
            raise TimetableError("输出文件已存在；请换名或使用 --force。")
        rows = extract_pdf_lines(pdf_path)
        courses, times = parse_timetable(rows)
        if args.period_times:
            times = json.loads(args.period_times.expanduser().read_text(encoding="utf-8"))
            if not isinstance(times, dict):
                raise TimetableError("时间表 JSON 必须是节次到起止时间的对象。")
        address = args.campus_address
        lat, lon = args.campus_lat, args.campus_lon
        if args.university == "西南大学":
            address = "重庆市北碚区天生路2号" if address is None else address
            if lat is None and lon is None:
                lat, lon = DEFAULT_CAMPUS_LAT, DEFAULT_CAMPUS_LON
        courses = add_locations(courses, args.university, address or "")
        ics, count = build_ics(courses, args.week1, args.calendar_name, pdf_path,
                               args.utc_offset, lat, lon, times)
        output.parent.mkdir(parents=True, exist_ok=True)
        # Exclusive creation protects existing files unless overwrite was explicit.
        with output.open("wb" if args.force else "xb") as stream:
            stream.write(ics.encode("utf-8"))
        print(f"识别到 {len(courses)} 个课程时段，生成 {count} 条日历日程。")
        for c in courses:
            print(f"  星期{'一二三四五六日'[c['weekday']]} 第{c['periods'][0]}-{c['periods'][1]}节 {c['name']}（{c['week_spec']}）")
        print(f"日历文件：{output}")
        print("请先核对课程清单。未自动处理假期调课；导入 iCloud 日历后才能同步 iPhone。")
    except (TimetableError, OSError, ValueError, subprocess.TimeoutExpired) as error:
        raise SystemExit("错误：" + str(error)) from None


if __name__ == "__main__":
    main()
