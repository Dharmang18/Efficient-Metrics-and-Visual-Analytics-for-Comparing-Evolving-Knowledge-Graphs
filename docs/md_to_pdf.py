"""
Minimal Markdown -> PDF converter (reportlab) for the metrics catalog.

Handles: # / ## / ### headings, paragraphs, '-' bullets, 'N.' numbered items,
``` fenced code blocks, --- rules, **bold**, `inline code`.

Run:  python md_to_pdf.py metrics_candidates.md metrics_candidates.pdf
"""
import re
import sys
from html import escape

from reportlab.lib.pagesizes import A4
from reportlab.lib.units import mm
from reportlab.lib import colors
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Preformatted, HRFlowable, ListFlowable,
    ListItem,
)


def inline(text: str) -> str:
    """Escape HTML, then apply **bold** and `code` inline markup."""
    text = escape(text)
    text = re.sub(r"\*\*(.+?)\*\*", r"<b>\1</b>", text)
    text = re.sub(r"`([^`]+?)`", r'<font face="Courier" size=9>\1</font>', text)
    return text


def build(md_path: str, pdf_path: str):
    ss = getSampleStyleSheet()
    h1 = ParagraphStyle("h1", parent=ss["Heading1"], fontSize=18, spaceBefore=6,
                        spaceAfter=8, textColor=colors.HexColor("#1d4ed8"))
    h2 = ParagraphStyle("h2", parent=ss["Heading2"], fontSize=13.5, spaceBefore=12,
                        spaceAfter=4, textColor=colors.HexColor("#111827"))
    h3 = ParagraphStyle("h3", parent=ss["Heading3"], fontSize=11, spaceBefore=8,
                        spaceAfter=2, textColor=colors.HexColor("#374151"))
    body = ParagraphStyle("body", parent=ss["BodyText"], fontSize=9.5, leading=13,
                          spaceAfter=4)
    em = ParagraphStyle("em", parent=body, textColor=colors.HexColor("#6b7280"),
                        fontName="Helvetica-Oblique")
    code = ParagraphStyle("code", parent=ss["Code"], fontSize=8.2, leading=10.5,
                          backColor=colors.HexColor("#f3f4f6"),
                          borderPadding=6, leftIndent=4, spaceBefore=2, spaceAfter=6)

    lines = open(md_path, encoding="utf-8").read().splitlines()
    flow = []
    i = 0
    bullets, numbered = [], []

    def flush_lists():
        nonlocal bullets, numbered
        if bullets:
            flow.append(ListFlowable(
                [ListItem(Paragraph(inline(b), body), leftIndent=10) for b in bullets],
                bulletType="bullet", start="•"))
            bullets = []
        if numbered:
            flow.append(ListFlowable(
                [ListItem(Paragraph(inline(b), body), leftIndent=10) for b in numbered],
                bulletType="1"))
            numbered = []

    while i < len(lines):
        ln = lines[i]
        if ln.strip().startswith("```"):
            flush_lists()
            buf = []
            i += 1
            while i < len(lines) and not lines[i].strip().startswith("```"):
                buf.append(lines[i]); i += 1
            flow.append(Preformatted("\n".join(buf), code))
            i += 1
            continue
        if ln.startswith("### "):
            flush_lists(); flow.append(Paragraph(inline(ln[4:]), h3))
        elif ln.startswith("## "):
            flush_lists(); flow.append(Paragraph(inline(ln[3:]), h2))
        elif ln.startswith("# "):
            flush_lists(); flow.append(Paragraph(inline(ln[2:]), h1))
        elif ln.strip() == "---":
            flush_lists()
            flow.append(Spacer(1, 3))
            flow.append(HRFlowable(width="100%", color=colors.HexColor("#d1d5db")))
            flow.append(Spacer(1, 3))
        elif ln.startswith("- "):
            numbered and flush_lists(); bullets.append(ln[2:])
        elif re.match(r"^\d+\.\s", ln):
            bullets and flush_lists(); numbered.append(re.sub(r"^\d+\.\s", "", ln))
        elif ln.strip() == "":
            flush_lists()
        elif ln.startswith("*") and ln.rstrip().endswith("*") and not ln.startswith("**"):
            flush_lists(); flow.append(Paragraph(inline(ln.strip().strip("*")), em))
        else:
            flush_lists(); flow.append(Paragraph(inline(ln), body))
        i += 1
    flush_lists()

    SimpleDocTemplate(pdf_path, pagesize=A4,
                      leftMargin=18 * mm, rightMargin=18 * mm,
                      topMargin=16 * mm, bottomMargin=16 * mm,
                      title="Candidate KG Metrics").build(flow)
    print("wrote", pdf_path)


if __name__ == "__main__":
    src = sys.argv[1] if len(sys.argv) > 1 else "metrics_candidates.md"
    dst = sys.argv[2] if len(sys.argv) > 2 else "metrics_candidates.pdf"
    build(src, dst)
