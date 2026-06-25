"""
exporters/pdf_general.py
-------------------------
General platform report PDF — the comprehensive multi-section document.
Includes its own page-callback helpers and full-width table builders
that are specific to the general report layout.
"""
from __future__ import annotations

import io
from datetime import datetime

from reportlab.lib import colors
from reportlab.lib.pagesizes import A4
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import (
    SimpleDocTemplate, Paragraph, Spacer, Table, TableStyle,
    HRFlowable, KeepTogether,
)

from ._helpers import _today_suffix, _ts_short, _fmt_bytes
from .pdf_base import (
    _pdf_styles, _metric_pair,
    _TEXT, _TEXT_SECONDARY, _GREEN, _GREEN_SOFT, _RED, _AMBER,
    _ROW_ALT, _BORDER, _RULE,
    _MARGIN_L, _MARGIN_R, _CONTENT_W,
)
from .pdf_sections import (
    _LEVEL_LABELS, _TYPE_LABELS, _ENTITY_TYPE_LABELS,
    _format_extra_data, _smart_truncate as _trunc_section,
)


_RANKING_NOTE_TEXT = "Se muestran los 5 registros más relevantes."


def _translate_action(action: str | None) -> str:
    """Etiqueta legible para una acción. Reutiliza el mapeo canónico de
    admin_service.ACTION_LABELS (incluye los 28 actions: login/logout,
    cambios admin, quota_change, sync_*, role_*, etc.). Si no encaja,
    devuelve la acción tal cual.
    """
    if not action:
        return ""
    from app.model.services.admin import admin_service as _audit
    return _audit.label_for_action(action)


def _action_translations_view() -> dict[str, str]:
    """Snapshot del mapeo de acciones → etiqueta legible. Se construye al
    importar el módulo y se exporta como `_ACTION_TRANSLATIONS` para
    compatibilidad con código que ya lo importaba (ver exporters/__init__.py).
    """
    from app.model.services.admin import admin_service as _audit
    return dict(_audit.ACTION_LABELS)


# Compatibilidad hacia atrás: el módulo solía exponer un dict literal con las
# traducciones de actions. Ahora delegamos en admin_service.ACTION_LABELS, que
# es la fuente única (idéntico al usado en /auditoria/).
_ACTION_TRANSLATIONS: dict[str, str] = _action_translations_view()


def _smart_truncate(text: str, max_len: int = 60) -> str:
    if not text or len(text) <= max_len:
        return text or ""
    truncated = text[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len * 0.4:
        return truncated[:last_space] + "…"
    return truncated + "…"


# ─── Narrative summary ────────────────────────────────────────────────────────

def _build_narrative_summary(data: dict) -> str:
    parts = []

    parts.append(
        f"La plataforma cuenta con <b>{data['total_users']}</b> usuarios "
        f"sincronizados y <b>{data['total_projects']}</b> proyectos, "
        f"con un almacenamiento total de <b>{data['total_storage_fmt']}</b>."
    )

    n_exceeded = len(data["users_exceeded_quota"])
    n_near     = len(data["users_near_quota"])
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

    if data["total_syncs"] > 0 and data["last_sync"]:
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
        parts.append("No se han registrado alertas en las últimas 24 horas.")

    return " ".join(parts)


# ─── Page callbacks ───────────────────────────────────────────────────────────

def _general_first_page(canvas, doc, generated_by: str):
    canvas.saveState()
    w, h = A4

    canvas.setStrokeColor(_GREEN)
    canvas.setLineWidth(1.8)
    canvas.line(_MARGIN_L, h - 12 * mm, w - _MARGIN_R, h - 12 * mm)

    canvas.setFont("Helvetica-Bold", 20)
    canvas.setFillColor(_TEXT)
    canvas.drawString(_MARGIN_L, h - 22 * mm, "Informe general de la plataforma")

    canvas.setFont("Helvetica", 9.5)
    canvas.setFillColor(_TEXT_SECONDARY)
    canvas.drawString(_MARGIN_L, h - 28 * mm,
                      "Overleaf Community — Panel de administración")

    canvas.setFont("Helvetica", 8)
    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    canvas.drawString(_MARGIN_L, h - 35 * mm, f"Generado: {now_str}")
    canvas.drawString(90 * mm, h - 35 * mm, f"Usuario: {generated_by}")
    canvas.setFillColor(_GREEN)
    canvas.drawRightString(w - _MARGIN_R, h - 35 * mm, "● Informe completo")

    canvas.setStrokeColor(_RULE)
    canvas.setLineWidth(0.4)
    canvas.line(_MARGIN_L, h - 38 * mm, w - _MARGIN_R, h - 38 * mm)

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_TEXT_SECONDARY)
    canvas.drawString(_MARGIN_L, 10 * mm, f"Generado: {now_str}")
    canvas.drawRightString(w - _MARGIN_R, 10 * mm, f"Página {doc.page}")

    canvas.restoreState()


