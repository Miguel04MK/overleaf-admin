"""
app/modules/reports/exporters.py
----------------------------------
CSV and PDF generation for each report type.

PDF engine: ReportLab (pure Python, no system dependencies).
The PDF builder is abstracted so the engine can be swapped later.
"""
from __future__ import annotations

import csv
import io
from datetime import datetime
from typing import Any

from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.audit_log import AuditLog
from app.model.entities.sync_run import SyncRun

# ═══════════════════════════════════════════════════════════════════════════════
# CSV helpers
# ═══════════════════════════════════════════════════════════════════════════════

def _make_csv(filename: str, rows: list[list]) -> tuple[bytes, str, str]:
    """Build a UTF-8 CSV bytes object, filename and content-type."""
    buf = io.StringIO()
    w = csv.writer(buf)
    for row in rows:
        w.writerow(row)
    data = buf.getvalue().encode("utf-8-sig")  # BOM for Excel compatibility
    return data, filename, "text/csv; charset=utf-8"


def _today_suffix() -> str:
    """Return today's date as dd-mm-yyyy for filenames."""
    return datetime.now().strftime("%d-%m-%Y")


def _ts(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d %H:%M:%S") if dt else ""


def _ts_short(dt: datetime | None) -> str:
    """Compact timestamp for PDF table cells: '07/05/2026 17:53'."""
    return dt.strftime("%d/%m/%Y %H:%M") if dt else ""


def _date(dt: datetime | None) -> str:
    return dt.strftime("%Y-%m-%d") if dt else ""


def _fmt_bytes(n) -> str:
    if n is None:
        return ""
    n = float(n)
    for unit in ("B", "KB", "MB", "GB", "TB"):
        if abs(n) < 1024.0:
            return f"{n:.1f} {unit}"
        n /= 1024.0
    return f"{n:.1f} PB"


# ═══════════════════════════════════════════════════════════════════════════════
# CSV EXPORTERS
# ═══════════════════════════════════════════════════════════════════════════════

def export_users_csv(users: list[OverleafUser]) -> tuple[bytes, str, str]:
    header = [
        "ID", "Email", "Nombre", "Apellidos",
        "Admin", "Rol", "Cuota asignada (bytes)", "Cuota usada (bytes)",
        "% Uso", "Proyectos propietario", "Proyectos colaborador",
        "Fecha alta", "Último acceso",
    ]
    rows = [header]
    for u in users:
        rows.append([
            u.overleaf_id,
            u.email or "",
            u.first_name or "",
            u.last_name or "",
            "Sí" if u.is_admin else "No",
            u.role.name if u.role else "",
            u.max_quota_bytes if u.max_quota_bytes is not None else "Sin límite",
            u.quota_used_bytes,
            u.quota_percent if u.quota_percent is not None else "",
            u.projects_owned.count(),
            u.memberships.count(),
            _date(u.signup_date),
            _ts(u.last_login_at),
        ])
    return _make_csv(f"informe_usuarios_{_today_suffix()}.csv", rows)


def export_projects_csv(projects: list[OverleafProject]) -> tuple[bytes, str, str]:
    header = [
        "ID", "Nombre", "Propietario (email)", "Tamaño",
        "Archivos", "Miembros", "Creado", "Última actualización",
    ]
    rows = [header]
    for p in projects:
        member_count = p.members.count() if p.members else 0
        rows.append([
            p.overleaf_id,
            p.name or "",
            p.owner.email if p.owner else p.owner_overleaf_id or "",
            _fmt_bytes(p.size_bytes),
            p.file_count if p.file_count is not None else "",
            member_count,
            _date(p.created_at),
            _date(p.last_updated_at),
        ])
    return _make_csv(f"informe_proyectos_{_today_suffix()}.csv", rows)


def export_storage_csv(rows_data: list[dict]) -> tuple[bytes, str, str]:
    header = [
        "Email", "Nombre", "Cuota asignada", "Espacio usado",
        "% Uso", "Num proyectos",
    ]
    rows = [header]
    for r in rows_data:
        u = r["user"]
        rows.append([
            u.email or "",
            u.display_name,
            r["quota_fmt"],
            r["used_fmt"],
            r["quota_pct"] if r["quota_pct"] is not None else "Sin límite",
            r["proj_count"],
        ])
    return _make_csv(f"informe_almacenamiento_{_today_suffix()}.csv", rows)


def export_activity_csv(entries: list[AuditLog]) -> tuple[bytes, str, str]:
    header = ["Fecha/Hora", "Actor", "Acción", "Nivel", "IP", "Detalle"]
    rows = [header]
    for e in entries:
        rows.append([
            _ts(e.created_at),
            e.actor,
            e.action,
            e.level,
            e.ip_address or "",
            e.detail or "",
        ])
    return _make_csv(f"informe_actividad_{_today_suffix()}.csv", rows)


def export_syncs_csv(runs: list[SyncRun]) -> tuple[bytes, str, str]:
    header = [
        "ID", "Estado", "Iniciado por", "Inicio", "Fin",
        "Duración (s)", "Usuarios encontrados", "Usuarios sincronizados",
        "Proyectos encontrados", "Proyectos sincronizados",
        "Delta usuarios", "Delta proyectos", "Mensaje",
    ]
    rows = [header]
    for r in runs:
        rows.append([
            r.id,
            r.status,
            r.triggered_by,
            _ts(r.started_at),
            _ts(r.finished_at),
            r.duration_seconds if r.duration_seconds is not None else "",
            r.users_found,
            r.users_synced,
            r.projects_found,
            r.projects_synced,
            r.users_delta if r.users_delta is not None else "",
            r.projects_delta if r.projects_delta is not None else "",
            r.message or "",
        ])
    return _make_csv(f"informe_sincronizaciones_{_today_suffix()}.csv", rows)


def export_quotas_csv(rows_data: list[dict]) -> tuple[bytes, str, str]:
    header = [
        "Email", "Nombre", "Rol", "Cuota asignada", "Espacio usado",
        "% Uso", "Estado", "Proyectos", "Límite proyectos",
        "Excede límite proyectos",
    ]
    rows = [header]
    for r in rows_data:
        u = r["user"]
        rows.append([
            u.email or "",
            u.display_name,
            r["role_name"],
            r["quota_fmt"],
            r["used_fmt"],
            r["pct"] if r["pct"] is not None else "",
            r["status"],
            r["projects_count"],
            r["max_projects"] if r["max_projects"] is not None else "Sin límite",
            "Sí" if r["exceeds_project_limit"] else "No",
        ])
    return _make_csv(f"informe_cuotas_{_today_suffix()}.csv", rows)


def export_incidents_csv(entries: list[AuditLog]) -> tuple[bytes, str, str]:
    header = ["Fecha/Hora", "Nivel", "Actor", "Acción", "Detalle", "IP"]
    rows = [header]
    for e in entries:
        rows.append([
            _ts(e.created_at),
            e.level,
            e.actor,
            e.action,
            e.detail or "",
            e.ip_address or "",
        ])
    return _make_csv(f"informe_incidencias_{_today_suffix()}.csv", rows)


def export_general_csv(data: dict) -> tuple[bytes, str, str]:
    """Flat CSV summary of the general platform report."""
    rows = [
        ["Sección", "Métrica", "Valor"],
        ["Usuarios", "Total usuarios sincronizados", data["total_users"]],
        ["Usuarios", "Administradores internos", data["total_admins_internal"]],
        ["Usuarios", "Roles definidos", data["total_roles"]],
        ["Usuarios", "Usuarios sin rol", data["users_no_role"]],
        ["Usuarios", "Usuarios cerca de cuota", len(data["users_near_quota"])],
        ["Usuarios", "Usuarios excedidos de cuota", len(data["users_exceeded_quota"])],
        ["Proyectos", "Total proyectos", data["total_projects"]],
        ["Proyectos", "Proyectos grandes (>10 MB)", data["large_projects"]],
        ["Proyectos", "Proyectos inactivos (>90 días)", data["inactive_projects"]],
        ["Proyectos", "Proyectos colaborativos", data["collaborative_projects"]],
        ["Almacenamiento", "Total consumido", data["total_storage_fmt"]],
        ["Almacenamiento", "Media por usuario", data["avg_storage_per_user_fmt"]],
        ["Almacenamiento", "Media por proyecto", data["avg_storage_per_project_fmt"]],
        ["Sincronización", "Total ejecuciones", data["total_syncs"]],
        ["Sincronización", "% correctas", data["success_pct"]],
        ["Sincronización", "Duración media (s)", data["avg_sync_duration"] or "N/A"],
        ["Auditoría", "Alertas activas (24 h)", data["active_alerts_count"]],
    ]
    return _make_csv(f"informe_general_{_today_suffix()}.csv", rows)


# ═══════════════════════════════════════════════════════════════════════════════
# PDF BUILDER — ReportLab abstraction
# ═══════════════════════════════════════════════════════════════════════════════

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import getSampleStyleSheet, ParagraphStyle
from reportlab.lib.units import mm, cm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    PageBreak, HRFlowable, KeepTogether,
)
from reportlab.lib.enums import TA_CENTER, TA_LEFT, TA_RIGHT


