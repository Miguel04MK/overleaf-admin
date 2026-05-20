"""
exporters/pdf_base.py
----------------------
ReportLab abstraction layer: colour palette, stylesheet, shared helpers.
All other PDF modules import from here — never the reverse.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable,
)
from reportlab.lib.enums import TA_CENTER

from ._helpers import _today_suffix


# ─── Colour palette ──────────────────────────────────────────────────────────
_TEXT            = colors.HexColor("#1f2933")
_TEXT_SECONDARY  = colors.HexColor("#667085")
_GREEN           = colors.HexColor("#198754")
_GREEN_SOFT      = colors.HexColor("#e8f5e9")
_RED             = colors.HexColor("#dc3545")
_AMBER           = colors.HexColor("#e6a817")
_ROW_ALT         = colors.HexColor("#f7f8fa")
_BORDER          = colors.HexColor("#d0d5dd")
_RULE            = colors.HexColor("#e5e7eb")

# Legacy aliases
_GREEN_LIGHT = _GREEN_SOFT
_GRAY        = _TEXT_SECONDARY
_LIGHT_GRAY  = _ROW_ALT

# Page geometry
_PAGE_W, _PAGE_H = A4
_MARGIN_L = 16 * mm
_MARGIN_R = 16 * mm
_CONTENT_W = _PAGE_W - _MARGIN_L - _MARGIN_R   # ≈ 178 mm


# ─── Stylesheet ──────────────────────────────────────────────────────────────

def _pdf_styles():
    """Return extended stylesheet for reports.

    Typography scale (pt):
      20   — report title (first page only)
      13.5 — section headings
      10.5 — body paragraphs, narrative text, metrics
       9.5 — table cells, sub-section headings
       8.5 — table header, ranking notes
       8   — footer / page header
    """
    styles = getSampleStyleSheet()

    styles.add(ParagraphStyle(
        "ReportTitle",
        parent=styles["Title"],
        fontSize=20, leading=24,
        textColor=_TEXT, spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=9.5, leading=13,
        textColor=_TEXT_SECONDARY, spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13.5, leading=17,
        textColor=_TEXT, spaceBefore=22, spaceAfter=6,
        borderWidth=0, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "MetricLabel",
        parent=styles["Normal"],
        fontSize=10.5, leading=15,
        textColor=_TEXT_SECONDARY,
    ))
    styles.add(ParagraphStyle(
        "MetricValue",
        parent=styles["Normal"],
        fontSize=10.5, leading=15,
        textColor=_TEXT,
    ))
    styles.add(ParagraphStyle(
        "CellText",
        parent=styles["Normal"],
        fontSize=9.5, leading=12.5,
        textColor=_TEXT,
    ))
    styles.add(ParagraphStyle(
        "CellHeader",
        parent=styles["Normal"],
        fontSize=8.5, leading=11,
        textColor=_TEXT, fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8, textColor=_TEXT_SECONDARY,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "Conclusion",
        parent=styles["Normal"],
        fontSize=10.5, leading=15,
        spaceBefore=8, spaceAfter=8,
        leftIndent=12, borderPadding=6,
    ))

    return styles


# ─── Header / footer for non-general PDFs ───────────────────────────────────

def _header_footer(canvas, doc, title: str, generated_by: str):
    """Draw header/footer on each page (used by specific-report PDFs)."""
    canvas.saveState()
    w, h = A4

    canvas.setStrokeColor(_RULE)
    canvas.setLineWidth(0.4)
    canvas.line(_MARGIN_L, h - 14 * mm, w - _MARGIN_R, h - 14 * mm)

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_TEXT_SECONDARY)
    canvas.drawString(_MARGIN_L, h - 12.5 * mm, f"Overleaf Admin — {title}")
    canvas.drawRightString(w - _MARGIN_R, h - 12.5 * mm,
                           f"Generado por: {generated_by}")

    canvas.drawString(_MARGIN_L, 11 * mm,
                      f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    canvas.drawRightString(w - _MARGIN_R, 11 * mm, f"Página {doc.page}")

    canvas.restoreState()


# ─── Core PDF builder ────────────────────────────────────────────────────────

def _build_pdf(
    title: str,
    generated_by: str,
    flowables: list,
    filters_text: str | None = None,
) -> bytes:
    """Render flowables into a PDF bytes buffer."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=20 * mm, bottomMargin=18 * mm,
        leftMargin=_MARGIN_L, rightMargin=_MARGIN_R,
        title=title,
    )

    styles = _pdf_styles()
    story = []

    story.append(Paragraph(title, styles["ReportTitle"]))
    story.append(Paragraph(
        f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')} &bull; "
        f"Usuario: {generated_by}",
        styles["ReportSubtitle"],
    ))
    if filters_text:
        story.append(Paragraph(
            f"<b>Filtros aplicados:</b> {filters_text}",
            styles["ReportSubtitle"],
        ))
    story.append(HRFlowable(
        width="100%", thickness=0.4, color=_RULE,
        spaceAfter=10, spaceBefore=2,
    ))

    story.extend(flowables)

    def _on_page(canvas, doc):
        _header_footer(canvas, doc, title, generated_by)

    doc.build(story, onFirstPage=_on_page, onLaterPages=_on_page)
    return buf.getvalue()


# ─── Shared table builder ────────────────────────────────────────────────────

def _make_table(headers: list[str], rows: list[list], col_pcts: list[float] | None = None) -> Table:
    """Build a styled data table matching the general-report design.

    Parameters
    ----------
    col_pcts : optional list of floats that sum to ~1.0.
        Each value is the fraction of ``_CONTENT_W`` for that column.
        When omitted the table auto-sizes columns.
    """
    styles = _pdf_styles()
    col_widths = [_CONTENT_W * p for p in col_pcts] if col_pcts else None

    table_data = [
        [Paragraph(h, styles["CellHeader"]) for h in headers]
    ]
    for row in rows:
        table_data.append([
            Paragraph(str(cell), styles["CellText"]) for cell in row
        ])

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _GREEN_SOFT),
        ("TEXTCOLOR", (0, 0), (-1, 0), _TEXT),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, _BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_ALT]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, _RULE),
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def _metric_pair(label: str, value) -> Paragraph:
    """Inline metric: Label: Value."""
    styles = _pdf_styles()
    return Paragraph(
        f'<font color="{_TEXT_SECONDARY.hexval()}">{label}:</font> '
        f'<b>{value}</b>',
        styles["MetricValue"],
    )
