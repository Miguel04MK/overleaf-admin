"""
app/modules/reports/service/
------------------------------
Public re-export surface — all names that existed in the old service.py
are available here so callers do ``from app.modules.reports import service``
and then ``service.get_users_report(...)`` without any changes.
"""

# ── Helpers ───────────────────────────────────────────────────────────────────
from ._helpers import (
    _INACTIVE_DAYS,
    _LARGE_BYTES,
    _parse_date,
    _fmt_bytes,
    _split_bytes,
    _trend,
    _actor_name,
)

# ── Export logging ────────────────────────────────────────────────────────────
from .export_log import (
    log_report_export,
    get_export_history,
    get_recent_exports,
    get_last_exports_by_type,
    get_last_general_export,
)

# ── Individual report queries ─────────────────────────────────────────────────
from .report_queries import (
    get_users_report,
    get_users_report_all,
    get_projects_report,
    get_projects_report_all,
    get_storage_report,
    get_activity_report,
    get_activity_report_all,
    get_syncs_report,
    get_syncs_report_all,
    get_quotas_report,
    get_quotas_report_all,
    get_incidents_report,
    get_incidents_report_all,
    get_alerts_report_all,
)

# ── General report queries ────────────────────────────────────────────────────
from .general_queries import (
    get_general_section_resumen,
    get_general_section_usuarios,
    get_general_section_proyectos,
    get_general_section_almacenamiento,
    get_general_section_sincronizacion,
    get_general_section_auditoria,
    get_general_report_data,
)

# ── System checks ─────────────────────────────────────────────────────────────
from .system_checks import (
    check_system_status,
)

# ── Index / bundle stats ──────────────────────────────────────────────────────
from .index_stats import (
    get_index_stats,
    get_all_reports_data,
    get_reports_overview,
)

__all__ = [
    # helpers
    "_INACTIVE_DAYS", "_LARGE_BYTES", "_parse_date", "_fmt_bytes",
    "_split_bytes", "_trend", "_actor_name",
    # export log
    "log_report_export", "get_export_history", "get_recent_exports",
    "get_last_exports_by_type", "get_last_general_export",
    # individual reports
    "get_users_report", "get_users_report_all",
    "get_projects_report", "get_projects_report_all",
    "get_storage_report",
    "get_activity_report", "get_activity_report_all",
    "get_syncs_report", "get_syncs_report_all",
    "get_quotas_report", "get_quotas_report_all",
    "get_incidents_report", "get_incidents_report_all",
    "get_alerts_report_all",
    # general report
    "get_general_section_resumen", "get_general_section_usuarios",
    "get_general_section_proyectos", "get_general_section_almacenamiento",
    "get_general_section_sincronizacion", "get_general_section_auditoria",
    "get_general_report_data",
    # system
    "check_system_status",
    # index / bundle
    "get_index_stats", "get_all_reports_data", "get_reports_overview",
]