# ─── Colour palette ──────────────────────────────────────────────────────────
# Sober, academic palette: dark text, subtle accents.
_TEXT = colors.HexColor("#1f2933")           # main body text
_TEXT_SECONDARY = colors.HexColor("#667085") # muted labels, footer
_GREEN = colors.HexColor("#198754")          # accent only (small details)
_GREEN_SOFT = colors.HexColor("#e8f5e9")     # table-header background
_RED = colors.HexColor("#dc3545")            # warnings / errors
_AMBER = colors.HexColor("#e6a817")          # caution
_ROW_ALT = colors.HexColor("#f7f8fa")        # alternating table rows
_BORDER = colors.HexColor("#d0d5dd")         # table grid
_RULE = colors.HexColor("#e5e7eb")           # section separators

# Legacy aliases kept so other PDF exporters still compile:
_GREEN_LIGHT = _GREEN_SOFT
_GRAY = _TEXT_SECONDARY
_LIGHT_GRAY = _ROW_ALT

# Page geometry
_PAGE_W, _PAGE_H = A4
_MARGIN_L = 16 * mm
_MARGIN_R = 16 * mm
_CONTENT_W = _PAGE_W - _MARGIN_L - _MARGIN_R  # ≈ 178 mm


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
        fontSize=20,
        leading=24,
        textColor=_TEXT,
        spaceAfter=4,
    ))
    styles.add(ParagraphStyle(
        "ReportSubtitle",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=13,
        textColor=_TEXT_SECONDARY,
        spaceAfter=10,
    ))
    styles.add(ParagraphStyle(
        "SectionHeading",
        parent=styles["Heading2"],
        fontSize=13.5,
        leading=17,
        textColor=_TEXT,
        spaceBefore=22,
        spaceAfter=6,
        borderWidth=0,
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "MetricLabel",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=15,
        textColor=_TEXT_SECONDARY,
    ))
    styles.add(ParagraphStyle(
        "MetricValue",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=15,
        textColor=_TEXT,
    ))
    styles.add(ParagraphStyle(
        "CellText",
        parent=styles["Normal"],
        fontSize=9.5,
        leading=12.5,
        textColor=_TEXT,
    ))
    styles.add(ParagraphStyle(
        "CellHeader",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=_TEXT,
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "Footer",
        parent=styles["Normal"],
        fontSize=8,
        textColor=_TEXT_SECONDARY,
        alignment=TA_CENTER,
    ))
    styles.add(ParagraphStyle(
        "Conclusion",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=15,
        spaceBefore=8,
        spaceAfter=8,
        leftIndent=12,
        borderPadding=6,
    ))

    return styles


