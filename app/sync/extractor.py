"""
OverleafExtractor — reads raw documents from Overleaf's MongoDB.

VERSION SENSITIVITY:
    This file documents known differences across Overleaf CE versions.
    All field-name assumptions are centralized here.

Known collection structure (as of Overleaf CE 2.x–5.x, community branch):

  users collection:
    _id           ObjectId   — unique user ID
    email         string     — user email (always present)
    first_name    string     — may be absent in some versions
    last_name     string     — may be absent
    isAdmin       bool       — admin flag (may be absent → default False)
    signUpDate    Date       — registration date (absent in some old versions)
    lastLoggedIn  Date       — last login (absent if never logged in)
    hashedPassword string    — NOT extracted (security)

  projects collection:
    _id           ObjectId   — unique project ID
    name          string     — project name
    owner_ref     ObjectId   — references users._id
    collaberator_refs [ObjectId] — read-write collaborators
    readOnly_refs [ObjectId] — read-only collaborators
    created       Date       — creation date (may be named 'date' in very old versions)
    lastUpdated   Date       — last modification date
    active        bool       — soft-delete flag (True = active)

If your version has different field names, update the _extract_* methods below
and document the change here.
"""
import logging
from datetime import datetime, timezone
from typing import Any

from bson import ObjectId
from pymongo.database import Database

logger = logging.getLogger(__name__)

# Fields that are explicitly NOT extracted (privacy/security)
_USER_EXCLUDED_FIELDS = {"hashedPassword", "password", "tokens", "loginSecret"}


class OverleafExtractor:
    """Reads raw data from Overleaf MongoDB. Returns Python dicts."""

    def __init__(self, db: Database):
        self.db = db

    # ------------------------------------------------------------------ #
    #  Users                                                               #
    # ------------------------------------------------------------------ #

    def extract_users(self) -> list[dict[str, Any]]:
        """
        Extract all users from Overleaf's users collection.
        Returns a list of raw dicts (ObjectIds converted to strings).
        """
        logger.info("Extracting users from MongoDB...")
        projection = {field: 0 for field in _USER_EXCLUDED_FIELDS}

        raw_users = list(self.db["users"].find({}, projection))
        logger.info("Found %d users in MongoDB.", len(raw_users))

        return [self._normalize_user(u) for u in raw_users]

    def _normalize_user(self, doc: dict) -> dict[str, Any]:
        """Convert ObjectIds to strings and handle missing fields."""
        return {
            "overleaf_id": str(doc["_id"]),
            "email": doc.get("email"),
            "first_name": doc.get("first_name") or doc.get("firstName"),
            "last_name": doc.get("last_name") or doc.get("lastName"),
            "is_admin": bool(doc.get("isAdmin", False)),
            # signUpDate vs date — handle both for compatibility
            "signup_date": self._to_utc(
                doc.get("signUpDate") or doc.get("date")
            ),
            "last_login_at": self._to_utc(doc.get("lastLoggedIn")),
        }

    # ------------------------------------------------------------------ #
    #  Projects                                                            #
    # ------------------------------------------------------------------ #

    def extract_projects(self) -> list[dict[str, Any]]:
        """
        Extract all active projects from Overleaf's projects collection.
        """
        logger.info("Extracting projects from MongoDB...")

        # Filter: active != False  (some versions omit 'active' for active projects)
        query = {"active": {"$ne": False}}
        raw_projects = list(self.db["projects"].find(query))
        logger.info("Found %d projects in MongoDB.", len(raw_projects))

        return [self._normalize_project(p) for p in raw_projects]

    def _normalize_project(self, doc: dict) -> dict[str, Any]:
        """Convert ObjectIds to strings and handle version differences."""
        # owner_ref is an ObjectId in all known versions
        owner_ref = doc.get("owner_ref")
        owner_id_str = str(owner_ref) if owner_ref else None

        # Collaborators
        collab_refs = [str(r) for r in doc.get("collaberator_refs", [])]
        readonly_refs = [str(r) for r in doc.get("readOnly_refs", [])]

        # created: 'created' field (newer) or 'date' (older versions)
        created_at = self._to_utc(doc.get("created") or doc.get("date"))

        return {
            "overleaf_id": str(doc["_id"]),
            "name": doc.get("name"),
            "owner_overleaf_id": owner_id_str,
            "collaborator_overleaf_ids": collab_refs,
            "readonly_overleaf_ids": readonly_refs,
            "created_at": created_at,
            "last_updated_at": self._to_utc(doc.get("lastUpdated")),
        }

    # ------------------------------------------------------------------ #
    #  Helpers                                                             #
    # ------------------------------------------------------------------ #

    @staticmethod
    def _to_utc(value) -> datetime | None:
        """Normalize a MongoDB date to a timezone-aware UTC datetime."""
        if value is None:
            return None
        if isinstance(value, datetime):
            if value.tzinfo is None:
                return value.replace(tzinfo=timezone.utc)
            return value
        return None
