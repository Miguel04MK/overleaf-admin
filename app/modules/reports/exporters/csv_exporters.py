"""
exporters/csv_exporters.py
---------------------------
CSV row builders and individual CSV export functions.
"""
from __future__ import annotations

import csv
import io

from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.audit_log import AuditLog
from app.model.entities.sync_run import SyncRun

from ._helpers import _make_csv, _today_suffix, _ts, _date, _fmt_bytes


# ═══════════════════════════════════════════════════════════════════════════════
# Row builders  (shared with individual exporters and bundle)
# ═══════════════════════════════════════════════════════════════════════════════

def _build_users_csv_rows(users) -> list[list]:
    header = [
        "ID", "Email", "Nombre", "Apellidos", "Admin", "Rol",
        "Cuota asignada (bytes)", "Cuota usada (bytes)",
        "% Uso", "Proyectos propietario", "Proyectos colaborador",
        "Fecha alta", "Último acceso",
    ]
    rows = [header]
    for u in users:
        rows.append([
            u.overleaf_id, u.email or "", u.first_name or "", u.last_name or "",
            "Sí" if u.is_admin else "No",
            u.role.name if u.role else "",
            u.max_quota_bytes if u.max_quota_bytes is not None else "Sin límite",
            u.quota_used_bytes, u.quota_percent if u.quota_percent is not None else "",
            u.projects_owned.count(), u.memberships.count(),
            _date(u.signup_date), _ts(u.last_login_at),
        ])
    return rows


def _build_projects_csv_rows(projects) -> list[list]:
    header = ["ID", "Nombre", "Propietario (email)", "Tamaño", "Archivos", "Miembros", "Creado", "Última actualización"]
    rows = [header]
    for p in projects:
        rows.append([
            p.overleaf_id, p.name or "",
            p.owner.email if p.owner else p.owner_overleaf_id or "",
            _fmt_bytes(p.size_bytes),
            p.file_count if p.file_count is not None else "",
            p.members.count() if p.members else 0,
            _date(p.created_at), _date(p.last_updated_at),
        ])
    return rows


def _build_storage_csv_rows(rows_data) -> list[list]:
    header = ["Email", "Nombre", "Cuota asignada", "Espacio usado", "% Uso", "Num proyectos"]
    rows = [header]
    for r in rows_data:
        u = r["user"]
        rows.append([
            u.email or "", u.display_name, r["quota_fmt"], r["used_fmt"],
            r["quota_pct"] if r["quota_pct"] is not None else "Sin límite",
            r["proj_count"],
        ])
    return rows


def _build_quotas_csv_rows(rows_data) -> list[list]:
    header = [
        "Email", "Nombre", "Rol", "Cuota asignada", "Espacio usado",
        "% Uso", "Estado", "Proyectos", "Límite proyectos", "Excede límite proyectos",
    ]
    rows = [header]
    for r in rows_data:
        u = r["user"]
        rows.append([
            u.email or "", u.display_name, r["role_name"],
            r["quota_fmt"], r["used_fmt"],
            r["pct"] if r["pct"] is not None else "",
            r["status"], r["projects_count"],
            r["max_projects"] if r["max_projects"] is not None else "Sin límite",
            "Sí" if r["exceeds_project_limit"] else "No",
        ])
    return rows


def _build_activity_csv_rows(entries) -> list[list]:
    header = ["Fecha/Hora", "Actor", "Acción", "Nivel", "IP", "Detalle"]
    rows = [header]
    for e in entries:
        rows.append([_ts(e.created_at), e.actor, e.action, e.level, e.ip_address or "", e.detail or ""])
    return rows


def _build_incidents_csv_rows(entries) -> list[list]:
    header = ["Fecha/Hora", "Nivel", "Actor", "Acción", "Detalle", "IP"]
    rows = [header]
    for e in entries:
        rows.append([_ts(e.created_at), e.level, e.actor, e.action, e.detail or "", e.ip_address or ""])
    return rows


def _build_syncs_csv_rows(runs) -> list[list]:
    header = [
        "ID", "Estado", "Iniciado por", "Inicio", "Fin", "Duración (s)",
        "Usuarios encontrados", "Usuarios sincronizados",
        "Proyectos encontrados", "Proyectos sincronizados",
        "Delta usuarios", "Delta proyectos", "Mensaje",
    ]
    rows = [header]
    for r in runs:
        rows.append([
            r.id, r.status, r.triggered_by,
            _ts(r.started_at), _ts(r.finished_at),
            r.duration_seconds if r.duration_seconds is not None else "",
            r.users_found, r.users_synced, r.projects_found, r.projects_synced,
            r.users_delta if r.users_delta is not None else "",
            r.projects_delta if r.projects_delta is not None else "",
            r.message or "",
        ])
    return rows


