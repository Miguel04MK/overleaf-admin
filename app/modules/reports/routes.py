"""
app/modules/reports/routes.py
-------------------------------
Blueprint for the Informes (Reports) module — /informes
"""
from __future__ import annotations

from flask import (
    Blueprint, render_template, request,
    redirect, url_for, make_response, jsonify,
)
from flask_login import login_required, current_user

from app.modules.reports import service
from app.modules.reports import exporters

reports_bp = Blueprint(
    "reports",
    __name__,
    url_prefix="/informes",
    template_folder="templates",
)

_ACTIVE = "reports"


# ─── helpers ─────────────────────────────────────────────────────────────────

def _page() -> int:
    try:
        return max(1, int(request.args.get("page", 1)))
    except (ValueError, TypeError):
        return 1


def _per_page(default: int = 50) -> int:
    try:
        return max(10, min(200, int(request.args.get("per_page", default))))
    except (ValueError, TypeError):
        return default


def _csv_response(data: bytes, filename: str, content_type: str):
    resp = make_response(data)
    resp.headers["Content-Type"] = content_type
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


def _pdf_response(data: bytes, filename: str):
    resp = make_response(data)
    resp.headers["Content-Type"] = "application/pdf"
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


def _actor() -> str:
    if current_user and current_user.is_authenticated:
        return current_user.username
    return "system"


def _log_export(report_type: str, fmt: str, filename: str, filters: dict | None = None):
    """Record the export in ReportExportLog + AuditLog."""
    try:
        service.log_report_export(
            report_type=report_type,
            fmt=fmt,
            file_name=filename,
            filters=filters,
        )
    except Exception:
        pass  # Don't fail the export if logging fails


def _filters_text(pairs: list[tuple[str, str | None]]) -> str | None:
    """Build a human-readable filters string for PDF header."""
    parts = [f"{k}: {v}" for k, v in pairs if v]
    return ", ".join(parts) if parts else None


# ─── Index ───────────────────────────────────────────────────────────────────

@reports_bp.route("/")
@login_required
def index():
    # Lightweight: only fetch recent exports + minimal counts
    recent_exports = service.get_recent_exports(limit=8)
    index_stats = service.get_index_stats()
    last_exports = service.get_last_exports_by_type()

    report_types = [
        {
            "key": "usuarios",
            "name": "Informe de usuarios",
            "desc": "Listado con rol, cuota, actividad y fechas.",
            "icon": "bi-people-fill",
            "color": "#198754",
            "url_csv": url_for("reports.export_users_csv"),
            "url_pdf": url_for("reports.export_users_pdf"),
        },
        {
            "key": "proyectos",
            "name": "Informe de proyectos",
            "desc": "Proyectos con propietario, tamano, miembros y actividad.",
            "icon": "bi-folder-fill",
            "color": "#6d7c3a",
            "url_csv": url_for("reports.export_projects_csv"),
            "url_pdf": url_for("reports.export_projects_pdf"),
        },
        {
            "key": "almacenamiento",
            "name": "Informe de almacenamiento",
            "desc": "Consumo por usuario, ranking y medias.",
            "icon": "bi-hdd-stack-fill",
            "color": "#0d9488",
            "url_csv": url_for("reports.export_storage_csv"),
            "url_pdf": url_for("reports.export_storage_pdf"),
        },
        {
            "key": "cuotas",
            "name": "Informe de cuotas",
            "desc": "Usuarios dentro/cerca/fuera de cuota y limites de proyectos.",
            "icon": "bi-speedometer",
            "color": "#198754",
            "url_csv": url_for("reports.export_quotas_csv"),
            "url_pdf": url_for("reports.export_quotas_pdf"),
        },
        {
            "key": "actividad",
            "name": "Actividad administrativa",
            "desc": "Log de auditoria: acciones, actores, niveles.",
            "icon": "bi-journal-text",
            "color": "#e6a817",
            "url_csv": url_for("reports.export_activity_csv"),
            "url_pdf": url_for("reports.export_activity_pdf"),
        },
        {
            "key": "incidencias",
            "name": "Informe de incidencias",
            "desc": "Errores y avisos del sistema.",
            "icon": "bi-exclamation-triangle-fill",
            "color": "#dc3545",
            "url_csv": url_for("reports.export_incidents_csv"),
            "url_pdf": url_for("reports.export_incidents_pdf"),
        },
        {
            "key": "sincronizaciones",
            "name": "Informe de sincronizaciones",
            "desc": "Historial de ejecuciones con estado y duracion.",
            "icon": "bi-arrow-repeat",
            "color": "#6c757d",
            "url_csv": url_for("reports.export_syncs_csv"),
            "url_pdf": url_for("reports.export_syncs_pdf"),
        },
    ]

    # Attach last-download metadata to each report type
    for rpt in report_types:
        exp = last_exports.get(rpt["key"])
        if exp:
            rpt["last_export"] = exp
        else:
            rpt["last_export"] = None

    return render_template(
        "reports/index.html",
        active_page=_ACTIVE,
        recent_exports=recent_exports,
        report_types=report_types,
        stats=index_stats,
    )