def _general_later_pages(canvas, doc, generated_by: str):
    canvas.saveState()
    w, h = A4

    canvas.setStrokeColor(_RULE)
    canvas.setLineWidth(0.4)
    canvas.line(_MARGIN_L, h - 13 * mm, w - _MARGIN_R, h - 13 * mm)

    canvas.setFont("Helvetica", 8)
    canvas.setFillColor(_TEXT_SECONDARY)
    canvas.drawString(_MARGIN_L, h - 11.5 * mm,
                      "Informe general — Overleaf Admin")
    canvas.drawRightString(w - _MARGIN_R, h - 11.5 * mm,
                           f"Generado por: {generated_by}")

    now_str = datetime.now().strftime("%d/%m/%Y %H:%M")
    canvas.drawString(_MARGIN_L, 10 * mm, f"Generado: {now_str}")
    canvas.drawRightString(w - _MARGIN_R, 10 * mm, f"Página {doc.page}")

    canvas.restoreState()


# ─── Full-width table helpers ─────────────────────────────────────────────────

def _gen_table(headers: list[str], rows: list[list], col_pcts: list[float]) -> Table:
    """Full-width table using percentage-based column widths."""
    styles = _pdf_styles()
    col_widths = [_CONTENT_W * p for p in col_pcts]

    table_data = [[Paragraph(h, styles["CellHeader"]) for h in headers]]
    for row in rows:
        table_data.append([Paragraph(str(cell), styles["CellText"]) for cell in row])

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
        ("ALIGN", (1, 0), (1, -1), "RIGHT"),
    ]))
    return t


# ═══════════════════════════════════════════════════════════════════════════════
# Main export function
# ═══════════════════════════════════════════════════════════════════════════════

