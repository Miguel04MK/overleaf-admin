"""
tests/test_projects.py
----------------------
Tests for the Projects domain: entity, DAO, service and controller.

Run with:
    python -m pytest tests/test_projects.py -v
"""
import pytest
from datetime import datetime, timezone, timedelta

from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.project_member import ProjectMember
from app.model.entities import overleaf_project_dao as project_dao
from app.model.services import projects_service
from app.rest.controllers.projects_controller import _fmt_size
from app.rest.common.helpers import parse_date as _parse_date
from tests.conftest import make_user, make_project


# ═══════════════════════════════════════════════════════════════════════════════
# ENTITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestOverleafProjectEntity:

    def _project(self, **kwargs):
        defaults = dict(overleaf_id="oid-p", name="Test Project")
        defaults.update(kwargs)
        return OverleafProject(**defaults)

    def test_repr_shows_name(self):
        p = self._project(name="Mi Proyecto")
        assert "Mi Proyecto" in repr(p)

    def test_repr_shows_overleaf_id_when_no_name(self):
        p = self._project(name=None, overleaf_id="abc123")
        assert "abc123" in repr(p)

    def test_fields_stored_correctly(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-pe-owner")
            p = make_project(db, "oid-pe1", name="My Proj", owner=owner, size_bytes=2048)
            assert p.name == "My Proj"
            assert p.size_bytes == 2048
            assert p.owner_id == owner.id
            assert p.owner_overleaf_id == owner.overleaf_id

    def test_synced_at_set_automatically(self, app, db):
        with app.app_context():
            p = make_project(db, "oid-pe2")
            assert p.synced_at is not None

    def test_size_bytes_nullable(self, app, db):
        with app.app_context():
            p = OverleafProject(overleaf_id="oid-pe3", name="No size")
            db.session.add(p)
            db.session.commit()
            assert p.size_bytes is None

    def test_owner_relationship(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-pe-owner2")
            p = make_project(db, "oid-pe4", owner=owner)
            assert p.owner.overleaf_id == "oid-pe-owner2"

    def test_overleaf_id_unique_constraint(self, app, db):
        from sqlalchemy.exc import IntegrityError
        with app.app_context():
            make_project(db, "oid-pe-dup")
            db.session.add(OverleafProject(overleaf_id="oid-pe-dup", name="Dup"))
            with pytest.raises(IntegrityError):
                db.session.commit()
            db.session.rollback()


# ═══════════════════════════════════════════════════════════════════════════════
# DAO
# ═══════════════════════════════════════════════════════════════════════════════

class TestOverleafProjectDao:

    def test_find_by_overleaf_id_found(self, app, db):
        with app.app_context():
            make_project(db, "oid-dao1", name="Found")
            result = project_dao.find_by_overleaf_id("oid-dao1")
            assert result is not None
            assert result.name == "Found"

    def test_find_by_overleaf_id_not_found(self, app, db):
        with app.app_context():
            assert project_dao.find_by_overleaf_id("nonexistent") is None

    def test_count_all_empty(self, app, db):
        with app.app_context():
            assert project_dao.count_all() == 0

    def test_count_all_multiple(self, app, db):
        with app.app_context():
            for i in range(4):
                make_project(db, f"oid-count{i}")
            assert project_dao.count_all() == 4

    def test_count_by_owner(self, app, db):
        with app.app_context():
            owner1 = make_user(db, "oid-own1")
            owner2 = make_user(db, "oid-own2")
            make_project(db, "oid-bo1", owner=owner1)
            make_project(db, "oid-bo2", owner=owner1)
            make_project(db, "oid-bo3", owner=owner2)
            assert project_dao.count_by_owner(owner1.id) == 2
            assert project_dao.count_by_owner(owner2.id) == 1

    def test_count_by_owner_no_projects(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-own3")
            assert project_dao.count_by_owner(owner.id) == 0


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLER HELPERS (pure functions — no DB needed)
# ═══════════════════════════════════════════════════════════════════════════════

class TestControllerHelpers:

    # ── _fmt_size ────────────────────────────────────────────────────────────

    def test_fmt_size_none_returns_none(self):
        assert _fmt_size(None) is None

    def test_fmt_size_zero_returns_none(self):
        assert _fmt_size(0) is None

    def test_fmt_size_bytes(self):
        assert _fmt_size(512) == "512 B"

    def test_fmt_size_kb(self):
        result = _fmt_size(2048)
        assert "KB" in result

    def test_fmt_size_mb(self):
        result = _fmt_size(5 * 1024 * 1024)
        assert "MB" in result

    def test_fmt_size_gb(self):
        result = _fmt_size(2 * 1024 * 1024 * 1024)
        assert "GB" in result

    # ── _parse_date ──────────────────────────────────────────────────────────

    def test_parse_date_valid(self):
        dt = _parse_date("2024-03-15")
        assert dt is not None
        assert dt.year == 2024 and dt.month == 3 and dt.day == 15

    def test_parse_date_invalid_returns_none(self):
        assert _parse_date("not-a-date") is None

    def test_parse_date_empty_returns_none(self):
        assert _parse_date("") is None

    def test_parse_date_none_returns_none(self):
        assert _parse_date(None) is None

    def test_parse_date_result_is_utc(self):
        dt = _parse_date("2024-01-01")
        assert dt.tzinfo == timezone.utc


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectsService:

    # ── get_project_by_id ─────────────────────────────────────────────────────

    def test_get_project_by_id_found(self, app, db):
        with app.app_context():
            p = make_project(db, "oid-svc1", name="Found Project")
            result = projects_service.get_project_by_id(p.id)
            assert result is not None
            assert result.name == "Found Project"

    def test_get_project_by_id_not_found(self, app, db):
        with app.app_context():
            assert projects_service.get_project_by_id(9999) is None

    # ── get_project_detail_data ───────────────────────────────────────────────

    def test_get_project_detail_data_none_for_missing(self, app, db):
        with app.app_context():
            assert projects_service.get_project_detail_data(9999) is None

    def test_get_project_detail_data_returns_expected_keys(self, app, db):
        with app.app_context():
            p = make_project(db, "oid-svc2")
            data = projects_service.get_project_detail_data(p.id)
            assert data is not None
            assert "project" in data
            assert "members" in data
            assert "sync_logs" in data

    def test_get_project_detail_data_includes_members(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-svc3-own")
            member = make_user(db, "oid-svc3-mem")
            p = make_project(db, "oid-svc3", owner=owner)
            pm = ProjectMember(project=p, user=member, role="collaborator")
            db.session.add(pm)
            db.session.commit()
            data = projects_service.get_project_detail_data(p.id)
            assert len(data["members"]) == 1
            assert data["members"][0].user.overleaf_id == "oid-svc3-mem"

    # ── get_owners_for_filter ─────────────────────────────────────────────────

    def test_get_owners_for_filter_empty(self, app, db):
        with app.app_context():
            assert projects_service.get_owners_for_filter() == []

    def test_get_owners_for_filter_returns_owners_only(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-of1", email="owner@test.com")
            non_owner = make_user(db, "oid-of2", email="nonowner@test.com")
            make_project(db, "oid-of-p1", owner=owner)
            result = projects_service.get_owners_for_filter()
            ids = [u.id for u in result]
            assert owner.id in ids
            assert non_owner.id not in ids

    def test_get_owners_for_filter_no_duplicates(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-of3", email="owner2@test.com")
            make_project(db, "oid-of-p2", owner=owner)
            make_project(db, "oid-of-p3", owner=owner)
            result = projects_service.get_owners_for_filter()
            owner_ids = [u.id for u in result]
            assert owner_ids.count(owner.id) == 1

    # ── get_projects_list_data ────────────────────────────────────────────────

    def test_get_projects_list_data_returns_pagination(self, app, db):
        with app.app_context():
            for i in range(5):
                make_project(db, f"oid-list{i}")
            data = projects_service.get_projects_list_data(page=1, per_page=3)
            assert data["pagination"].total == 5
            assert len(data["pagination"].items) == 3

    def test_get_projects_list_data_search_by_name(self, app, db):
        with app.app_context():
            make_project(db, "oid-search1", name="LaTeX Report")
            make_project(db, "oid-search2", name="Other Project")
            data = projects_service.get_projects_list_data(
                page=1, per_page=10, search="LaTeX"
            )
            assert data["pagination"].total == 1

    def test_get_projects_list_data_filter_by_owner(self, app, db):
        with app.app_context():
            owner1 = make_user(db, "oid-fo1")
            owner2 = make_user(db, "oid-fo2")
            make_project(db, "oid-fp1", owner=owner1)
            make_project(db, "oid-fp2", owner=owner2)
            make_project(db, "oid-fp3", owner=owner1)
            data = projects_service.get_projects_list_data(
                page=1, per_page=10, owner_id=owner1.id
            )
            assert data["pagination"].total == 2

    def test_get_projects_list_data_size_filter_gt(self, app, db):
        """Filtro: proyectos con tamaño > 10 MB (sustituye al antiguo indicador 'large')."""
        with app.app_context():
            make_project(db, "oid-large", size_bytes=20 * 1024 * 1024)
            make_project(db, "oid-small", size_bytes=100)
            data = projects_service.get_projects_list_data(
                page=1, per_page=10, size_op="gt", size_mb=10,
            )
            assert data["pagination"].total == 1

    def test_get_projects_list_data_date_from_filter(self, app, db):
        """Filtro por fecha (sustituye al antiguo indicador 'inactive')."""
        with app.app_context():
            old_date = datetime.now(timezone.utc) - timedelta(days=120)
            p_old = make_project(db, "oid-inactive")
            p_old.last_updated_at = old_date
            p_recent = make_project(db, "oid-active")
            p_recent.last_updated_at = datetime.now(timezone.utc)
            db.session.commit()
            # Solo los actualizados en los últimos 30 días → 1 proyecto
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            data = projects_service.get_projects_list_data(
                page=1, per_page=10, date_from=cutoff,
            )
            assert data["pagination"].total == 1

    def test_get_projects_list_data_member_counts_included(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-mc-own")
            member = make_user(db, "oid-mc-mem")
            p = make_project(db, "oid-mc-proj", owner=owner)
            pm = ProjectMember(project=p, user=member, role="collaborator")
            db.session.add(pm)
            db.session.commit()
            data = projects_service.get_projects_list_data(page=1, per_page=10)
            assert data["member_counts"].get(p.id, 0) == 1

    def test_get_projects_list_data_date_filter_from(self, app, db):
        with app.app_context():
            new_date = datetime.now(timezone.utc)
            old_date = datetime.now(timezone.utc) - timedelta(days=60)
            p_new = make_project(db, "oid-df-new")
            p_new.last_updated_at = new_date
            p_old = make_project(db, "oid-df-old")
            p_old.last_updated_at = old_date
            db.session.commit()
            cutoff = datetime.now(timezone.utc) - timedelta(days=30)
            data = projects_service.get_projects_list_data(
                page=1, per_page=10, date_from=cutoff
            )
            assert data["pagination"].total == 1


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLER
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectsController:

    # ── Redirect when unauthenticated ────────────────────────────────────────

    def test_list_projects_redirects_unauthenticated(self, client):
        resp = client.get("/proyectos/")
        assert resp.status_code in (302, 401)

    def test_project_detail_redirects_unauthenticated(self, client):
        resp = client.get("/proyectos/1")
        assert resp.status_code in (302, 401)

    # ── GET /proyectos/ ────────────────────────────────────────────────────────

    def test_list_projects_renders_ok(self, auth_client):
        resp = auth_client.get("/proyectos/")
        assert resp.status_code == 200

    # ── GET /proyectos/buscar ──────────────────────────────────────────────────

    def test_search_projects_returns_json(self, app, db, auth_client):
        with app.app_context():
            make_project(db, "oid-sc1", name="Search Test")
        resp = auth_client.get("/proyectos/buscar")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "projects" in data
        assert "total" in data

    def test_search_projects_filters_by_name(self, app, db, auth_client):
        with app.app_context():
            make_project(db, "oid-sc2", name="Find This")
            make_project(db, "oid-sc3", name="Other")
        resp = auth_client.get("/proyectos/buscar?q=Find+This")
        data = resp.get_json()
        assert data["total"] == 1
        assert data["projects"][0]["name"] == "Find This"

    def test_search_projects_pagination_keys(self, auth_client):
        resp = auth_client.get("/proyectos/buscar")
        data = resp.get_json()
        for key in ("page", "pages", "has_prev", "has_next"):
            assert key in data

    def test_search_projects_empty_result(self, auth_client):
        resp = auth_client.get("/proyectos/buscar?q=absolutely_not_found")
        data = resp.get_json()
        assert data["total"] == 0
        assert data["projects"] == []

    # ── GET /proyectos/<id> ────────────────────────────────────────────────────

    def test_project_detail_ok(self, app, db, auth_client):
        with app.app_context():
            p = make_project(db, "oid-ctrl-det1", name="Detail Test")
            pid = p.id
        resp = auth_client.get(f"/proyectos/{pid}")
        assert resp.status_code == 200

    def test_project_detail_404(self, auth_client):
        resp = auth_client.get("/proyectos/999999")
        assert resp.status_code == 404