# ─── General report (progressive loading) ───────────────────────────────────

@reports_bp.route("/general")
@login_required
def general_report():
    """Renders the base page quickly — sections load via AJAX."""
    last_export = service.get_last_general_export()
    return render_template(
        "reports/preview_general.html",
        active_page=_ACTIVE,
        last_export=last_export,
    )


@reports_bp.route("/general/seccion/resumen")
@login_required
def general_section_resumen():
    data = service.get_general_section_resumen()
    return jsonify(data)


@reports_bp.route("/general/seccion/usuarios")
@login_required
def general_section_usuarios():
    data = service.get_general_section_usuarios()
    return jsonify(data)


@reports_bp.route("/general/seccion/proyectos")
@login_required
def general_section_proyectos():
    data = service.get_general_section_proyectos()
    return jsonify(data)


@reports_bp.route("/general/seccion/almacenamiento-cuotas")
@login_required
def general_section_almacenamiento():
    data = service.get_general_section_almacenamiento()
    return jsonify(data)


@reports_bp.route("/general/seccion/sincronizacion")
@login_required
def general_section_sincronizacion():
    data = service.get_general_section_sincronizacion()
    return jsonify(data)


@reports_bp.route("/general/seccion/auditoria-incidencias")
@login_required
def general_section_auditoria():
    data = service.get_general_section_auditoria()
    return jsonify(data)


@reports_bp.route("/general/pdf")
@login_required
def export_general_pdf():
    data = service.get_general_report_data()
    pdf_data, filename, ct = exporters.export_general_pdf(data, generated_by=_actor())
    _log_export("general", "pdf", filename)
    return _pdf_response(pdf_data, filename)


@reports_bp.route("/general/csv")
@login_required
def export_general_csv():
    data = service.get_general_report_data()
    csv_data, filename, ct = exporters.export_general_csv(data)
    _log_export("general", "csv", filename)
    return _csv_response(csv_data, filename, ct)


# ─── Bundle (all-reports ZIP) ────────────────────────────────────────────────

@reports_bp.route("/exportar-todo/csv")
@login_required
def export_all_csv():
    """ZIP archive containing one CSV per report type."""
    all_data = service.get_all_reports_data()
    zip_data, filename, ct = exporters.export_all_csv_zip(all_data)
    _log_export("todos", "zip", filename)
    resp = make_response(zip_data)
    resp.headers["Content-Type"] = ct
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


@reports_bp.route("/exportar-todo/pdf")
@login_required
def export_all_pdf():
    """ZIP archive containing one PDF per report type."""
    all_data = service.get_all_reports_data()
    zip_data, filename, ct = exporters.export_all_pdf_zip(all_data, generated_by=_actor())
    _log_export("todos", "zip", filename)
    resp = make_response(zip_data)
    resp.headers["Content-Type"] = ct
    resp.headers["Content-Disposition"] = f"attachment; filename={filename}"
    return resp


@reports_bp.route("/exportar-todo/csv-unico")
@login_required
def export_all_csv_single():
    """Single CSV file with every report as a labelled section."""
    all_data = service.get_all_reports_data()
    csv_data, filename, ct = exporters.export_all_csv_single(all_data)
    _log_export("todos", "csv", filename)
    return _csv_response(csv_data, filename, ct)


@reports_bp.route("/exportar-todo/pdf-unico")
@login_required
def export_all_pdf_single():
    """Single PDF with every report as a separate section."""
    all_data = service.get_all_reports_data()
    pdf_data, filename, ct = exporters.export_all_pdf_single(all_data, generated_by=_actor())
    _log_export("todos", "pdf", filename)
    return _pdf_response(pdf_data, filename)


# ─── Specific report views → redirect to index ──────────────────────────────
# These used to render preview pages. Now they redirect since specific reports
# are download-only (CSV/PDF).

@reports_bp.route("/usuarios")
@login_required
def users_report():
    return redirect(url_for("reports.index"))


@reports_bp.route("/proyectos")
@login_required
def projects_report():
    return redirect(url_for("reports.index"))


