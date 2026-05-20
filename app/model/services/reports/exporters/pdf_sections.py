"""
exporters/pdf_sections.py
--------------------------
Section helpers and individual PDF exporters for the 7 standard reports:
users, projects, storage, quotas, activity, incidents+alerts, syncs.

Each report exposes:
  _XXX_section(data) -> list[flowable]   (used by bundle exporter too)
  export_XXX_pdf(data, ...) -> (bytes, filename, content_type)
"""
from __future__ import annotations

import json as _json

from reportlab.platypus import Paragraph, Spacer

from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.audit_log import AuditLog
from app.model.entities.sync_run import SyncRun
from app.model.entities.system_alert import SystemAlert

from ._helpers import _today_suffix, _ts, _ts_short, _date, _fmt_bytes
from .pdf_base import (
    _pdf_styles, _build_pdf, _make_table, _metric_pair,
    _CONTENT_W, _TEXT, _TEXT_SECONDARY, _RED, _AMBER, _GREEN,
)


# ── Shared helpers ──────────────────────────────────────────────────────────

def _smart_truncate(text: str, max_len: int = 60) -> str:
    if not text or len(text) <= max_len:
        return text or ""
    truncated = text[:max_len]
    last_space = truncated.rfind(" ")
    if last_space > max_len * 0.4:
        return truncated[:last_space] + "…"
    return truncated + "…"


# ─── Users ───────────────────────────────────────────────────────────────────

def _users_section(users: list[OverleafUser]) -> list:
    styles = _pdf_styles()
    fl = [
        Paragraph(f"Total usuarios: <b>{len(users)}</b>", styles["MetricValue"]),
        Spacer(1, 8),
    ]
    headers = ["Email", "Nombre", "Rol", "Admin", "Cuota usada", "% Uso", "Alta", "Últ. acceso"]
    rows = [[
        _smart_truncate(u.email or u.overleaf_id, 35),
        _smart_truncate(u.display_name, 22),
        u.role.name if u.role else "",
        "Sí" if u.is_admin else "No",
        u.quota_used_fmt,
        f"{u.quota_percent}%" if u.quota_percent is not None else "",
        _date(u.signup_date),
        _date(u.last_login_at),
    ] for u in users]
    fl.append(_make_table(
        headers, rows,
        col_pcts=[0.21, 0.15, 0.10, 0.06, 0.13, 0.08, 0.13, 0.14],
    ))
    return fl


