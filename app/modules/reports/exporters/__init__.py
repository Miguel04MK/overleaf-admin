"""
app/modules/reports/exporters/
--------------------------------
Public re-export surface — all names that existed in the old exporters.py
are available here so callers do ``from app.modules.reports import exporters``
and then ``exporters.export_users_csv(...)`` without any changes.
"""

# ── helpers (shared) ─────────────────────────────────────────────────────────
from ._helpers import (
    _make_csv,
    _today_suffix,
    _ts,
    _ts_short,
    _date,
    _fmt_bytes,
)

# ── CSV ───────────────────────────────────────────────────────────────────────
from .csv_exporters import (
    # row builders
    _build_users_csv_rows,
    _build_projects_csv_rows,
    _build_storage_csv_rows,
    _build_quotas_csv_rows,
    _build_activity_csv_rows,
    _build_incidents_csv_rows,
    _build_syncs_csv_rows,
    _build_alerts_csv_rows,
    _build_incidents_alerts_csv_rows,
    _build_general_csv_rows,
    # individual exporters
    export_users_csv,
    export_projects_csv,
    export_storage_csv,
    export_activity_csv,
    export_syncs_csv,
    export_quotas_csv,
    export_incidents_csv,
    export_alerts_csv,
    export_incidents_alerts_csv,
    export_general_csv,
    # bundle
    export_all_csv_zip,
    export_all_csv_single,
)

# ── PDF base ──────────────────────────────────────────────────────────────────
from .pdf_base import (
    _pdf_styles,
    _header_footer,
    _build_pdf,
    _make_table,
    _metric_pair,
    # colour constants (used in tests / other modules)
    _TEXT, _TEXT_SECONDARY, _GREEN, _GREEN_SOFT, _RED, _AMBER,
    _ROW_ALT, _BORDER, _RULE,
    _GREEN_LIGHT, _GRAY, _LIGHT_GRAY,
    _MARGIN_L, _MARGIN_R, _CONTENT_W, _PAGE_W, _PAGE_H,
)

# ── PDF sections (individual reports) ────────────────────────────────────────
from .pdf_sections import (
    _users_section,    export_users_pdf,
    _projects_section, export_projects_pdf,
    _storage_section,  export_storage_pdf,
    _quotas_section,   export_quotas_pdf,
    _activity_section, export_activity_pdf,
    _incidents_section,export_incidents_pdf,      # legacy alias
    _syncs_section,    export_syncs_pdf,
    _alerts_section,   export_alerts_pdf,          # legacy alias
    _incidents_alerts_section, export_incidents_alerts_pdf,
)

# ── PDF general ───────────────────────────────────────────────────────────────
from .pdf_general import (
    _translate_action,
    _smart_truncate,
    _build_narrative_summary,
    _general_first_page,
    _general_later_pages,
    _gen_table,
    _gen_kv_table,
    _ACTION_TRANSLATIONS,
    _RANKING_NOTE_TEXT,
    export_general_pdf,
)

# ── PDF bundle ────────────────────────────────────────────────────────────────
from .pdf_bundle import (
    export_all_pdf_zip,
    export_all_pdf_single,
)

__all__ = [
    # helpers
    "_make_csv", "_today_suffix", "_ts", "_ts_short", "_date", "_fmt_bytes",
    # CSV row builders
    "_build_users_csv_rows", "_build_projects_csv_rows", "_build_storage_csv_rows",
    "_build_quotas_csv_rows", "_build_activity_csv_rows", "_build_incidents_csv_rows",
    "_build_syncs_csv_rows", "_build_alerts_csv_rows",
    "_build_incidents_alerts_csv_rows", "_build_general_csv_rows",
    # CSV exporters
    "export_users_csv", "export_projects_csv", "export_storage_csv",
    "export_activity_csv", "export_syncs_csv", "export_quotas_csv",
    "export_incidents_csv", "export_alerts_csv",
    "export_incidents_alerts_csv", "export_general_csv",
    "export_all_csv_zip", "export_all_csv_single",
    # PDF base
    "_pdf_styles", "_header_footer", "_build_pdf", "_make_table", "_metric_pair",
    # PDF sections
    "_users_section", "export_users_pdf",
    "_projects_section", "export_projects_pdf",
    "_storage_section", "export_storage_pdf",
    "_quotas_section", "export_quotas_pdf",
    "_activity_section", "export_activity_pdf",
    "_incidents_section", "export_incidents_pdf",
    "_syncs_section", "export_syncs_pdf",
    "_alerts_section", "export_alerts_pdf",
    "_incidents_alerts_section", "export_incidents_alerts_pdf",
    # PDF general
    "export_general_pdf", "_translate_action", "_smart_truncate",
    "_build_narrative_summary", "_gen_table", "_gen_kv_table",
    # PDF bundle
    "export_all_pdf_zip", "export_all_pdf_single",
]
