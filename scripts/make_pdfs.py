"""Render demos/*/docs_src/*.md to PDF in the sibling docs/ folder, so demos exercise real PDF ingestion."""
import re
from pathlib import Path

from fpdf import FPDF

ROOT = Path(__file__).resolve().parents[1]


def render(md: Path, out: Path) -> None:
    pdf = FPDF()
    pdf.set_auto_page_break(True, margin=15)
    pdf.add_page()
    for line in md.read_text(encoding="utf-8").splitlines():
        line = line.replace("–", "-").replace("—", "-")
        h = re.match(r"^(#+)\s+(.*)", line)
        if h:
            pdf.set_font("Helvetica", "B", 15 if len(h.group(1)) == 1 else 12)
            pdf.multi_cell(0, 8, h.group(2), new_x="LMARGIN", new_y="NEXT")
        elif line.strip():
            pdf.set_font("Helvetica", "", 10)
            pdf.multi_cell(0, 5, line, new_x="LMARGIN", new_y="NEXT")
        else:
            pdf.ln(3)
    pdf.output(str(out))


if __name__ == "__main__":
    for src in ROOT.glob("demos/**/docs_src/*.md"):
        out = src.parent.parent / "docs" / (src.stem + ".pdf")
        out.parent.mkdir(exist_ok=True)
        render(src, out)
        print("wrote", out.relative_to(ROOT))
