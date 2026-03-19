"""
OverleafLoader — upserts transformed ORM objects into PostgreSQL.

Strategy: upsert by overleaf_id.
  - If an object with the same overleaf_id already exists → update it.
  - Otherwise → insert a new row.
This makes syncs idempotent and safe to re-run.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from app.extensions import db
from app.models.overleaf_user import OverleafUser
from app.models.overleaf_project import OverleafProject
from app.models.project_member import ProjectMember

logger = logging.getLogger(__name__)


class OverleafLoader:

    def upsert_users(self, raw_users: list[dict[str, Any]]) -> tuple[int, int]:
        """
        Upsert a list of raw user dicts.
        Returns (total_found, total_synced).
        """
        synced = 0
        now = datetime.now(timezone.utc)

        for raw in raw_users:
            try:
                existing = OverleafUser.query.filter_by(
                    overleaf_id=raw["overleaf_id"]
                ).first()

                if existing:
                    # Update fields
                    existing.email = raw.get("email", existing.email)
                    existing.first_name = raw.get("first_name", existing.first_name)
                    existing.last_name = raw.get("last_name", existing.last_name)
                    existing.is_admin = bool(raw.get("is_admin", existing.is_admin))
                    existing.signup_date = raw.get("signup_date") or existing.signup_date
                    existing.last_login_at = raw.get("last_login_at") or existing.last_login_at
                    existing.synced_at = now
                else:
                    user = OverleafUser(
                        overleaf_id=raw["overleaf_id"],
                        email=raw.get("email"),
                        first_name=raw.get("first_name"),
                        last_name=raw.get("last_name"),
                        is_admin=bool(raw.get("is_admin", False)),
                        signup_date=raw.get("signup_date"),
                        last_login_at=raw.get("last_login_at"),
                        synced_at=now,
                    )
                    db.session.add(user)

                synced += 1
            except Exception as exc:
                logger.error(
                    "Error upserting user %s: %s",
                    raw.get("overleaf_id", "?"),
                    exc,
                )

        db.session.flush()  # Get IDs before committing
        return len(raw_users), synced

    def build_user_map(self) -> dict[str, int]:
        """Return mapping of overleaf_id → internal DB id for all users."""
        rows = db.session.query(OverleafUser.overleaf_id, OverleafUser.id).all()
        return {r.overleaf_id: r.id for r in rows}

    def upsert_projects(
        self,
        raw_projects: list[dict[str, Any]],
        memberships_data: list[tuple[str, list[dict]]],  # (overleaf_project_id, memberships)
        user_map: dict[str, int],
    ) -> tuple[int, int]:
        """
        Upsert projects and their memberships.
        Returns (total_found, total_synced).
        """
        synced = 0
        now = datetime.now(timezone.utc)

        for raw in raw_projects:
            try:
                owner_oid = raw.get("owner_overleaf_id")
                owner_internal_id = user_map.get(owner_oid) if owner_oid else None

                existing = OverleafProject.query.filter_by(
                    overleaf_id=raw["overleaf_id"]
                ).first()

                if existing:
                    existing.name = raw.get("name", existing.name)
                    existing.owner_id = owner_internal_id or existing.owner_id
                    existing.owner_overleaf_id = owner_oid or existing.owner_overleaf_id
                    existing.created_at = raw.get("created_at") or existing.created_at
                    existing.last_updated_at = raw.get("last_updated_at") or existing.last_updated_at
                    existing.synced_at = now
                else:
                    project = OverleafProject(
                        overleaf_id=raw["overleaf_id"],
                        name=raw.get("name"),
                        owner_id=owner_internal_id,
                        owner_overleaf_id=owner_oid,
                        created_at=raw.get("created_at"),
                        last_updated_at=raw.get("last_updated_at"),
                        synced_at=now,
                    )
                    db.session.add(project)

                synced += 1
            except Exception as exc:
                logger.error(
                    "Error upserting project %s: %s",
                    raw.get("overleaf_id", "?"),
                    exc,
                )

        db.session.flush()

        # Upsert memberships
        self._upsert_memberships(memberships_data, user_map)

        return len(raw_projects), synced

    def _upsert_memberships(
        self,
        memberships_data: list[tuple[str, list[dict]]],
        user_map: dict[str, int],
    ) -> None:
        """Upsert project membership records."""
        for project_overleaf_id, members in memberships_data:
            project = OverleafProject.query.filter_by(
                overleaf_id=project_overleaf_id
            ).first()
            if not project:
                continue

            for m in members:
                user_internal_id = user_map.get(m["overleaf_user_id"])
                if not user_internal_id:
                    continue

                existing = ProjectMember.query.filter_by(
                    project_id=project.id, user_id=user_internal_id
                ).first()

                if existing:
                    existing.role = m["role"]
                    existing.synced_at = datetime.now(timezone.utc)
                else:
                    member = ProjectMember(
                        project_id=project.id,
                        user_id=user_internal_id,
                        role=m["role"],
                    )
                    db.session.add(member)
