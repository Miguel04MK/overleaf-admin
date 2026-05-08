"""
ReportExportLog entity — tracks every report export (CSV/PDF).

Provides an auditable history of who generated what report, when,
with which filters, and whether it succeeded.
"""
from datetime import datetime, timezone

from app.config.extensions import db


class ReportExportLog(db.Model):
    __tablename__ = "report_export_logs"

    id = db.Column(db.Integer, primary_key=True)

    # "general", "usuarios", "proyectos", "almacenamiento",
    # "cuotas", "actividad", "incidencias", "sincronizaciones"
    report_type = db.Column(db.String(64), nullable=False, index=True)

    # "csv" | "pdf"
    format = db.Column(db.String(16), nullable=False)

    generated_by = db.Column(db.String(128), nullable=False, default="system")

    generated_at = db.Column(
        db.DateTime(timezone=True),
        default=lambda: datetime.now(timezone.utc),
        nullable=False,
        index=True,
    )

    # JSON string of the filters applied (e.g. '{"search":"test","role_id":2}')
    filters_json = db.Column(db.Text, nullable=True)

    # "completed" | "error"
    status = db.Column(db.String(32), nullable=False, default="completed")

    file_name = db.Column(db.String(255), nullable=True)

    error_message = db.Column(db.Text, nullable=True)

    def __repr__(self) -> str:
        return (
            f"<ReportExportLog {self.report_type}/{self.format} "
            f"by {self.generated_by} at {self.generated_at}>"
        )
