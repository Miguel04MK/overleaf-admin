"""
OverleafTransformer — converts extracted raw dicts to SQLAlchemy model instances.

This layer is deliberately simple: it maps the normalized dicts from the
extractor to ORM objects, resolving foreign keys where needed.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from app.models.overleaf_user import OverleafUser
from app.models.overleaf_project import OverleafProject
from app.models.project_member import ProjectMember

logger = logging.getLogger(__name__)


class OverleafTransformer:
    """
    Transforms raw normalized dicts (from extractor) into ORM objects.
    Does NOT write to the database — that is the Loader's job.
    """

    def transform_user(self, raw: dict[str, Any]) -> OverleafUser:
        """Create or update an OverleafUser ORM instance from a raw dict."""
        user = OverleafUser(
            overleaf_id=raw["overleaf_id"],
            email=raw.get("email"),
            first_name=raw.get("first_name"),
            last_name=raw.get("last_name"),
            is_admin=bool(raw.get("is_admin", False)),
            signup_date=raw.get("signup_date"),
            last_login_at=raw.get("last_login_at"),
            synced_at=datetime.now(timezone.utc),
        )
        return user

    def transform_project(
        self,
        raw: dict[str, Any],
        user_map: dict[str, int],  # overleaf_id -> internal DB id
    ) -> tuple[OverleafProject, list[dict]]:
        """
        Create an OverleafProject ORM instance and a list of membership dicts.

        Returns:
            (project_orm, memberships)
            memberships: list of {"overleaf_user_id": str, "role": str}
        """
        owner_oid = raw.get("owner_overleaf_id")
        owner_internal_id = user_map.get(owner_oid) if owner_oid else None

        project = OverleafProject(
            overleaf_id=raw["overleaf_id"],
            name=raw.get("name"),
            owner_id=owner_internal_id,
            owner_overleaf_id=owner_oid,
            created_at=raw.get("created_at"),
            last_updated_at=raw.get("last_updated_at"),
            synced_at=datetime.now(timezone.utc),
        )

        memberships = []
        for oid in raw.get("collaborator_overleaf_ids", []):
            if oid in user_map:
                memberships.append({"overleaf_user_id": oid, "role": "collaborator"})
        for oid in raw.get("readonly_overleaf_ids", []):
            if oid in user_map:
                memberships.append({"overleaf_user_id": oid, "role": "read_only"})

        return project, memberships
