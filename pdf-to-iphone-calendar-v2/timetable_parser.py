"""Geometry-aware parsing for text timetables. Never infer missing week/time data."""
from __future__ import annotations

import math
import re
import statistics
import unicodedata
from collections import defaultdict


class TimetableError(ValueError):
    """The input cannot be safely converted in full."""


def normalize(text):
    text = unicodedata.normalize("NFKC", text)
    return re.sub(r"\s+", "", text).translate(str.maketrans("－–—~～、", "-----,"))


def parse_weeks(spec):
    value = normalize(spec).replace("第", "").replace("单周", "单").replace("双周", "双")
    # A final qualifier applies to the entire comma-list, unless earlier items
    # explicitly carry their own 周/qualifier (13-15周(单),16周).
    global_parity = None
    match = re.fullmatch(r"([\d,\-]+)周?\(([单双])\)", value)
    if match:
        value, global_parity = match.groups()
    weeks = set()
    for token in value.split(","):
        match = re.fullmatch(r"(\d+)(?:-(\d+))?周?(?:\(([单双])\))?", token)
        if not match:
            raise TimetableError(f"无法完整识别周次：{spec}")
        lo, hi, parity = match.groups()
        lo, hi = int(lo), int(hi or lo)
        if not 1 <= lo <= hi <= 53:
            raise TimetableError(f"周次范围无效：{spec}")
        parity = parity or global_parity
        weeks.update(w for w in range(lo, hi + 1)
                     if parity is None or w % 2 == (1 if parity == "单" else 0))
    if not weeks:
        raise TimetableError(f"周次没有有效上课周：{spec}")
    return sorted(weeks)


def center(row):
    return row["x"] + row["width"] / 2, row["y"] + row["height"] / 2


def layouts(rows):
    pages = {r["page"]: r for r in rows if r["type"] == "page"}
    result = {}
    previous = None
    for page, info in sorted(pages.items()):
        headers = [r for r in rows if r["page"] == page and r["type"] == "weekday"]
        if not headers:
            shape = tuple(info[k] for k in ("width", "height", "rotation"))
            if previous is None or shape != previous["shape"]:
                raise TimetableError(f"第{page}页缺少星期表头，不能安全沿用上一页布局。")
            result[page] = dict(previous, header_v=None)
            continue
        by_day = {}
        for row in headers:
            day = "一二三四五六日".index(row["text"][-1].replace("天", "日"))
            if day in by_day:
                raise TimetableError(f"第{page}页有多组星期表头，暂不支持。")
            by_day[day] = row
        if set(by_day) != set(range(7)):
            raise TimetableError(f"第{page}页星期表头不完整（需要周一至周日）。")
        a, b = center(by_day[0]), center(by_day[6])
        dx, dy = b[0] - a[0], b[1] - a[1]
        length = math.hypot(dx, dy)
        if length <= 0:
            raise TimetableError("星期表头坐标无效。")
        dx, dy = dx / length, dy / length
        us = [center(by_day[d])[0] * dx + center(by_day[d])[1] * dy for d in range(7)]
        vs = [center(by_day[d])[0] * dy - center(by_day[d])[1] * dx for d in range(7)]
        gaps = [us[i + 1] - us[i] for i in range(6)]
        gap = statistics.median(gaps)
        if gap <= 0 or any(abs(g - gap) > gap * .15 for g in gaps) or max(vs) - min(vs) > gap * .1:
            raise TimetableError("星期列不规则或不是单行七列，暂不支持此布局。")
        bounds = [us[0] - gaps[0] / 2] + [(us[i] + us[i + 1]) / 2 for i in range(6)] + [us[6] + gaps[-1] / 2]
        previous = dict(dx=dx, dy=dy, bounds=bounds, header_v=statistics.mean(vs),
                        shape=tuple(info[k] for k in ("width", "height", "rotation")))
        result[page] = previous
    if not result:
        raise TimetableError("未读取到 PDF 页面信息。")
    return result


def project(row, layout):
    x, y = center(row)
    dx, dy = layout["dx"], layout["dy"]
    return x * dx + y * dy, x * dy - y * dx


def text_lines(chars, layout):
    """Rebuild lines by baseline, then reading order, independent of PDF object order."""
    if not chars:
        return []
    thickness = statistics.median(abs(layout["dy"]) * c["width"] + abs(layout["dx"]) * c["height"] for c in chars)
    tolerance = max(.1, thickness * .3)
    buckets = []
    for c in sorted(chars, key=lambda r: project(r, layout)[1]):
        u, v = project(c, layout)
        if not buckets or abs(v - buckets[-1][0]) > tolerance:
            buckets.append((v, []))
        buckets[-1][1].append((u, c["text"]))
    return [dict(v=v, text="".join(t for _, t in sorted(parts))) for v, parts in buckets]