@reports_bp.route("/almacenamiento")
@login_required
def storage_report():
    return redirect(url_for("reports.index"))


@reports_bp.route("/actividad")
@login_required
def activity_report():
    return redirect(url_for("reports.index"))


@reports_bp.route("/cuotas")
@login_required
def quotas_report():
    return redirect(url_for("reports.index"))


@reports_bp.route("/incidencias")
@login_required
def incidents_report():
    return redirect(url_for("reports.index"))


@reports_bp.route("/sincronizaciones")
@login_required
def syncs_report():
    return redirect(url_for("reports.index"))


# ─── Users CSV/PDF ──────────────────────────────────────────────────────────

@reports_bp.route("/usuarios/csv")
@login_required
def export_users_csv():
    args = request.args
    users = service.get_users_report_all(
        search=args.get("q", "").strip() or None,
        role_id=int(args["role_id"]) if args.get("role_id") else None,
        is_admin=True if args.get("admin") == "1" else (False if args.get("admin") == "0" else None),
        date_from=service._parse_date(args.get("date_from")),
        date_to=service._parse_date(args.get("date_to")),
    )
    data, filename, ct = exporters.export_users_csv(users)
    _log_export("usuarios", "csv", filename, {"q": args.get("q"), "role_id": args.get("role_id")})
    return _csv_response(data, filename, ct)


@reports_bp.route("/usuarios/pdf")
@login_required
def export_users_pdf():
    args = request.args
    users = service.get_users_report_all(
        search=args.get("q", "").strip() or None,
        role_id=int(args["role_id"]) if args.get("role_id") else None,
        is_admin=True if args.get("admin") == "1" else (False if args.get("admin") == "0" else None),
        date_from=service._parse_date(args.get("date_from")),
        date_to=service._parse_date(args.get("date_to")),
    )
    ft = _filters_text([
        ("Busqueda", args.get("q")),
        ("Rol", args.get("role_id")),
        ("Admin", args.get("admin")),
    ])
    pdf_data, filename, ct = exporters.export_users_pdf(users, generated_by=_actor(), filters_text=ft)
    _log_export("usuarios", "pdf", filename, {"q": args.get("q")})
    return _pdf_response(pdf_data, filename)


# ─── Projects CSV/PDF ───────────────────────────────────────────────────────

@reports_bp.route("/proyectos/csv")
@login_required
def export_projects_csv():
    args = request.args
    projects = service.get_projects_report_all(
        search=args.get("q", "").strip() or None,
        owner_id=int(args["owner_id"]) if args.get("owner_id") else None,
        size_filter=args.get("size") or None,
        activity_filter=args.get("activity") or None,
    )
    data, filename, ct = exporters.export_projects_csv(projects)
    _log_export("proyectos", "csv", filename)
    return _csv_response(data, filename, ct)


@reports_bp.route("/proyectos/pdf")
@login_required
def export_projects_pdf():
    args = request.args
    projects = service.get_projects_report_all(
        search=args.get("q", "").strip() or None,
        owner_id=int(args["owner_id"]) if args.get("owner_id") else None,
        size_filter=args.get("size") or None,
        activity_filter=args.get("activity") or None,
    )
    ft = _filters_text([
        ("Busqueda", args.get("q")),
        ("Tamano", args.get("size")),
        ("Actividad", args.get("activity")),
    ])
    pdf_data, filename, ct = exporters.export_projects_pdf(projects, generated_by=_actor(), filters_text=ft)
    _log_export("proyectos", "pdf", filename)
    return _pdf_response(pdf_data, filename)


# ─── Storage CSV/PDF ────────────────────────────────────────────────────────

@reports_bp.route("/almacenamiento/csv")
@login_required
def export_storage_csv():
    data = service.get_storage_report()
    csv_data, filename, ct = exporters.export_storage_csv(data["rows"])
    _log_export("almacenamiento", "csv", filename)
    return _csv_response(csv_data, filename, ct)


@reports_bp.route("/almacenamiento/pdf")
@login_required
def export_storage_pdf():
    data = service.get_storage_report()
    pdf_data, filename, ct = exporters.export_storage_pdf(
        data["rows"],
        totals=data,
        generated_by=_actor(),
    )
    _log_export("almacenamiento", "pdf", filename)
    return _pdf_response(pdf_data, filename)


# ─── Activity CSV/PDF ───────────────────────────────────────────────────────

