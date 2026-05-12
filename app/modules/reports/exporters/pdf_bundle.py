"""
exporters/pdf_bundle.py
------------------------
Bundle exporters: ZIP of all PDFs and single combined PDF.
Imports section helpers from pdf_sections and pdf_general.
"""
from __future__ import annotations

import io
import zipfile

from reportlab.platypus import PageBreak, Paragraph, HRFlowable

from ._helpers import _today_suffix
from .pdf_base import _pdf_styles, _build_pdf, _RULE
from .pdf_sections import (
    _users_section, _projects_section, _storage_section,
    _quotas_section, _activity_section, _syncs_section,
    _incidents_alerts_section,
    export_users_pdf, export_projects_pdf, export_storage_pdf,
    export_quotas_pdf, export_activity_pdf, export_syncs_pdf,
    export_incidents_alerts_pdf,
)
from .pdf_general import export_general_pdf


def export_all_pdf_zip(all_data: dict, generated_by: str = "system") -> tuple[bytes, str, str]:
    """Bundle every individual PDF export into a single ZIP file."""
    buf = io.BytesIO()
    with zipfile.ZipFile(buf, "w", zipfile.ZIP_DEFLATED) as zf:
        entries: list[tuple[str, bytes]] = []

        data, fname, _ = export_users_pdf(all_data["users"], generated_by=generated_by)
        entries.append((fname, data))

        data, fname, _ = export_projects_pdf(all_data["projects"], generated_by=generated_by)
        entries.append((fname, data))

        storage = all_data["storage"]
        data, fname, _ = export_storage_pdf(
            storage["rows"], totals=storage, generated_by=generated_by
        )
        entries.append((fname, data))

        data, fname, _ = export_quotas_pdf(all_data["quotas"], generated_by=generated_by)
        entries.append((fname, data))

        data, fname, _ = export_activity_pdf(all_data["activity"], generated_by=generated_by)
        entries.append((fname, data))

        data, fname, _ = export_incidents_alerts_pdf(
            all_data["incidents"], all_data["alerts"], generated_by=generated_by,
        )
        entries.append((fname, data))

        data, fname, _ = export_syncs_pdf(all_data["syncs"], generated_by=generated_by)
        entries.append((fname, data))

        data, fname, _ = export_general_pdf(all_data["general"], generated_by=generated_by)
        entries.append((fname, data))

        for fname, content in entries:
            zf.writestr(fname, content)

    filename = f"informes_completos_{_today_suffix()}.zip"
    return buf.getvalue(), filename, "application/zip"


def export_all_pdf_single(all_data: dict, generated_by: str = "system") -> tuple[bytes, str, str]:
    """One PDF containing every report as a labelled section."""
    styles = _pdf_styles()

    def _section_title(name: str) -> list:
        return [
            Paragraph(name, styles["SectionHeading"]),
            HRFlowable(width="100%", thickness=0.4, color=_RULE,
                       spaceAfter=8, spaceBefore=0),
        ]

    sections = [
        ("Usuarios",                 _users_section(all_data["users"])),
        ("Proyectos",                _projects_section(all_data["projects"])),
        ("Almacenamiento",           _storage_section(all_data["storage_rows"], all_data["storage"])),
        ("Cuotas",                   _quotas_section(all_data["quotas"])),
        ("Actividad administrativa", _activity_section(all_data["activity"])),
        ("Incidencias y alertas",    _incidents_alerts_section(all_data["incidents"], all_data["alerts"])),
        ("Sincronizaciones",         _syncs_section(all_data["syncs"])),
    ]

    combined: list = []
    for i, (title, section_fl) in enumerate(sections):
        if i > 0:
            combined.append(PageBreak())
        combined += _section_title(title)
        combined += section_fl

    data = _build_pdf(
        "Informe completo — todos los informes",
        generated_by,
        combined,
    )
    return data, f"informe_completo_{_today_suffix()}.pdf", "application/pdf"