def export_users_pdf(
    users: list[OverleafUser],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    data = _build_pdf("Informe de usuarios", generated_by, _users_section(users), filters_text)
    return data, f"informe_usuarios_{_today_suffix()}.pdf", "application/pdf"


# ─── Projects ────────────────────────────────────────────────────────────────

def _projects_section(projects: list[OverleafProject]) -> list:
    styles = _pdf_styles()
    fl = [
        Paragraph(f"Total proyectos: <b>{len(projects)}</b>", styles["MetricValue"]),
        Spacer(1, 8),
    ]
    headers = ["Nombre", "Propietario", "Tamaño", "Archivos", "Miembros", "Creado", "Últ. act."]
    rows = [[
        _smart_truncate(p.name or "", 40),
        _smart_truncate(p.owner.email if p.owner else "", 30),
        _fmt_bytes(p.size_bytes),
        p.file_count or "",
        p.members.count() if p.members else 0,
        _date(p.created_at),
        _date(p.last_updated_at),
    ] for p in projects]
    fl.append(_make_table(
        headers, rows,
        col_pcts=[0.24, 0.20, 0.12, 0.08, 0.08, 0.14, 0.14],
    ))
    return fl


def export_projects_pdf(
    projects: list[OverleafProject],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    data = _build_pdf("Informe de proyectos", generated_by, _projects_section(projects), filters_text)
    return data, f"informe_proyectos_{_today_suffix()}.pdf", "application/pdf"


# ─── Storage ─────────────────────────────────────────────────────────────────

def _storage_section(rows_data: list[dict], totals: dict | None = None) -> list:
    fl = []
    if totals:
        fl += [
            _metric_pair("Total consumido", totals.get("total_bytes_fmt", "")),
            _metric_pair("Media por usuario", totals.get("avg_per_user_fmt", "")),
            _metric_pair("Media por proyecto", totals.get("avg_per_project_fmt", "")),
            Spacer(1, 10),
        ]
    headers = ["Email", "Nombre", "Cuota", "Usado", "% Uso", "Proyectos"]
    rows = [[
        _smart_truncate(r["user"].email or "", 35),
        _smart_truncate(r["user"].display_name, 22),
        r["quota_fmt"], r["used_fmt"],
        f"{r['quota_pct']}%" if r["quota_pct"] is not None else "Sin límite",
        r["proj_count"],
    ] for r in rows_data]
    fl.append(_make_table(
        headers, rows,
        col_pcts=[0.25, 0.18, 0.15, 0.15, 0.12, 0.15],
    ))
    return fl


def export_storage_pdf(
    rows_data: list[dict],
    totals: dict | None = None,
    generated_by: str = "system",
) -> tuple[bytes, str, str]:
    data = _build_pdf("Informe de almacenamiento", generated_by, _storage_section(rows_data, totals))
    return data, f"informe_almacenamiento_{_today_suffix()}.pdf", "application/pdf"


# ─── Quotas ──────────────────────────────────────────────────────────────────

def _quotas_section(rows_data: list[dict]) -> list:
    styles = _pdf_styles()
    fl = [
        Paragraph(f"Total usuarios: <b>{len(rows_data)}</b>", styles["MetricValue"]),
        Spacer(1, 8),
    ]
    headers = ["Email", "Rol", "Cuota", "Usado", "% Uso", "Estado", "Proy.", "Límite", "Excede"]
    rows = [[
        _smart_truncate(r["user"].email or "", 28),
        r["role_name"][:15],
        r["quota_fmt"], r["used_fmt"],
        f"{r['pct']}%" if r["pct"] is not None else "",
        r["status"], r["projects_count"],
        r["max_projects"] if r["max_projects"] is not None else "Sin lím.",
        "Sí" if r["exceeds_project_limit"] else "No",
    ] for r in rows_data]
    fl.append(_make_table(
        headers, rows,
        col_pcts=[0.20, 0.10, 0.12, 0.12, 0.08, 0.10, 0.08, 0.10, 0.10],
    ))
    return fl


def export_quotas_pdf(
    rows_data: list[dict],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    data = _build_pdf("Informe de cuotas", generated_by, _quotas_section(rows_data), filters_text)
    return data, f"informe_cuotas_{_today_suffix()}.pdf", "application/pdf"


# ─── Activity ────────────────────────────────────────────────────────────────

def _activity_section(entries: list[AuditLog]) -> list:
    styles = _pdf_styles()
    fl = [
        Paragraph(f"Total entradas: <b>{len(entries)}</b>", styles["MetricValue"]),
        Spacer(1, 8),
    ]
    headers = ["Fecha", "Actor", "Acción", "Nivel", "IP", "Detalle"]
    rows = [[
        _ts_short(e.created_at), e.actor or "", e.action or "",
        e.level or "", e.ip_address or "",
        _smart_truncate(e.detail or "", 60),
    ] for e in entries]
    fl.append(_make_table(
        headers, rows,
        col_pcts=[0.15, 0.12, 0.13, 0.08, 0.12, 0.40],
    ))
    return fl


def export_activity_pdf(
    entries: list[AuditLog],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    data = _build_pdf("Informe de actividad administrativa", generated_by, _activity_section(entries), filters_text)
    return data, f"informe_actividad_{_today_suffix()}.pdf", "application/pdf"


# ─── Syncs ───────────────────────────────────────────────────────────────────

def _syncs_section(runs: list[SyncRun]) -> list:
    styles = _pdf_styles()
    fl = [
        Paragraph(f"Total ejecuciones: <b>{len(runs)}</b>", styles["MetricValue"]),
        Spacer(1, 8),
    ]
    headers = [
        "Inicio", "Fin", "Dur.(s)", "Estado", "Iniciado",
        "Us. enc.", "Us. sync.", "Pr. enc.", "Pr. sync.",
    ]
    rows = [[
        _ts_short(r.started_at), _ts_short(r.finished_at),
        f"{r.duration_seconds:.0f}" if r.duration_seconds else "",
        r.status, r.triggered_by,
        r.users_found, r.users_synced, r.projects_found, r.projects_synced,
    ] for r in runs]
    fl.append(_make_table(
        headers, rows,
        col_pcts=[0.15, 0.15, 0.07, 0.09, 0.10, 0.09, 0.09, 0.09, 0.09],
    ))
    return fl


def export_syncs_pdf(
    runs: list[SyncRun],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    data = _build_pdf("Informe de sincronizaciones", generated_by, _syncs_section(runs), filters_text)
    return data, f"informe_sincronizaciones_{_today_suffix()}.pdf", "application/pdf"


# ─── Incidencias y alertas (merged) ─────────────────────────────────────────

_EXTRA_DATA_LABELS = {
    "email":            "Correo electrónico",
    "max_quota_bytes":  "Cuota máxima",
    "quota_percent":    "% de cuota usada",
    "sync_run_id":      "ID de sincronización",
    "status":           "Estado",
    "project_count":    "Nº de proyectos",
    "max_projects":     "Límite de proyectos",
    "error_count":      "Errores detectados",
    "hours":            "Ventana de tiempo (h)",
    "service_name":     "Nombre del servicio",
    "detail":           "Detalle",
}

_BYTE_FIELDS = {"max_quota_bytes"}

_ENTITY_TYPE_LABELS = {
    "user":     "Usuario",
    "project":  "Proyecto",
    "sync_run": "Sincronización",
    "service":  "Servicio",
}

_LEVEL_LABELS = {
    "info":     "Información",
    "warning":  "Aviso",
    "danger":   "Peligro",
    "critical": "Crítico",
}

_TYPE_LABELS = {
    "quota_warning":          "Cuota cercana",
    "quota_exceeded":         "Cuota excedida",
    "project_limit_warning":  "Proyectos cerca del límite",
    "project_limit_exceeded": "Límite de proyectos superado",
    "sync_failed":            "Fallo de sincronización",
    "service_down":           "Servicio caído",
    "repeated_errors":        "Errores repetidos",
    "many_projects":          "Muchos proyectos",
    "administrative_warning": "Aviso administrativo",
}


def _translate_extra_key(key: str) -> str:
    return _EXTRA_DATA_LABELS.get(key, key.replace("_", " ").capitalize())


def _format_extra_value(key: str, value) -> str:
    if key in _BYTE_FIELDS and isinstance(value, (int, float)):
        return _fmt_bytes(value)
    if isinstance(value, float):
        return f"{value:.1f}"
    return str(value) if value is not None else ""


def _format_extra_data(alert: SystemAlert) -> str:
    """Format extra_data dict as a readable multi-line string for PDF cells."""
    ed = alert.extra_data
    if not ed:
        return ""
    parts = []
    for k, v in ed.items():
        label = _translate_extra_key(k)
        val = _format_extra_value(k, v)
        parts.append(f"{label}: {val}")
    return "; ".join(parts)


def _incidents_alerts_section(
    incidents: list[AuditLog],
    alerts: list[SystemAlert],
) -> list:
    """Combined incidents + alerts section for individual and bundle PDFs."""
    styles = _pdf_styles()
    fl = []

    # ── Metrics ──────────────────────────────────────────────────────────
    total_alerts = len(alerts)
    active_alerts = sum(1 for a in alerts if not a.is_resolved)
    unread_alerts = sum(1 for a in alerts if not a.is_read)
    critical_alerts = sum(1 for a in alerts if a.level in ("critical", "danger"))

    fl.append(_metric_pair("Total alertas del sistema", total_alerts))
    fl.append(_metric_pair("Alertas activas (sin resolver)", active_alerts))
    fl.append(_metric_pair("Alertas no leídas", unread_alerts))
    fl.append(_metric_pair("Alertas críticas / peligro", critical_alerts))
    fl.append(_metric_pair("Incidencias en auditoría", len(incidents)))
    fl.append(Spacer(1, 12))

    # ── Alerts table ─────────────────────────────────────────────────────
    if alerts:
        fl.append(Paragraph("<b>Alertas del sistema</b>", styles["MetricValue"]))
        fl.append(Spacer(1, 6))

        alert_headers = [
            "Fecha", "Nivel", "Tipo", "Título",
            "Entidad", "Estado", "Leída",
        ]
        alert_rows = [[
            _ts_short(a.created_at),
            _LEVEL_LABELS.get(a.level, a.level),
            _TYPE_LABELS.get(a.type, a.type),
            _smart_truncate(a.title, 45),
            f"{_ENTITY_TYPE_LABELS.get(a.entity_type, a.entity_type or '')}"
            + (f" ({a.entity_id})" if a.entity_id else ""),
            "Resuelta" if a.is_resolved else "Activa",
            "Sí" if a.is_read else "No",
        ] for a in alerts]

        fl.append(_make_table(
            alert_headers, alert_rows,
            col_pcts=[0.12, 0.09, 0.14, 0.23, 0.18, 0.12, 0.12],
        ))
        fl.append(Spacer(1, 12))

        # Detail sub-table
        alerts_with_detail = [a for a in alerts if a.message or a.extra_data]
        if alerts_with_detail:
            fl.append(Paragraph("<b>Detalle de alertas</b>", styles["MetricValue"]))
            fl.append(Spacer(1, 6))

            detail_headers = ["Fecha", "Título", "Mensaje", "Datos adicionales", "Resolución"]
            detail_rows = []
            for a in alerts_with_detail:
                resolution = ""
                if a.is_resolved:
                    parts = []
                    if a.resolved_by:
                        parts.append(f"Por: {a.resolved_by}")
                    if a.resolved_at:
                        parts.append(_ts_short(a.resolved_at))
                    if a.resolution_comment:
                        parts.append(_smart_truncate(a.resolution_comment, 40))
                    resolution = "\n".join(parts) if parts else "Sí"

                detail_rows.append([
                    _ts_short(a.created_at),
                    _smart_truncate(a.title, 35),
                    _smart_truncate(a.message or "", 60),
                    _smart_truncate(_format_extra_data(a), 60),
                    resolution or "—",
                ])

            fl.append(_make_table(
                detail_headers, detail_rows,
                col_pcts=[0.12, 0.18, 0.28, 0.24, 0.18],
            ))
            fl.append(Spacer(1, 12))

    # ── Incidents table (audit log errors/warnings) ──────────────────────
    if incidents:
        fl.append(Paragraph(
            f"<b>Incidencias en auditoría ({len(incidents)})</b>",
            styles["MetricValue"],
        ))
        fl.append(Spacer(1, 6))

        inc_headers = ["Fecha", "Nivel", "Actor", "Acción", "Detalle"]
        inc_rows = [[
            _ts_short(e.created_at), e.level or "", e.actor or "",
            e.action or "", _smart_truncate(e.detail or "", 80),
        ] for e in incidents]
        fl.append(_make_table(
            inc_headers, inc_rows,
            col_pcts=[0.15, 0.08, 0.12, 0.15, 0.50],
        ))

    # ── Empty state ──────────────────────────────────────────────────────
    if not alerts and not incidents:
        fl.append(Paragraph(
            "No se han registrado alertas ni incidencias.",
            styles["MetricValue"],
        ))

    return fl


def export_incidents_alerts_pdf(
    incidents: list[AuditLog],
    alerts: list[SystemAlert],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    data = _build_pdf(
        "Informe de incidencias y alertas",
        generated_by,
        _incidents_alerts_section(incidents, alerts),
        filters_text,
    )
    return data, f"informe_incidencias_alertas_{_today_suffix()}.pdf", "application/pdf"


# ── Legacy aliases (backward compat for tests / imports) ─────────────────────

def _incidents_section(entries: list[AuditLog]) -> list:
    return _incidents_alerts_section(entries, [])


def export_incidents_pdf(
    entries: list[AuditLog],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    return export_incidents_alerts_pdf(entries, [], generated_by, filters_text)


def _alerts_section(alerts: list[SystemAlert]) -> list:
    return _incidents_alerts_section([], alerts)


def export_alerts_pdf(
    alerts: list[SystemAlert],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    return export_incidents_alerts_pdf([], alerts, generated_by, filters_text)