META = re.compile(r"\((\d+)(?:-(\d+))?节\)([^/]+)(?:/|$)")


def parse_timetable(rows):
    maps = layouts(rows)
    groups = defaultdict(list)
    times = {}
    for page, layout in maps.items():
        chars = [r for r in rows if r["type"] == "char" and r["page"] == page]
        if not chars:
            raise TimetableError(f"第{page}页没有可提取文字；扫描件不支持自动识别。")
        cells = defaultdict(list)
        for c in chars:
            u, v = project(c, layout)
            if layout["header_v"] is not None and v <= layout["header_v"] + 1:
                continue
            bounds = layout["bounds"]
            if u < bounds[0]:
                cells[-1].append(c)
            elif u < bounds[-1]:
                day = next(i for i in range(7) if u < bounds[i + 1])
                cells[day].append(c)
            elif c["text"] in "◇◆节":
                raise TimetableError(f"第{page}页星期列之外发现课程标记，请检查版式。")
        for day in range(7):
            lines = text_lines(cells[day], layout)
            # Repeated footer legends are not course records.
            lines = [r for r in lines if not re.search(r"[◇◆][:：]", r["text"])]
            groups[day].extend(lines)
        # Period sidebar contains labels and two clocks in reading order.
        sidebar = text_lines(cells[-1], layout)
        pending = None
        clocks = []
        for line in sidebar:
            value = normalize(line["text"])
            number = re.fullmatch(r"(?:第)?(\d{1,2})(?:节)?", value)
            if number:
                pending, clocks = int(number[1]), []
            else:
                clocks.extend(re.findall(r"(?<!\d)(\d{2}:\d{2})(?!\d)", value))
                if pending is not None and len(clocks) >= 2:
                    pair = tuple(clocks[:2])
                    if pending in times and times[pending] != pair:
                        raise TimetableError(f"第{pending}节有相互冲突的上课时间。")
                    times[pending] = pair
                    pending, clocks = None, []
    courses = []
    for day, lines in sorted(groups.items()):
        # Course titles may span lines. Metadata and remaining slash fields are
        # consumed up to the next title; no fixed font size or coordinate needed.
        texts = [normalize(r["text"]) for r in lines]
        joined = "\n".join(texts)
        # A title begins after the previous metadata's final line; icon-only
        # lines are retained as part of the preceding wrapped title.
        starts = []
        for i, text in enumerate(texts):
            if "◇" in text or "◆" in text:
                start = i
                while start > 0:
                    prev = texts[start - 1]
                    if re.search(r"[/:◇◆]", prev):
                        break
                    start -= 1
                starts.append(start)
        if len(starts) != len(set(starts)):
            raise TimetableError(f"星期{day + 1}的课程标题边界不明确。")
        if not starts:
            if re.search(r"节|校区:|场地:", joined):
                raise TimetableError(f"星期{day + 1}存在无法归属的课程（需要◇/◆课程标记）。")
            continue
        if re.search(r"节|校区:|场地:", "".join(texts[:starts[0]])):
            raise TimetableError(f"星期{day + 1}有未识别的前置课程内容。")
        for index, start in enumerate(starts):
            end = starts[index + 1] if index + 1 < len(starts) else len(texts)
            raw = "".join(texts[start:end])
            icon = re.search(r"[◇◆]", raw)
            matches = list(META.finditer(raw))
            if len(matches) != 1 or len(re.findall(r"\([^()]*节\)", raw)) != 1 or not icon:
                raise TimetableError(f"星期{day + 1}课程未完整识别：{raw[:90]}")
            meta = matches[0]
            title = raw[:icon.start()]
            if not title or meta.start() != icon.end():
                raise TimetableError(f"标题与节次之间有未识别内容：{raw[:90]}")
            first, last = int(meta[1]), int(meta[2] or meta[1])
            if not 1 <= first <= last <= 30:
                raise TimetableError(f"课程节次无效：{title}")
            def field(name):
                m = re.search(r"(?:/|^)" + name + r":([^/]*)", raw)
                return m[1] if m else ""
            courses.append(dict(name=title, weekday=day, periods=(first, last),
                                weeks=parse_weeks(meta[3]), week_spec=meta[3],
                                campus=field("校区"), place=field("场地"), teacher=field("教师"),
                                kind="讲课" if icon[0] == "◇" else "实验/实践"))
    if not courses:
        raise TimetableError("没有识别到课程；需要带◇/◆、节次和周次的文本型教务课表。")
    return courses, times