def _build_general_csv_rows(data) -> list[list]:
    return [
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


# ═══════════════════════════════════════════════════════════════════════════════
# Individual CSV exporters
# ═══════════════════════════════════════════════════════════════════════════════

def export_users_csv(users: list[OverleafUser]) -> tuple[bytes, str, str]:
    return _make_csv(f"informe_usuarios_{_today_suffix()}.csv", _build_users_csv_rows(users))


def export_projects_csv(projects: list[OverleafProject]) -> tuple[bytes, str, str]:
    return _make_csv(f"informe_proyectos_{_today_suffix()}.csv", _build_projects_csv_rows(projects))


def export_storage_csv(rows_data: list[dict]) -> tuple[bytes, str, str]:
    return _make_csv(f"informe_almacenamiento_{_today_suffix()}.csv", _build_storage_csv_rows(rows_data))


def export_activity_csv(entries: list[AuditLog]) -> tuple[bytes, str, str]:
    return _make_csv(f"informe_actividad_{_today_suffix()}.csv", _build_activity_csv_rows(entries))


def export_syncs_csv(runs: list[SyncRun]) -> tuple[bytes, str, str]:
    return _make_csv(f"informe_sincronizaciones_{_today_suffix()}.csv", _build_syncs_csv_rows(runs))


def export_quotas_csv(rows_data: list[dict]) -> tuple[bytes, str, str]:
    return _make_csv(f"informe_cuotas_{_today_suffix()}.csv", _build_quotas_csv_rows(rows_data))


def export_incidents_csv(entries: list[AuditLog]) -> tuple[bytes, str, str]:
    return _make_csv(f"informe_incidencias_{_today_suffix()}.csv", _build_incidents_csv_rows(entries))


def export_general_csv(data: dict) -> tuple[bytes, str, str]:
    """Flat CSV summary of the general platform report."""
    return _make_csv(f"informe_general_{_today_suffix()}.csv", _build_general_csv_rows(data))


# ═══════════════════════════════════════════════════════════════════════════════
# Bundle CSV exporters
# ═══════════════════════════════════════════════════════════════════════════════

def export_all_csv_zip(all_data: dict) -> tuple[bytes, str, str]:
    """Bundle every individual CSV export into a single ZIP file."""
    import io
    import zipfile

    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        entries: list[tuple[str, bytes]] = []

        data, fname, _ = export_users_csv(all_data["users"])
        entries.append((fname, data))

        data, fname, _ = export_projects_csv(all_data["projects"])
        entries.append((fname, data))

        data, fname, _ = export_storage_csv(all_data["storage_rows"])
        entries.append((fname, data))

        data, fname, _ = export_quotas_csv(all_data["quotas"])
        entries.append((fname, data))

        data, fname, _ = export_activity_csv(all_data["activity"])
        entries.append((fname, data))

        data, fname, _ = export_incidents_csv(all_data["incidents"])
        entries.append((fname, data))

        data, fname, _ = export_syncs_csv(all_data["syncs"])
        entries.append((fname, data))

        data, fname, _ = export_general_csv(all_data["general"])
        entries.append((fname, data))

        for fname, content in entries:
            zf.writestr(fname, content)

    filename = f"informes_completos_{_today_suffix()}.zip"
    return buf.getvalue(), filename, "application/zip"


def export_all_csv_single(all_data: dict) -> tuple[bytes, str, str]:
    """One CSV file with every report as a labelled section."""
    buf = io.StringIO()
    w = csv.writer(buf)

    sections: list[tuple[str, list[list]]] = [
        ("USUARIOS",         _build_users_csv_rows(all_data["users"])),
        ("PROYECTOS",        _build_projects_csv_rows(all_data["projects"])),
        ("ALMACENAMIENTO",   _build_storage_csv_rows(all_data["storage_rows"])),
        ("CUOTAS",           _build_quotas_csv_rows(all_data["quotas"])),
        ("ACTIVIDAD",        _build_activity_csv_rows(all_data["activity"])),
        ("INCIDENCIAS",      _build_incidents_csv_rows(all_data["incidents"])),
        ("SINCRONIZACIONES", _build_syncs_csv_rows(all_data["syncs"])),
        ("GENERAL",          _build_general_csv_rows(all_data["general"])),
    ]

    first = True
    for section_name, rows in sections:
        if not first:
            w.writerow([])
        first = False
        w.writerow([f"=== {section_name} ==="])
        for row in rows:
            w.writerow(row)

    filename = f"informe_completo_{_today_suffix()}.csv"
    return buf.getvalue().encode("utf-8-sig"), filename, "text/csv; charset=utf-8"