# ─── Shared header / footer for non-general PDFs ────────────────────────────

def _header_footer(canvas, doc, title: str, generated_by: str):
    """Draw header/footer on each page (used by specific-report PDFs)."""
    canvas.saveState()
    w, h = A4

    # Header — thin rule + small text
    canvas.setStrokeColor(_RULE)
    canvas.setLineWidth(0.4)
    canvas.line(_MARGIN_L, h - 14 * mm, w - _MARGIN_R, h - 14 * mm)

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_TEXT_SECONDARY)
    canvas.drawString(_MARGIN_L, h - 12.5 * mm, f"Overleaf Admin — {title}")
    canvas.drawRightString(w - _MARGIN_R, h - 12.5 * mm,
                           f"Generado por: {generated_by}")

    # Footer
    canvas.drawString(_MARGIN_L, 11 * mm,
                      f"Generado: {datetime.now().strftime('%d/%m/%Y %H:%M')}")
    canvas.drawRightString(w - _MARGIN_R, 11 * mm, f"Página {doc.page}")

    canvas.restoreState()


def _build_pdf(
    title: str,
    generated_by: str,
    flowables: list,
    filters_text: str | None = None,
) -> bytes:
    """Render flowables into a PDF bytes buffer."""
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=20 * mm,
        bottomMargin=18 * mm,
        leftMargin=_MARGIN_L,
        rightMargin=_MARGIN_R,
        title=title,
    )

    styles = _pdf_styles()
    story = []

    # Title block
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

def _make_table(headers: list[str], rows: list[list], col_widths=None) -> Table:
    """Build a styled data table with soft header and generous padding."""
    styles = _pdf_styles()

    table_data = [
        [Paragraph(h, styles["CellHeader"]) for h in headers]
    ]
    for row in rows:
        table_data.append([
            Paragraph(str(cell), styles["CellText"]) for cell in row
        ])

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        # Header row: soft green background, dark text
        ("BACKGROUND", (0, 0), (-1, 0), _GREEN_SOFT),
        ("TEXTCOLOR", (0, 0), (-1, 0), _TEXT),
        ("FONTSIZE", (0, 0), (-1, 0), 8.5),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, _BORDER),
        # Data rows
        ("FONTSIZE", (0, 1), (-1, -1), 9.5),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_ALT]),
        # Grid
        ("GRID", (0, 0), (-1, -1), 0.3, _BORDER),
        # Alignment & padding
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


# ═══════════════════════════════════════════════════════════════════════════════
# PDF EXPORTERS
# ═══════════════════════════════════════════════════════════════════════════════

