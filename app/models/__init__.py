# Import all models so Flask-Migrate can detect them
from app.models.admin_user import AdminUser
from app.models.overleaf_user import OverleafUser
from app.models.overleaf_project import OverleafProject
from app.models.project_member import ProjectMember
from app.models.sync_run import SyncRun
from app.models.audit_log import AuditLog

__all__ = [
    "AdminUser",
    "OverleafUser",
    "OverleafProject",
    "ProjectMember",
    "SyncRun",
    "AuditLog",
]
