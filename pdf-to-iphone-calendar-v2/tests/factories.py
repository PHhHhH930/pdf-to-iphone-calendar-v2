"""Entirely fictional timetable fixtures; no student data."""
import math


def fixture_rows(scale=1, angle=0, offset=0, page=1, headers=True):
    rows = [dict(type="page", page=page, x=0, y=0, width=1000, height=1000, rotation=0, text="")]
    def line(text, x, y):
        for i, char in enumerate(text):
            rows.append(dict(type="char", page=page, text=char,
                             x=x + i * 5, y=y, width=5, height=8))
    if headers:
        for d, day in enumerate("一二三四五六日"):
            x = 110 + d * 110
            rows.append(dict(type="weekday", page=page, text="星期" + day, x=x, y=800, width=15, height=8))
            line("星期" + day, x, 800)
    for d in range(7):
        x = 70 + d * 110
        text = ["2026测试课程" + str(d), "节能原理◇",
                "（1－2节）2－8周（单）/", "校区：南区/场地：09－0102/", "教师：测试教师/学分：2"]
        for j, item in enumerate(text):
            line(item, x, 750 - j * 12)
    for p, y, a, b in [(1, 750, "08:10", "08:55"), (2, 690, "09:05", "09:50")]:
        line(str(p), 40, y)
        line(a, 30, y - 12)
        line(b, 30, y - 24)
    co, si = math.cos(math.radians(angle)), math.sin(math.radians(angle))
    for r in rows:
        if r["type"] == "page":
            r["width"] *= scale
            r["height"] *= scale
            continue
        corners = [(r["x"] + dx, r["y"] + dy) for dx in (0, r["width"]) for dy in (0, r["height"])]
        transformed = [(scale * (co*x - si*y) + offset, scale * (si*x + co*y) + offset) for x,y in corners]
        xs, ys = zip(*transformed)
        r.update(x=min(xs), y=min(ys), width=max(xs)-min(xs), height=max(ys)-min(ys))
    return rows
