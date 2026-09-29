"""Rebuild anonymous PDFs on macOS. Development-only dependency: reportlab."""
from pathlib import Path
from reportlab.pdfgen import canvas
from reportlab.pdfbase import pdfmetrics
from reportlab.pdfbase.ttfonts import TTFont
from factories import fixture_rows


def generate(directory):
    directory.mkdir(parents=True, exist_ok=True)
    font_path = "/System/Library/Fonts/Supplemental/Arial Unicode.ttf"
    pdfmetrics.registerFont(TTFont("FixtureChinese", font_path))
    for name, scale, angle, multipage in [
        ("anonymous-normal", 1, 0, False),
        ("anonymous-scaled", .72, 0, False),
        ("anonymous-rotated", 1, 90, False),
        ("anonymous-continuation", 1, 0, True),
    ]:
        target = directory / (name + ".pdf")
        pdf = canvas.Canvas(str(target), pagesize=(1000, 1000), invariant=1)
        pdf.setTitle("Anonymous synthetic timetable - parser test only")
        for page in range(2 if multipage else 1):
            pdf.saveState()
            pdf.translate(20, 20)
            if angle:
                pdf.translate(950, 0)
                pdf.rotate(angle)
            pdf.scale(scale, scale)
            pdf.setFont("FixtureChinese", 5)
            for r in fixture_rows():
                if r["type"] != "char":
                    continue
                is_body = r["x"] >= 65 and r["y"] < 790
                if multipage and is_body:
                    if (page == 0 and r["y"] < 720) or (page == 1 and r["y"] >= 720):
                        continue
                if multipage and page == 1 and not is_body:
                    continue  # true continuation without weekday header
                y = r["y"] + (50 if page == 1 else 0)
                pdf.drawString(r["x"], y, r["text"])
            pdf.restoreState()
            pdf.showPage()
        pdf.save()


if __name__ == "__main__":
    generate(Path(__file__).parent / "fixtures")
