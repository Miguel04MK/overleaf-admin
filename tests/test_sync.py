"""
tests/test_sync.py
------------------
Basic tests for the ETL transformation layer.
These tests do NOT require a real MongoDB or PostgreSQL connection.
They validate the normalization logic using mock data.

Run with:
    python -m pytest tests/ -v
"""
import pytest
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

from app.etl.extractors.extractor import OverleafExtractor
from app.etl.transformers.transformer import OverleafTransformer


# ── Extractor tests ────────────────────────────────────────────────────────

class TestOverleafExtractor:

    def _make_extractor(self, users=None, projects=None):
        mock_db = MagicMock()
        mock_db["users"].find.return_value = users or []
        mock_db["projects"].find.return_value = projects or []
        mock_db["users"].count_documents.return_value = len(users or [])
        mock_db["projects"].count_documents.return_value = len(projects or [])
        return OverleafExtractor(mock_db)

    def test_extract_users_empty(self):
        extractor = self._make_extractor()
        result = extractor.extract_users()
        assert result == []

    def test_normalize_user_standard_fields(self):
        from bson import ObjectId
        oid = ObjectId()
        doc = {
            "_id": oid,
            "email": "alice@example.com",
            "first_name": "Alice",
            "last_name": "García",
            "isAdmin": True,
            "signUpDate": datetime(2023, 1, 15, tzinfo=timezone.utc),
            "lastLoggedIn": datetime(2024, 3, 1, tzinfo=timezone.utc),
        }
        extractor = self._make_extractor()
        normalized = extractor._normalize_user(doc)

        assert normalized["overleaf_id"] == str(oid)
        assert normalized["email"] == "alice@example.com"
        assert normalized["first_name"] == "Alice"
        assert normalized["last_name"] == "García"
        assert normalized["is_admin"] is True
        assert normalized["signup_date"].year == 2023
        assert normalized["last_login_at"].year == 2024

    def test_normalize_user_missing_optional_fields(self):
        from bson import ObjectId
        doc = {
            "_id": ObjectId(),
            "email": "bob@example.com",
            # No first_name, last_name, isAdmin, signUpDate, lastLoggedIn
        }
        extractor = self._make_extractor()
        normalized = extractor._normalize_user(doc)

        assert normalized["first_name"] is None
        assert normalized["last_name"] is None
        assert normalized["is_admin"] is False
        assert normalized["signup_date"] is None
        assert normalized["last_login_at"] is None

    def test_normalize_project_standard_fields(self):
        from bson import ObjectId
        proj_oid = ObjectId()
        owner_oid = ObjectId()
        collab_oid = ObjectId()
        doc = {
            "_id": proj_oid,
            "name": "Mi TFG",
            "owner_ref": owner_oid,
            "collaberator_refs": [collab_oid],
            "readOnly_refs": [],
            "created": datetime(2023, 9, 1, tzinfo=timezone.utc),
            "lastUpdated": datetime(2024, 1, 10, tzinfo=timezone.utc),
            "active": True,
        }
        extractor = self._make_extractor()
        normalized = extractor._normalize_project(doc)

        assert normalized["overleaf_id"] == str(proj_oid)
        assert normalized["name"] == "Mi TFG"
        assert normalized["owner_overleaf_id"] == str(owner_oid)
        assert str(collab_oid) in normalized["collaborator_overleaf_ids"]
        assert normalized["created_at"].year == 2023

    def test_to_utc_naive_datetime(self):
        naive = datetime(2023, 6, 15, 10, 30)
        result = OverleafExtractor._to_utc(naive)
        assert result.tzinfo is not None
        assert result.year == 2023

    def test_to_utc_none(self):
        assert OverleafExtractor._to_utc(None) is None


# ── Transformer tests ──────────────────────────────────────────────────────

class TestOverleafTransformer:

    def test_transform_user(self):
        transformer = OverleafTransformer()
        raw = {
            "overleaf_id": "aabbcc112233",
            "email": "test@example.com",
            "first_name": "Test",
            "last_name": "User",
            "is_admin": False,
            "signup_date": datetime(2023, 1, 1, tzinfo=timezone.utc),
            "last_login_at": None,
        }
        user = transformer.transform_user(raw)
        assert user.overleaf_id == "aabbcc112233"
        assert user.email == "test@example.com"
        assert user.is_admin is False

    def test_transform_project_resolves_owner(self):
        transformer = OverleafTransformer()
        user_map = {"owner_oid_123": 42}
        raw = {
            "overleaf_id": "proj_oid_abc",
            "name": "Mi proyecto",
            "owner_overleaf_id": "owner_oid_123",
            "collaborator_overleaf_ids": [],
            "readonly_overleaf_ids": [],
            "created_at": None,
            "last_updated_at": None,
        }
        project, memberships = transformer.transform_project(raw, user_map)
        assert project.overleaf_id == "proj_oid_abc"
        assert project.owner_id == 42
        assert memberships == []

    def test_transform_project_memberships(self):
        transformer = OverleafTransformer()
        user_map = {"owner_oid": 1, "collab_oid": 2, "ro_oid": 3}
        raw = {
            "overleaf_id": "proj_xyz",
            "name": "Proyecto compartido",
            "owner_overleaf_id": "owner_oid",
            "collaborator_overleaf_ids": ["collab_oid"],
            "readonly_overleaf_ids": ["ro_oid"],
            "created_at": None,
            "last_updated_at": None,
        }
        project, memberships = transformer.transform_project(raw, user_map)
        roles = {m["overleaf_user_id"]: m["role"] for m in memberships}
        assert roles["collab_oid"] == "collaborator"
        assert roles["ro_oid"] == "read_only"