@reports_bp.route("/actividad/csv")
@login_required
def export_activity_csv():
    args = request.args
    entries = service.get_activity_report_all(
        level=args.get("level") or None,
        action=args.get("action") or None,
        actor=args.get("actor") or None,
        date_from=service._parse_date(args.get("date_from")),
        date_to=service._parse_date(args.get("date_to")),
    )
    data, filename, ct = exporters.export_activity_csv(entries)
    _log_export("actividad", "csv", filename)
    return _csv_response(data, filename, ct)


@reports_bp.route("/actividad/pdf")
@login_required
def export_activity_pdf():
    args = request.args
    entries = service.get_activity_report_all(
        level=args.get("level") or None,
        action=args.get("action") or None,
        actor=args.get("actor") or None,
        date_from=service._parse_date(args.get("date_from")),
        date_to=service._parse_date(args.get("date_to")),
    )
    ft = _filters_text([
        ("Nivel", args.get("level")),
        ("Accion", args.get("action")),
        ("Actor", args.get("actor")),
    ])
    pdf_data, filename, ct = exporters.export_activity_pdf(entries, generated_by=_actor(), filters_text=ft)
    _log_export("actividad", "pdf", filename)
    return _pdf_response(pdf_data, filename)


# ─── Quotas CSV/PDF ─────────────────────────────────────────────────────────

@reports_bp.route("/cuotas/csv")
@login_required
def export_quotas_csv():
    args = request.args
    rows = service.get_quotas_report_all(
        status_filter=args.get("status") or None,
    )
    data, filename, ct = exporters.export_quotas_csv(rows)
    _log_export("cuotas", "csv", filename)
    return _csv_response(data, filename, ct)


@reports_bp.route("/cuotas/pdf")
@login_required
def export_quotas_pdf():
    args = request.args
    rows = service.get_quotas_report_all(
        status_filter=args.get("status") or None,
    )
    ft = _filters_text([("Estado", args.get("status"))])
    pdf_data, filename, ct = exporters.export_quotas_pdf(rows, generated_by=_actor(), filters_text=ft)
    _log_export("cuotas", "pdf", filename)
    return _pdf_response(pdf_data, filename)


# ─── Incidents CSV/PDF ──────────────────────────────────────────────────────

@reports_bp.route("/incidencias/csv")
@login_required
def export_incidents_csv():
    args = request.args
    entries = service.get_incidents_report_all(
        level=args.get("level") or None,
        date_from=service._parse_date(args.get("date_from")),
        date_to=service._parse_date(args.get("date_to")),
    )
    data, filename, ct = exporters.export_incidents_csv(entries)
    _log_export("incidencias", "csv", filename)
    return _csv_response(data, filename, ct)


@reports_bp.route("/incidencias/pdf")
@login_required
def export_incidents_pdf():
    args = request.args
    entries = service.get_incidents_report_all(
        level=args.get("level") or None,
        date_from=service._parse_date(args.get("date_from")),
        date_to=service._parse_date(args.get("date_to")),
    )
    ft = _filters_text([("Nivel", args.get("level"))])
    pdf_data, filename, ct = exporters.export_incidents_pdf(entries, generated_by=_actor(), filters_text=ft)
    _log_export("incidencias", "pdf", filename)
    return _pdf_response(pdf_data, filename)


# ─── Syncs CSV/PDF ──────────────────────────────────────────────────────────

@reports_bp.route("/sincronizaciones/csv")
@login_required
def export_syncs_csv():
    args = request.args
    runs = service.get_syncs_report_all(
        status=args.get("status") or None,
        date_from=service._parse_date(args.get("date_from")),
        date_to=service._parse_date(args.get("date_to")),
    )
    data, filename, ct = exporters.export_syncs_csv(runs)
    _log_export("sincronizaciones", "csv", filename)
    return _csv_response(data, filename, ct)


@reports_bp.route("/sincronizaciones/pdf")
@login_required
def export_syncs_pdf():
    args = request.args
    runs = service.get_syncs_report_all(
        status=args.get("status") or None,
        date_from=service._parse_date(args.get("date_from")),
        date_to=service._parse_date(args.get("date_to")),
    )
    ft = _filters_text([("Estado", args.get("status"))])
    pdf_data, filename, ct = exporters.export_syncs_pdf(runs, generated_by=_actor(), filters_text=ft)
    _log_export("sincronizaciones", "pdf", filename)
    return _pdf_response(pdf_data, filename)


# ─── Export history ──────────────────────────────────────────────────────────

@reports_bp.route("/exportaciones")
@login_required
def export_history():
    data = service.get_export_history(page=_page(), per_page=_per_page(25))
    return render_template(
        "reports/exports_history.html",
        active_page=_ACTIVE,
        **data,
    )
