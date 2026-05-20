# Import all entities so Flask-Migrate can detect them
from app.model.entities.admin_user import AdminUser
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.project_member import ProjectMember
from app.model.entities.sync_run import SyncRun
from app.model.entities.audit_log import AuditLog
from app.model.entities.report_export_log import ReportExportLog

__all__ = [
    "AdminUser",
    "OverleafUser",
    "OverleafProject",
    "ProjectMember",
    "SyncRun",
    "AuditLog",
    "ReportExportLog",
]