def export_general_pdf(data: dict, generated_by: str = "system") -> tuple[bytes, str, str]:
    """Build the comprehensive general platform report PDF."""
    styles = _pdf_styles()

    # Extra styles for this report only
    styles.add(ParagraphStyle(
        "Narrative",
        parent=styles["Normal"],
        fontSize=10.5, leading=15,
        spaceBefore=4, spaceAfter=10,
        textColor=_TEXT,
    ))
    styles.add(ParagraphStyle(
        "RankingNote",
        parent=styles["Normal"],
        fontSize=8.5, leading=11,
        textColor=_TEXT_SECONDARY,
        spaceBefore=2, spaceAfter=4,
        fontName="Helvetica-Oblique",
    ))
    styles.add(ParagraphStyle(
        "SubSectionHeading",
        parent=styles["Normal"],
        fontSize=10.5, leading=14,
        textColor=_TEXT,
        spaceBefore=14, spaceAfter=6,
        fontName="Helvetica-Bold",
    ))
    styles.add(ParagraphStyle(
        "TableIntro",
        parent=styles["Normal"],
        fontSize=10.5, leading=14,
        spaceBefore=8, spaceAfter=6,
        textColor=_TEXT,
    ))

    flowables: list = []

    # ── Shorthand helpers ────────────────────────────────────────────────

    def _heading(text: str):
        block = [
            Spacer(1, 18),
            HRFlowable(width="100%", thickness=0.4, color=_RULE,
                       spaceAfter=4, spaceBefore=0),
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
        flowables.append(Spacer(1, 16))

    def _after_metrics():
        flowables.append(Spacer(1, 10))

    # ══════════════════════════════════════════════════════════════════════
    # 1. Resumen
    # ══════════════════════════════════════════════════════════════════════
    _heading("1. Resumen")
    _narrative(_build_narrative_summary(data))

    summary_rows = [
        ["Usuarios sincronizados",       str(data["total_users"])],
        ["Proyectos sincronizados",      str(data["total_projects"])],
        ["Administradores internos",     str(data["total_admins_internal"])],
        ["Roles definidos",              str(data["total_roles"])],
        ["Almacenamiento total",         data["total_storage_fmt"]],
        ["Sincronizaciones totales",     str(data["total_syncs"])],
        ["% sincronizaciones correctas", f"{data['success_pct']}%"],
        ["Alertas activas (24 h)",       str(data["active_alerts_count"])],
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
        flowables.append(_gen_table(["Rol", "Usuarios"], role_rows, col_pcts=[0.65, 0.35]))
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
            ["Email", "Usado", "Cuota", "% Uso"], exc_rows,
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
            ["Email", "Usado", "Cuota", "% Uso"], near_rows,
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
            ["Proyecto", "Propietario", "Tamaño"], tp_rows,
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
            ["Email", "Espacio usado"], tu_rows,
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
            ["Fecha", "Iniciado por", "Mensaje"], fail_rows,
            col_pcts=[0.22, 0.18, 0.60],
        ))
        _after_table()

    # ══════════════════════════════════════════════════════════════════════
    # 6. Incidencias y alertas
    # ══════════════════════════════════════════════════════════════════════
    _heading("6. Incidencias y alertas")

    alerts_total      = data.get("system_alerts_total", 0)
    alerts_unresolved = data.get("system_alerts_unresolved", 0)
    alerts_critical   = data.get("system_alerts_critical", 0)
    alerts_active     = data.get("system_alerts_active", [])

    if alerts_unresolved > 0:
        narr_6 = (
            f"Se han registrado <b>{alerts_total}</b> alertas en el sistema. "
            f"De ellas, <b>{alerts_unresolved}</b> permanecen sin resolver"
        )
        if alerts_critical > 0:
            narr_6 += (
                f', de las cuales <font color="{_RED.hexval()}">'
                f"<b>{alerts_critical}</b> son de nivel crítico o peligro</font>"
            )
        narr_6 += "."
    else:
        narr_6 = (
            f'<font color="{_GREEN.hexval()}">No hay alertas activas '
            f"en el sistema.</font> Se han registrado "
            f"<b>{alerts_total}</b> alertas en total, todas resueltas."
        )
    _narrative(narr_6)

    _metric("Alertas totales", alerts_total)
    _metric("Sin resolver", alerts_unresolved)
    _metric("Críticas / Peligro", alerts_critical)
    _after_metrics()

    if alerts_active:
        _subheading("6.1 Alertas activas")
        alert_rows = []
        for a in alerts_active[:10]:
            entity = _ENTITY_TYPE_LABELS.get(a.entity_type, a.entity_type or "")
            if a.entity_id:
                entity += f" ({a.entity_id})"
            alert_rows.append([
                _ts_short(a.created_at),
                _LEVEL_LABELS.get(a.level, a.level),
                _TYPE_LABELS.get(a.type, a.type),
                _smart_truncate(a.title, 40),
                entity,
            ])
        flowables.append(_gen_table(
            ["Fecha", "Nivel", "Tipo", "Título", "Entidad"],
            alert_rows,
            col_pcts=[0.14, 0.10, 0.18, 0.34, 0.24],
        ))
        _after_table()

        # Detail sub-table with messages and extra data
        alerts_with_detail = [a for a in alerts_active[:10] if a.message or a.extra_data]
        if alerts_with_detail:
            _subheading("6.2 Detalle de alertas activas")
            detail_rows = []
            for a in alerts_with_detail:
                detail_rows.append([
                    _smart_truncate(a.title, 30),
                    _smart_truncate(a.message or "", 50),
                    _smart_truncate(_format_extra_data(a), 50),
                ])
            flowables.append(_gen_table(
                ["Título", "Mensaje", "Datos adicionales"],
                detail_rows,
                col_pcts=[0.25, 0.40, 0.35],
            ))
            _after_table()

    # 6.3 Desglose de auditoría por categoría
    if data.get("audit_by_category"):
        _subheading("6.3 Eventos de auditoría por categoría")
        cat_rows = [[c["label"], c["count"]] for c in data["audit_by_category"]]
        flowables.append(_gen_table(
            ["Categoría", "Eventos"], cat_rows,
            col_pcts=[0.60, 0.40],
        ))
        _after_table()

    if data["recent_errors"]:
        _subheading("6.4 Errores y avisos recientes en auditoría")
        err_rows = [
            [_ts_short(e.created_at), e.level, e.actor,
             _translate_action(e.action),
             _smart_truncate(e.detail or "", 120)]
            for e in data["recent_errors"][:5]
        ]
        flowables.append(_gen_table(
            ["Fecha", "Nivel", "Actor", "Acción", "Detalle"], err_rows,
            col_pcts=[0.15, 0.08, 0.15, 0.22, 0.40],
        ))
        _after_table()

    if data["recent_role_changes"]:
        _subheading("6.5 Cambios de rol/cuota recientes")
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

    # ── Build PDF ────────────────────────────────────────────────────────
    buf = io.BytesIO()
    doc = SimpleDocTemplate(
        buf, pagesize=A4,
        topMargin=42 * mm,
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
    return buf.getvalue(), f"informe_general_{_today_suffix()}.pdf", "application/pdf"
