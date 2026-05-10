"""
exporters/pdf_sections.py
--------------------------
Section helpers and individual PDF exporters for the 7 standard reports:
users, projects, storage, quotas, activity, incidents, syncs.

Each report exposes:
  _XXX_section(data) -> list[flowable]   (used by bundle exporter too)
  export_XXX_pdf(data, ...) -> (bytes, filename, content_type)
"""
from __future__ import annotations

from reportlab.platypus import Paragraph, Spacer

from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.audit_log import AuditLog
from app.model.entities.sync_run import SyncRun

from ._helpers import _today_suffix, _ts, _date, _fmt_bytes
from .pdf_base import _pdf_styles, _build_pdf, _make_table, _metric_pair


# ─── Users ───────────────────────────────────────────────────────────────────

def _users_section(users: list[OverleafUser]) -> list:
    styles = _pdf_styles()
    fl = [
        Paragraph(f"Total usuarios: <b>{len(users)}</b>", styles["Normal"]),
        Spacer(1, 6),
    ]
    headers = ["Email", "Nombre", "Rol", "Admin", "Cuota usada", "% Uso", "Alta", "Últ. acceso"]
    rows = [[
        u.email or u.overleaf_id, u.display_name,
        u.role.name if u.role else "",
        "Sí" if u.is_admin else "No",
        u.quota_used_fmt,
        f"{u.quota_percent}%" if u.quota_percent is not None else "",
        _date(u.signup_date), _date(u.last_login_at),
    ] for u in users]
    fl.append(_make_table(headers, rows, col_widths=[90, 70, 50, 30, 60, 35, 55, 60]))
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
        Paragraph(f"Total proyectos: <b>{len(projects)}</b>", styles["Normal"]),
        Spacer(1, 6),
    ]
    headers = ["Nombre", "Propietario", "Tamaño", "Archivos", "Miembros", "Creado", "Últ. act."]
    rows = [[
        (p.name or "")[:40],
        (p.owner.email if p.owner else "")[:30],
        _fmt_bytes(p.size_bytes),
        p.file_count or "",
        p.members.count() if p.members else 0,
        _date(p.created_at),
        _date(p.last_updated_at),
    ] for p in projects]
    fl.append(_make_table(headers, rows, col_widths=[100, 80, 55, 40, 40, 55, 55]))
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
            Spacer(1, 8),
        ]
    headers = ["Email", "Nombre", "Cuota", "Usado", "% Uso", "Proyectos"]
    rows = [[
        (r["user"].email or "")[:35],
        r["user"].display_name[:25],
        r["quota_fmt"], r["used_fmt"],
        f"{r['quota_pct']}%" if r["quota_pct"] is not None else "Sin límite",
        r["proj_count"],
    ] for r in rows_data]
    fl.append(_make_table(headers, rows, col_widths=[100, 80, 65, 65, 50, 45]))
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
        Paragraph(f"Total usuarios: <b>{len(rows_data)}</b>", styles["Normal"]),
        Spacer(1, 6),
    ]
    headers = ["Email", "Rol", "Cuota", "Usado", "% Uso", "Estado", "Proy.", "Limite", "Excede proy."]
    rows = [[
        (r["user"].email or "")[:30],
        r["role_name"][:12],
        r["quota_fmt"], r["used_fmt"],
        f"{r['pct']}%" if r["pct"] is not None else "",
        r["status"], r["projects_count"],
        r["max_projects"] if r["max_projects"] is not None else "Sin lím.",
        "Sí" if r["exceeds_project_limit"] else "No",
    ] for r in rows_data]
    fl.append(_make_table(headers, rows, col_widths=[80, 40, 50, 50, 35, 42, 28, 35, 42]))
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
        Paragraph(f"Total entradas: <b>{len(entries)}</b>", styles["Normal"]),
        Spacer(1, 6),
    ]
    headers = ["Fecha", "Actor", "Acción", "Nivel", "IP", "Detalle"]
    rows = [[
        _ts(e.created_at), e.actor or "", e.action or "",
        e.level or "", e.ip_address or "", (e.detail or "")[:60],
    ] for e in entries]
    fl.append(_make_table(headers, rows, col_widths=[75, 55, 55, 35, 55, 150]))
    return fl


def export_activity_pdf(
    entries: list[AuditLog],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    data = _build_pdf("Informe de actividad administrativa", generated_by, _activity_section(entries), filters_text)
    return data, f"informe_actividad_{_today_suffix()}.pdf", "application/pdf"


# ─── Incidents ───────────────────────────────────────────────────────────────

def _incidents_section(entries: list[AuditLog]) -> list:
    styles = _pdf_styles()
    fl = [
        Paragraph(f"Total incidencias: <b>{len(entries)}</b>", styles["Normal"]),
        Spacer(1, 6),
    ]
    headers = ["Fecha", "Nivel", "Actor", "Acción", "Detalle"]
    rows = [[
        _ts(e.created_at), e.level or "", e.actor or "",
        e.action or "", (e.detail or "")[:80],
    ] for e in entries]
    fl.append(_make_table(headers, rows, col_widths=[75, 40, 55, 55, 200]))
    return fl


def export_incidents_pdf(
    entries: list[AuditLog],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    data = _build_pdf("Informe de incidencias", generated_by, _incidents_section(entries), filters_text)
    return data, f"informe_incidencias_{_today_suffix()}.pdf", "application/pdf"


# ─── Syncs ───────────────────────────────────────────────────────────────────

def _syncs_section(runs: list[SyncRun]) -> list:
    styles = _pdf_styles()
    fl = [
        Paragraph(f"Total ejecuciones: <b>{len(runs)}</b>", styles["Normal"]),
        Spacer(1, 6),
    ]
    headers = ["Inicio", "Fin", "Dur.(s)", "Estado", "Iniciado", "Us.enc.", "Us.sync.", "Pr.enc.", "Pr.sync."]
    rows = [[
        _ts(r.started_at), _ts(r.finished_at),
        f"{r.duration_seconds:.0f}" if r.duration_seconds else "",
        r.status, r.triggered_by,
        r.users_found, r.users_synced, r.projects_found, r.projects_synced,
    ] for r in runs]
    fl.append(_make_table(headers, rows, col_widths=[68, 68, 32, 38, 40, 32, 32, 32, 32]))
    return fl


def export_syncs_pdf(
    runs: list[SyncRun],
    generated_by: str = "system",
    filters_text: str | None = None,
) -> tuple[bytes, str, str]:
    data = _build_pdf("Informe de sincronizaciones", generated_by, _syncs_section(runs), filters_text)
    return data, f"informe_sincronizaciones_{_today_suffix()}.pdf", "application/pdf"