def export_users_pdf(
    users: list[OverleafUser],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    styles = _pdf_styles()
    flowables = []

    flowables.append(Paragraph(f"Total usuarios: <b>{len(users)}</b>", styles["Normal"]))
    flowables.append(Spacer(1, 6))

    headers = ["Email", "Nombre", "Rol", "Admin", "Cuota usada", "% Uso", "Alta", "Últ. acceso"]
    rows = []
    for u in users:
        rows.append([
            u.email or u.overleaf_id,
            u.display_name,
            u.role.name if u.role else "",
            "Sí" if u.is_admin else "No",
            u.quota_used_fmt,
            f"{u.quota_percent}%" if u.quota_percent is not None else "",
            _date(u.signup_date),
            _date(u.last_login_at),
        ])

    widths = [90, 70, 50, 30, 60, 35, 55, 60]
    flowables.append(_make_table(headers, rows, col_widths=widths))

    data = _build_pdf("Informe de usuarios", generated_by, flowables, filters_text)
    return data, f"informe_usuarios_{_today_suffix()}.pdf", "application/pdf"


def export_projects_pdf(
    projects: list[OverleafProject],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    styles = _pdf_styles()
    flowables = []

    flowables.append(Paragraph(f"Total proyectos: <b>{len(projects)}</b>", styles["Normal"]))
    flowables.append(Spacer(1, 6))

    headers = ["Nombre", "Propietario", "Tamaño", "Archivos", "Miembros", "Creado", "Últ. act."]
    rows = []
    for p in projects:
        mc = p.members.count() if p.members else 0
        rows.append([
            (p.name or "")[:40],
            (p.owner.email if p.owner else "")[:30],
            _fmt_bytes(p.size_bytes),
            p.file_count or "",
            mc,
            _date(p.created_at),
            _date(p.last_updated_at),
        ])

    widths = [100, 80, 55, 40, 40, 55, 55]
    flowables.append(_make_table(headers, rows, col_widths=widths))

    data = _build_pdf("Informe de proyectos", generated_by, flowables, filters_text)
    return data, f"informe_proyectos_{_today_suffix()}.pdf", "application/pdf"


def export_storage_pdf(
    rows_data: list[dict],
    totals: dict | None = None,
    generated_by: str = "system",
) -> tuple[bytes, str, str]:
    styles = _pdf_styles()
    flowables = []

    if totals:
        flowables.append(_metric_pair("Total consumido", totals.get("total_bytes_fmt", "")))
        flowables.append(_metric_pair("Media por usuario", totals.get("avg_per_user_fmt", "")))
        flowables.append(_metric_pair("Media por proyecto", totals.get("avg_per_project_fmt", "")))
        flowables.append(Spacer(1, 8))

    headers = ["Email", "Nombre", "Cuota", "Usado", "% Uso", "Proyectos"]
    rows = []
    for r in rows_data:
        u = r["user"]
        rows.append([
            (u.email or "")[:35],
            u.display_name[:25],
            r["quota_fmt"],
            r["used_fmt"],
            f"{r['quota_pct']}%" if r["quota_pct"] is not None else "Sin límite",
            r["proj_count"],
        ])

    widths = [100, 80, 65, 65, 50, 45]
    flowables.append(_make_table(headers, rows, col_widths=widths))

    data = _build_pdf("Informe de almacenamiento", generated_by, flowables)
    return data, f"informe_almacenamiento_{_today_suffix()}.pdf", "application/pdf"


def export_quotas_pdf(
    rows_data: list[dict],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    styles = _pdf_styles()
    flowables = []

    flowables.append(Paragraph(f"Total usuarios: <b>{len(rows_data)}</b>", styles["Normal"]))
    flowables.append(Spacer(1, 6))

    headers = ["Email", "Rol", "Cuota", "Usado", "% Uso", "Estado", "Proy.", "Limite", "Excede proy."]
    rows = []
    for r in rows_data:
        u = r["user"]
        rows.append([
            (u.email or "")[:30],
            r["role_name"][:12],
            r["quota_fmt"],
            r["used_fmt"],
            f"{r['pct']}%" if r["pct"] is not None else "",
            r["status"],
            r["projects_count"],
            r["max_projects"] if r["max_projects"] is not None else "Sin lím.",
            "Sí" if r["exceeds_project_limit"] else "No",
        ])

    widths = [80, 40, 50, 50, 35, 42, 28, 35, 42]
    flowables.append(_make_table(headers, rows, col_widths=widths))

    data = _build_pdf("Informe de cuotas", generated_by, flowables, filters_text)
    return data, f"informe_cuotas_{_today_suffix()}.pdf", "application/pdf"


def export_activity_pdf(
    entries: list[AuditLog],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    styles = _pdf_styles()
    flowables = []

    flowables.append(Paragraph(f"Total entradas: <b>{len(entries)}</b>", styles["Normal"]))
    flowables.append(Spacer(1, 6))

    headers = ["Fecha", "Actor", "Acción", "Nivel", "IP", "Detalle"]
    rows = []
    for e in entries:
        rows.append([
            _ts(e.created_at),
            e.actor or "",
            e.action or "",
            e.level or "",
            e.ip_address or "",
            (e.detail or "")[:60],
        ])

    widths = [75, 55, 55, 35, 55, 150]
    flowables.append(_make_table(headers, rows, col_widths=widths))

    data = _build_pdf("Informe de actividad administrativa", generated_by, flowables, filters_text)
    return data, f"informe_actividad_{_today_suffix()}.pdf", "application/pdf"


def export_incidents_pdf(
    entries: list[AuditLog],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    styles = _pdf_styles()
    flowables = []

    flowables.append(Paragraph(f"Total incidencias: <b>{len(entries)}</b>", styles["Normal"]))
    flowables.append(Spacer(1, 6))

    headers = ["Fecha", "Nivel", "Actor", "Acción", "Detalle"]
    rows = []
    for e in entries:
        rows.append([
            _ts(e.created_at),
            e.level or "",
            e.actor or "",
            e.action or "",
            (e.detail or "")[:80],
        ])

    widths = [75, 40, 55, 55, 200]
    flowables.append(_make_table(headers, rows, col_widths=widths))

    data = _build_pdf("Informe de incidencias", generated_by, flowables, filters_text)
    return data, f"informe_incidencias_{_today_suffix()}.pdf", "application/pdf"


def export_syncs_pdf(
    runs: list[SyncRun],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    styles = _pdf_styles()
    flowables = []

    flowables.append(Paragraph(f"Total ejecuciones: <b>{len(runs)}</b>", styles["Normal"]))
    flowables.append(Spacer(1, 6))

    headers = ["Inicio", "Fin", "Dur.(s)", "Estado", "Iniciado", "Us.enc.", "Us.sync.", "Pr.enc.", "Pr.sync."]
    rows = []
    for r in runs:
        rows.append([
            _ts(r.started_at),
            _ts(r.finished_at),
            f"{r.duration_seconds:.0f}" if r.duration_seconds else "",
            r.status,
            r.triggered_by,
            r.users_found,
            r.users_synced,
            r.projects_found,
            r.projects_synced,
        ])

    widths = [68, 68, 32, 38, 40, 32, 32, 32, 32]
    flowables.append(_make_table(headers, rows, col_widths=widths))

    data = _build_pdf("Informe de sincronizaciones", generated_by, flowables, filters_text)
    return data, f"informe_sincronizaciones_{_today_suffix()}.pdf", "application/pdf"


# ═══════════════════════════════════════════════════════════════════════════════
# GENERAL REPORT PDF — helpers
# ═══════════════════════════════════════════════════════════════════════════════

# Action name translation (internal → Spanish)
_ACTION_TRANSLATIONS: dict[str, str] = {
    "changed": "Cambio de rol",
    "role_change": "Cambio de rol",
    "quota_change": "Cambio de cuota",
    "sync_error": "Error de sincronización",
    "sync_start": "Inicio de sincronización",
    "sync_ok": "Sincronización correcta",
    "login": "Inicio de sesión",
    "logout": "Cierre de sesión",
    "export": "Exportación",
    "create": "Creación",
    "delete": "Eliminación",
    "update": "Actualización",
}


def _translate_action(action: str | None) -> str:
    """Translate internal action names to Spanish."""
    if not action:
        return ""
    return _ACTION_TRANSLATIONS.get(action, action)


def _smart_truncate(text: str, max_len: int = 60) -> str:
    """Truncate text cleanly at word boundary with ellipsis."""
    if not text or len(text) <= max_len:
        return text or ""
    truncated = text[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len * 0.4:
        return truncated[:last_space] + "…"
    return truncated + "…"


def _build_narrative_summary(data: dict) -> str:
    """Generate a rule-based narrative summary paragraph for the report."""
    parts = []

    parts.append(
        f"La plataforma cuenta con <b>{data['total_users']}</b> usuarios "
        f"sincronizados y <b>{data['total_projects']}</b> proyectos, "
        f"con un almacenamiento total de <b>{data['total_storage_fmt']}</b>."
    )

    n_exceeded = len(data["users_exceeded_quota"])
    n_near = len(data["users_near_quota"])
    if n_exceeded > 0:
        parts.append(
            f'<font color="{_RED.hexval()}"><b>Atención:</b> {n_exceeded} usuario(s) '
            f"han superado su cuota de almacenamiento.</font>"
        )
    elif n_near > 0:
        parts.append(
            f'<font color="{_AMBER.hexval()}"><b>Aviso:</b> {n_near} usuario(s) '
            f"están cerca de alcanzar su cuota de almacenamiento.</font>"
        )

    if data["total_syncs"] > 0:
        if data["last_sync"]:
            ls = data["last_sync"]
            if ls.status == "error":
                parts.append(
                    f'<font color="{_RED.hexval()}">La última sincronización '
                    f"finalizó con errores. Se recomienda revisar el apartado "
                    f"de sincronización.</font>"
                )
            elif data["success_pct"] < 90:
                parts.append(
                    f'<font color="{_AMBER.hexval()}">El porcentaje de '
                    f"sincronizaciones correctas ({data['success_pct']}%) "
                    f"está por debajo del umbral recomendado (90%).</font>"
                )
            else:
                parts.append(
                    f"Las sincronizaciones funcionan correctamente, con un "
                    f"{data['success_pct']}% de ejecuciones exitosas."
                )

    if data["active_alerts_count"] > 0:
        parts.append(
            f"Se han registrado <b>{data['active_alerts_count']}</b> alertas "
            f"en las últimas 24 horas."
        )
    else:
        parts.append(
            "No se han registrado alertas en las últimas 24 horas."
        )

    return " ".join(parts)


# ─── Page callbacks for the general report ───────────────────────────────────

def _general_first_page(canvas, doc, generated_by: str):
    """Cover-style header — first page only.

    Small green accent bar at the very top, then title and meta below it.
    Keeps it sober: no full-width colour band.
    """
    canvas.saveState()
    w, h = A4

    # Thin green accent line across top
    canvas.setStrokeColor(_GREEN)
    canvas.setLineWidth(1.8)
    canvas.line(_MARGIN_L, h - 12 * mm, w - _MARGIN_R, h - 12 * mm)

    # Title
    canvas.setFont("Helvetica-Bold", 20)
    canvas.setFillColor(_TEXT)
    canvas.drawString(_MARGIN_L, h - 22 * mm, "Informe general de la plataforma")

    # Subtitle
    canvas.setFont("Helvetica", 9.5)
    canvas.setFillColor(_TEXT_SECONDARY)
    canvas.drawString(_MARGIN_L, h - 28 * mm,
                      "Overleaf Community — Panel de administración")

    # Meta line
    canvas.setFont("Helvetica", 8)
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    canvas.drawString(_MARGIN_L, h - 35 * mm, f"Generado: {now_str}")
    canvas.drawString(90 * mm, h - 35 * mm, f"Usuario: {generated_by}")
    canvas.setFillColor(_GREEN)
    canvas.drawRightString(w - _MARGIN_R, h - 35 * mm, "● Informe completo")

    # Separator below meta
    canvas.setStrokeColor(_RULE)
    canvas.setLineWidth(0.4)
    canvas.line(_MARGIN_L, h - 38 * mm, w - _MARGIN_R, h - 38 * mm)

    # Footer
    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_TEXT_SECONDARY)
    canvas.drawString(_MARGIN_L, 10 * mm, f"Generado: {now_str}")
    canvas.drawRightString(w - _MARGIN_R, 10 * mm, f"Página {doc.page}")

    canvas.restoreState()


def _general_later_pages(canvas, doc, generated_by: str):
    """Minimal header/footer on subsequent pages."""
    canvas.saveState()
    w, h = A4

    # Subtle rule
    canvas.setStrokeColor(_RULE)
    canvas.setLineWidth(0.4)
    canvas.line(_MARGIN_L, h - 13 * mm, w - _MARGIN_R, h - 13 * mm)

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_TEXT_SECONDARY)
    canvas.drawString(_MARGIN_L, h - 11.5 * mm,
                      "Informe general — Overleaf Admin")
    canvas.drawRightString(w - _MARGIN_R, h - 11.5 * mm,
                           f"Generado por: {generated_by}")

    # Footer
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    canvas.drawString(_MARGIN_L, 10 * mm, f"Generado: {now_str}")
    canvas.drawRightString(w - _MARGIN_R, 10 * mm, f"Página {doc.page}")

    canvas.restoreState()


_RANKING_NOTE_TEXT = "Se muestran los 5 registros más relevantes."


# ─── Full-width table helper for the general report ─────────────────────────

def _gen_table(headers: list[str], rows: list[list],
               col_pcts: list[float]) -> Table:
    """Build a full-width table using percentage-based column widths.

    ``col_pcts`` values should sum to 1.0 (e.g. [0.40, 0.20, 0.20, 0.20]).
    """
    styles = _pdf_styles()
    col_widths = [_CONTENT_W * p for p in col_pcts]

    table_data = [
        [Paragraph(h, styles["CellHeader"]) for h in headers]
    ]
    for row in rows:
        table_data.append([
            Paragraph(str(cell), styles["CellText"]) for cell in row
        ])

    t = Table(table_data, colWidths=col_widths, repeatRows=1)
    t.setStyle(TableStyle([
        # Header
        ("BACKGROUND", (0, 0), (-1, 0), _GREEN_SOFT),
        ("TEXTCOLOR", (0, 0), (-1, 0), _TEXT),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, _BORDER),
        # Data
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_ALT]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, _RULE),
        # Padding
        ("VALIGN", (0, 0), (-1, -1), "TOP"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
    ]))
    return t


def _gen_kv_table(rows: list[list[str]]) -> Table:
    """Key-value two-column table (Métrica / Valor), full width, 65/35 split."""
    styles = _pdf_styles()
    w_label = _CONTENT_W * 0.65
    w_value = _CONTENT_W * 0.35

    table_data = [
        [Paragraph(r[0], styles["CellText"]),
         Paragraph(str(r[1]), styles["CellText"])]
        for r in rows
    ]
    # Prepend header
    table_data.insert(0, [
        Paragraph("Métrica", styles["CellHeader"]),
        Paragraph("Valor", styles["CellHeader"]),
    ])

    t = Table(table_data, colWidths=[w_label, w_value], repeatRows=1)
    t.setStyle(TableStyle([
        ("BACKGROUND", (0, 0), (-1, 0), _GREEN_SOFT),
        ("LINEBELOW", (0, 0), (-1, 0), 0.6, _BORDER),
        ("ROWBACKGROUNDS", (0, 1), (-1, -1), [colors.white, _ROW_ALT]),
        ("LINEBELOW", (0, 1), (-1, -1), 0.3, _RULE),
        ("VALIGN", (0, 0), (-1, -1), "MIDDLE"),
        ("TOPPADDING", (0, 0), (-1, -1), 6),
        ("BOTTOMPADDING", (0, 0), (-1, -1), 6),
        ("LEFTPADDING", (0, 0), (-1, -1), 7),
        ("RIGHTPADDING", (0, 0), (-1, -1), 7),
        # Right-align values column
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    return t


# ═══════════════════════════════════════════════════════════════════════════════
# GENERAL REPORT PDF
# ═══════════════════════════════════════════════════════════════════════════════

def export_general_pdf(data: dict, generated_by: str = "system") -> tuple[bytes, str, str]:
    """Build the comprehensive general platform report PDF."""
    styles = _pdf_styles()

    # ── Extra styles for the general report only ─────────────────────────
    styles.add(ParagraphStyle(
        "Narrative",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=15,
        spaceBefore=4,
        spaceAfter=10,
        textColor=_TEXT,
    ))
    styles.add(ParagraphStyle(
        "RankingNote",
        parent=styles["Normal"],
        fontSize=8.5,
        leading=11,
        textColor=_TEXT_SECONDARY,
        spaceBefore=2,
        spaceAfter=4,
        fontName="Helvetica-Oblique",
    ))
    styles.add(ParagraphStyle(
        "SubSectionHeading",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=14,
        textColor=_TEXT,
        spaceBefore=14,
        spaceAfter=6,
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "TableIntro",
        parent=styles["Normal"],
        fontSize=10.5,
        leading=14,
        spaceBefore=8,
        spaceAfter=6,
        textColor=_TEXT,
    ))

    flowables: list = []

    # ── Shorthand helpers ────────────────────────────────────────────────

    def _heading(text: str):
        """Section heading kept together with the rule and next narrative."""
        block = [
            Spacer(1, 18),
            HRFlowable(
                width="100%", thickness=0.4, color=_RULE,
                spaceAfter=4, spaceBefore=0,
            ),
            Paragraph(text, styles["SectionHeading"]),
        ]
        flowables.append(KeepTogether(block))

    def _subheading(text: str):
        flowables.append(Paragraph(text, styles["SubSectionHeading"]))

    def _narrative(text: str):
        flowables.append(Paragraph(text, styles["Narrative"]))

    def _metric(label: str, value):
        flowables.append(_metric_pair(label, value))

    def _table_intro(text: str):
        flowables.append(Paragraph(text, styles["TableIntro"]))

    def _ranking_note():
        flowables.append(Paragraph(_RANKING_NOTE_TEXT, styles["RankingNote"]))

    def _after_table():
        """Standard spacing after a table block."""
        flowables.append(Spacer(1, 16))

    def _after_metrics():
        """Standard spacing after a metrics block."""
        flowables.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════
    # 1. Resumen
    # ══════════════════════════════════════════════════════════════════════
    _heading("1. Resumen")
    _narrative(_build_narrative_summary(data))

    summary_rows = [
        ["Usuarios sincronizados", str(data["total_users"])],
        ["Proyectos sincronizados", str(data["total_projects"])],
        ["Administradores internos", str(data["total_admins_internal"])],
        ["Roles definidos", str(data["total_roles"])],
        ["Almacenamiento total", data["total_storage_fmt"]],
        ["Sincronizaciones totales", str(data["total_syncs"])],
        ["% sincronizaciones correctas", f"{data['success_pct']}%"],
        ["Alertas activas (24 h)", str(data["active_alerts_count"])],
    ]
    if data["last_sync"]:
        ls = data["last_sync"]
        summary_rows.append(["Última sincronización", _ts_short(ls.started_at)])
        summary_rows.append(["Estado última sincronización", ls.status])

    flowables.append(_gen_kv_table(summary_rows))
    _after_table()

    # ══════════════════════════════════════════════════════════════════════
    # 2. Usuarios
    # ══════════════════════════════════════════════════════════════════════
    _heading("2. Usuarios")

    users_narr = (
        f"Se han sincronizado <b>{data['total_users']}</b> usuarios desde "
        f"Overleaf. De ellos, <b>{data['users_no_role']}</b> no tienen un "
        f"rol asignado en la plataforma."
    )
    if data["users_by_role"]:
        role_list = [f"{r['name']} ({r['count']})" for r in data["users_by_role"]]
        users_narr += f" Distribución por roles: {', '.join(role_list)}."
    _narrative(users_narr)

    _metric("Total usuarios sincronizados", data["total_users"])
    _metric("Usuarios sin rol asignado", data["users_no_role"])
    _after_metrics()

    if data["users_by_role"]:
        role_rows = [[r["name"], str(r["count"])] for r in data["users_by_role"]]
        flowables.append(_gen_table(
            ["Rol", "Usuarios"],
            role_rows,
            col_pcts=[0.65, 0.35],
        ))
        _after_table()

    if data["users_exceeded_quota"]:
        _table_intro(
            f'<font color="{_RED.hexval()}"><b>Usuarios que superan cuota '
            f'({len(data["users_exceeded_quota"])}):</b></font>'
        )
        exc_rows = [
            [u["email"], u["used_fmt"], u["quota_fmt"], f"{u['pct']}%"]
            for u in data["users_exceeded_quota"][:5]
        ]
        flowables.append(_gen_table(
            ["Email", "Usado", "Cuota", "% Uso"],
            exc_rows,
            col_pcts=[0.40, 0.20, 0.20, 0.20],
        ))
        if len(data["users_exceeded_quota"]) > 5:
            _ranking_note()
        _after_table()

    if data["users_near_quota"]:
        _table_intro(
            f'<font color="{_AMBER.hexval()}"><b>Usuarios cerca de cuota '
            f'({len(data["users_near_quota"])}):</b></font>'
        )
        near_rows = [
            [u["email"], u["used_fmt"], u["quota_fmt"], f"{u['pct']}%"]
            for u in data["users_near_quota"][:5]
        ]
        flowables.append(_gen_table(
            ["Email", "Usado", "Cuota", "% Uso"],
            near_rows,
            col_pcts=[0.40, 0.20, 0.20, 0.20],
        ))
        if len(data["users_near_quota"]) > 5:
            _ranking_note()
        _after_table()

    # ══════════════════════════════════════════════════════════════════════
    # 3. Proyectos
    # ══════════════════════════════════════════════════════════════════════
    _heading("3. Proyectos")

    _narrative(
        f"Existen <b>{data['total_projects']}</b> proyectos en la plataforma. "
        f"De ellos, <b>{data['large_projects']}</b> superan los 10 MB, "
        f"<b>{data['inactive_projects']}</b> llevan más de 90 días sin "
        f"actividad y <b>{data['collaborative_projects']}</b> son colaborativos."
    )

    _metric("Total proyectos", data["total_projects"])
    _metric("Proyectos grandes (>10 MB)", data["large_projects"])
    _metric("Proyectos inactivos (>90 días)", data["inactive_projects"])
    _metric("Proyectos colaborativos", data["collaborative_projects"])
    _after_metrics()

    if data["top_projects_size"]:
        _table_intro("<b>Top proyectos por tamaño:</b>")
        _ranking_note()
        tp_rows = [
            [_smart_truncate(p["name"], 50),
             _smart_truncate(p["owner_email"], 40),
             p["size_fmt"]]
            for p in data["top_projects_size"][:5]
        ]
        flowables.append(_gen_table(
            ["Proyecto", "Propietario", "Tamaño"],
            tp_rows,
            col_pcts=[0.45, 0.35, 0.20],
        ))
        _after_table()

    # ══════════════════════════════════════════════════════════════════════
    # 4. Almacenamiento y cuotas
    # ══════════════════════════════════════════════════════════════════════
    _heading("4. Almacenamiento y cuotas")

    _narrative(
        f"El almacenamiento total consumido es de "
        f"<b>{data['total_storage_fmt']}</b>, con una media de "
        f"<b>{data['avg_storage_per_user_fmt']}</b> por usuario y "
        f"<b>{data['avg_storage_per_project_fmt']}</b> por proyecto."
    )

    _metric("Total consumido", data["total_storage_fmt"])
    _metric("Media por usuario", data["avg_storage_per_user_fmt"])
    _metric("Media por proyecto", data["avg_storage_per_project_fmt"])
    _after_metrics()

    if data["top_users_storage"]:
        _table_intro("<b>Top usuarios por almacenamiento:</b>")
        _ranking_note()
        tu_rows = [
            [_smart_truncate(u["email"], 50), u["used_fmt"]]
            for u in data["top_users_storage"][:5]
        ]
        flowables.append(_gen_table(
            ["Email", "Espacio usado"],
            tu_rows,
            col_pcts=[0.70, 0.30],
        ))
        _after_table()

    # ══════════════════════════════════════════════════════════════════════
    # 5. Sincronización
    # ══════════════════════════════════════════════════════════════════════
    _heading("5. Sincronización")

    sync_narr = (
        f"Se han ejecutado <b>{data['total_syncs']}</b> sincronizaciones "
        f"en total, con un <b>{data['success_pct']}%</b> de ejecuciones "
        f"correctas."
    )
    if data["avg_sync_duration"]:
        sync_narr += (
            f" La duración media por ejecución es de "
            f"<b>{data['avg_sync_duration']} s</b>."
        )
    _narrative(sync_narr)

    _metric("Total ejecuciones", data["total_syncs"])
    _metric("% correctas", f"{data['success_pct']}%")
    _metric("Duración media",
            f"{data['avg_sync_duration']} s" if data["avg_sync_duration"] else "N/A")
    _after_metrics()

    if data["last_sync"]:
        ls = data["last_sync"]
        _metric("Última sincronización", _ts_short(ls.started_at))
        _metric("Estado", ls.status)
        _after_metrics()

    if data["failed_syncs_recent"]:
        _table_intro(
            f'<font color="{_RED.hexval()}"><b>Últimas sincronizaciones '
            f"fallidas:</b></font>"
        )
        fail_rows = [
            [_ts_short(sr.started_at), sr.triggered_by,
             _smart_truncate(sr.message or "", 120)]
            for sr in data["failed_syncs_recent"][:5]
        ]
        flowables.append(_gen_table(
            ["Fecha", "Iniciado por", "Mensaje"],
            fail_rows,
            col_pcts=[0.22, 0.18, 0.60],
        ))
        _after_table()

    # ══════════════════════════════════════════════════════════════════════
    # 6. Auditoría e incidencias
    # ══════════════════════════════════════════════════════════════════════
    _heading("6. Auditoría e incidencias")

    _narrative(
        f"En las últimas 24 horas se han registrado "
        f"<b>{data['active_alerts_count']}</b> alertas (errores y avisos)."
    )
    _metric("Alertas activas (24 h)", data["active_alerts_count"])
    _after_metrics()

    if data["recent_errors"]:
        _subheading("6.1 Errores y avisos recientes")
        err_rows = [
            [_ts_short(e.created_at), e.level, e.actor,
             _translate_action(e.action),
             _smart_truncate(e.detail or "", 120)]
            for e in data["recent_errors"][:5]
        ]
        flowables.append(_gen_table(
            ["Fecha", "Nivel", "Actor", "Acción", "Detalle"],
            err_rows,
            col_pcts=[0.15, 0.08, 0.15, 0.22, 0.40],
        ))
        _after_table()

    if data["recent_role_changes"]:
        _subheading("6.2 Cambios de rol/cuota recientes")
        rc_rows = []
        for rc in data["recent_role_changes"][:5]:
            rc_rows.append([
                _ts_short(rc.changed_at),
                rc.changed_by,
                _translate_action(rc.action),
                rc.role_from.name if rc.role_from else "",
                rc.role_to.name if rc.role_to else "",
            ])
        flowables.append(_gen_table(
            ["Fecha", "Administrador", "Acción", "Rol anterior", "Rol nuevo"],
            rc_rows,
            col_pcts=[0.18, 0.20, 0.24, 0.19, 0.19],
        ))
        _after_table()

    # ── Build PDF with differentiated first / later page ─────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf,
        pagesize=A4,
        topMargin=42 * mm,    # room for cover header on first page
        bottomMargin=16 * mm,
        leftMargin=_MARGIN_L,
        rightMargin=_MARGIN_R,
        title="Informe general de la plataforma",
    )

    def _on_first(canvas, doc):
        _general_first_page(canvas, doc, generated_by)

    def _on_later(canvas, doc):
        _general_later_pages(canvas, doc, generated_by)

    doc.build(flowables, onFirstPage=_on_first, onLaterPages=_on_later)
    pdf_data = buf.getvalue()
    return pdf_data, f"informe_general_{_today_suffix()}.pdf", "application/pdf"
