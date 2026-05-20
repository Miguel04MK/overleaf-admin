"""
tests/test_users.py
-------------------
Tests for the Users domain: entity, DAO, service and controller.

Run with:
    python -m pytest tests/test_users.py -v
"""
import pytest
from datetime import datetime, timezone, timedelta

from app.model.entities.overleaf_user import OverleafUser, QUOTA_WARNING_PCT, QUOTA_DANGER_PCT
from app.model.entities import overleaf_user_dao as user_dao
from app.model.services import users_service
from tests.conftest import make_user, make_project


# ═══════════════════════════════════════════════════════════════════════════════
# ENTITY
# ═══════════════════════════════════════════════════════════════════════════════

class TestOverleafUserEntity:
    """Unit tests for OverleafUser computed properties (no DB needed)."""

    def _user(self, **kwargs):
        """Build an unsaved OverleafUser with sensible defaults."""
        defaults = dict(overleaf_id="oid-x", email="x@test.com")
        defaults.update(kwargs)
        return OverleafUser(**defaults)

    # ── display_name ────────────────────────────────────────────────────────

    def test_display_name_full_name(self):
        u = self._user(first_name="Ana", last_name="García")
        assert u.display_name == "Ana García"

    def test_display_name_first_only(self):
        u = self._user(first_name="Ana", last_name=None)
        assert u.display_name == "Ana"

    def test_display_name_falls_back_to_email(self):
        u = self._user(first_name=None, last_name=None, email="fallback@test.com")
        assert u.display_name == "fallback@test.com"

    def test_display_name_falls_back_to_overleaf_id(self):
        u = self._user(first_name=None, last_name=None, email=None, overleaf_id="oid-abc")
        assert u.display_name == "oid-abc"

    # ── quota_percent ────────────────────────────────────────────────────────

    def test_quota_percent_none_when_no_quota(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-qp1", max_quota_bytes=None)
            assert u.quota_percent is None

    def test_quota_percent_zero_when_no_projects(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-qp2", max_quota_bytes=1000)
            assert u.quota_percent == 0.0

    def test_quota_percent_calculated(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-qp3", max_quota_bytes=1000)
            make_project(db, "proj-qp3", owner=u, size_bytes=500)
            assert u.quota_percent == 50.0

    def test_quota_percent_over_100(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-qp4", max_quota_bytes=100)
            make_project(db, "proj-qp4", owner=u, size_bytes=150)
            assert u.quota_percent == 150.0

    # ── quota_status ────────────────────────────────────────────────────────

    def test_quota_status_secondary_when_no_quota(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-qs1")
            assert u.quota_status == "secondary"

    def test_quota_status_success_when_low(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-qs2", max_quota_bytes=1000)
            make_project(db, "proj-qs2", owner=u, size_bytes=100)
            assert u.quota_status == "success"

    def test_quota_status_warning_at_threshold(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-qs3", max_quota_bytes=1000)
            make_project(db, "proj-qs3", owner=u, size_bytes=QUOTA_WARNING_PCT * 10)
            assert u.quota_status == "warning"

    def test_quota_status_danger_at_threshold(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-qs4", max_quota_bytes=1000)
            make_project(db, "proj-qs4", owner=u, size_bytes=QUOTA_DANGER_PCT * 10)
            assert u.quota_status == "danger"

    # ── quota_exceeded ───────────────────────────────────────────────────────

    def test_quota_exceeded_false_when_no_quota(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-qe1")
            assert u.quota_exceeded is False

    def test_quota_exceeded_false_when_under(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-qe2", max_quota_bytes=1000)
            make_project(db, "proj-qe2", owner=u, size_bytes=999)
            assert u.quota_exceeded is False

    def test_quota_exceeded_true_when_over(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-qe3", max_quota_bytes=100)
            make_project(db, "proj-qe3", owner=u, size_bytes=101)
            assert u.quota_exceeded is True

    # ── quota_used_fmt / quota_max_fmt ───────────────────────────────────────

    def test_quota_max_fmt_none(self):
        u = self._user(max_quota_bytes=None)
        assert u.quota_max_fmt == "Sin limite"

    def test_quota_max_fmt_bytes(self):
        u = self._user(max_quota_bytes=512)
        assert "512" in u.quota_max_fmt and "B" in u.quota_max_fmt

    def test_quota_max_fmt_mb(self):
        u = self._user(max_quota_bytes=5 * 1024 * 1024)
        assert "MB" in u.quota_max_fmt

    # ── repr ────────────────────────────────────────────────────────────────

    def test_repr_contains_email(self):
        u = self._user(email="repr@test.com")
        assert "repr@test.com" in repr(u)


# ═══════════════════════════════════════════════════════════════════════════════
# DAO
# ═══════════════════════════════════════════════════════════════════════════════

class TestOverleafUserDao:

    def test_find_by_overleaf_id_found(self, app, db):
        with app.app_context():
            make_user(db, "oid-dao1", email="dao1@test.com")
            result = user_dao.find_by_overleaf_id("oid-dao1")
            assert result is not None
            assert result.email == "dao1@test.com"

    def test_find_by_overleaf_id_not_found(self, app, db):
        with app.app_context():
            assert user_dao.find_by_overleaf_id("nonexistent") is None

    def test_find_by_email_found(self, app, db):
        with app.app_context():
            make_user(db, "oid-dao2", email="find@test.com")
            result = user_dao.find_by_email("find@test.com")
            assert result is not None
            assert result.overleaf_id == "oid-dao2"

    def test_find_by_email_not_found(self, app, db):
        with app.app_context():
            assert user_dao.find_by_email("ghost@test.com") is None

    def test_count_all_empty(self, app, db):
        with app.app_context():
            assert user_dao.count_all() == 0

    def test_count_all_multiple(self, app, db):
        with app.app_context():
            make_user(db, "oid-c1")
            make_user(db, "oid-c2")
            make_user(db, "oid-c3")
            assert user_dao.count_all() == 3

    def test_count_admins_none(self, app, db):
        with app.app_context():
            make_user(db, "oid-ca1", is_admin=False)
            assert user_dao.count_admins() == 0

    def test_count_admins_filters_correctly(self, app, db):
        with app.app_context():
            make_user(db, "oid-ca2", is_admin=True)
            make_user(db, "oid-ca3", is_admin=False)
            make_user(db, "oid-ca4", is_admin=True)
            assert user_dao.count_admins() == 2


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE
# ═══════════════════════════════════════════════════════════════════════════════

class TestUsersService:

    # ── search_users ─────────────────────────────────────────────────────────

    def test_search_users_no_filter_returns_all(self, app, db):
        with app.app_context():
            make_user(db, "oid-s1", email="alpha@test.com")
            make_user(db, "oid-s2", email="beta@test.com")
            result = users_service.search_users()
            assert len(result) == 2

    def test_search_users_filter_by_email(self, app, db):
        with app.app_context():
            make_user(db, "oid-s3", email="find_me@test.com")
            make_user(db, "oid-s4", email="other@test.com")
            result = users_service.search_users(q="find_me")
            assert len(result) == 1
            assert result[0].email == "find_me@test.com"

    def test_search_users_filter_by_first_name(self, app, db):
        with app.app_context():
            make_user(db, "oid-s5", first_name="Lucía")
            make_user(db, "oid-s6", first_name="Carlos")
            result = users_service.search_users(q="lucía")
            assert len(result) == 1

    def test_search_users_sort_email_asc(self, app, db):
        with app.app_context():
            make_user(db, "oid-s7", email="z_last@test.com")
            make_user(db, "oid-s8", email="a_first@test.com")
            result = users_service.search_users(sort="email", order="asc")
            assert result[0].email == "a_first@test.com"

    def test_search_users_sort_email_desc(self, app, db):
        with app.app_context():
            make_user(db, "oid-s9", email="z_last@test.com")
            make_user(db, "oid-s10", email="a_first@test.com")
            result = users_service.search_users(sort="email", order="desc")
            assert result[0].email == "z_last@test.com"

    def test_search_users_limit(self, app, db):
        with app.app_context():
            for i in range(5):
                make_user(db, f"oid-lim{i}", email=f"u{i}@test.com")
            result = users_service.search_users(limit=3)
            assert len(result) == 3

    def test_search_users_no_results(self, app, db):
        with app.app_context():
            make_user(db, "oid-s11", email="someone@test.com")
            result = users_service.search_users(q="nobody")
            assert result == []

    # ── get_users_page ───────────────────────────────────────────────────────

    def test_get_users_page_returns_pagination(self, app, db):
        with app.app_context():
            for i in range(5):
                make_user(db, f"oid-pg{i}", email=f"pg{i}@test.com")
            pagination = users_service.get_users_page(page=1, per_page=3)
            assert pagination.total == 5
            assert len(pagination.items) == 3

    def test_get_users_page_second_page(self, app, db):
        with app.app_context():
            for i in range(5):
                make_user(db, f"oid-pg2-{i}", email=f"pg2u{i}@test.com")
            pagination = users_service.get_users_page(page=2, per_page=3)
            assert len(pagination.items) == 2

    def test_get_users_page_with_search(self, app, db):
        with app.app_context():
            make_user(db, "oid-pgs1", email="search_hit@test.com")
            make_user(db, "oid-pgs2", email="miss@test.com")
            pagination = users_service.get_users_page(page=1, per_page=10, search="search_hit")
            assert pagination.total == 1

    # ── get_user_by_id ────────────────────────────────────────────────────────

    def test_get_user_by_id_found(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-gid1")
            result = users_service.get_user_by_id(u.id)
            assert result is not None
            assert result.overleaf_id == "oid-gid1"

    def test_get_user_by_id_not_found(self, app, db):
        with app.app_context():
            assert users_service.get_user_by_id(9999) is None

    # ── get_user_detail_data ──────────────────────────────────────────────────

    def test_get_user_detail_data_none_for_missing(self, app, db):
        with app.app_context():
            assert users_service.get_user_detail_data(9999) is None

    def test_get_user_detail_data_returns_expected_keys(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-det1")
            data = users_service.get_user_detail_data(u.id)
            assert data is not None
            for key in ("user", "projects_pagination", "collab_memberships",
                        "is_active", "recent_activity",
                        "chart_storage", "chart_projects", "chart_collabs"):
                assert key in data

    def test_get_user_detail_data_inactive_user(self, app, db):
        with app.app_context():
            old_login = datetime.now(timezone.utc) - timedelta(days=120)
            u = make_user(db, "oid-det2")
            u.last_login_at = old_login
            db.session.commit()
            data = users_service.get_user_detail_data(u.id)
            assert data["is_active"] is False

    def test_get_user_detail_data_active_user(self, app, db):
        with app.app_context():
            recent_login = datetime.now(timezone.utc) - timedelta(days=10)
            u = make_user(db, "oid-det3")
            u.last_login_at = recent_login
            db.session.commit()
            data = users_service.get_user_detail_data(u.id)
            assert data["is_active"] is True

    def test_get_user_detail_data_chart_storage_top10(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-det4")
            for i in range(12):
                make_project(db, f"proj-det4-{i}", owner=u, size_bytes=(i + 1) * 1000)
            data = users_service.get_user_detail_data(u.id)
            assert len(data["chart_storage"]["labels"]) <= 10

    # ── set_user_quota ────────────────────────────────────────────────────────

    def test_set_user_quota_ok(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-sq1")
            ok, msg = users_service.set_user_quota(u.id, 1024 * 1024)
            assert ok is True
            refreshed = users_service.get_user_by_id(u.id)
            assert refreshed.max_quota_bytes == 1024 * 1024

    def test_set_user_quota_none_removes_limit(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-sq2", max_quota_bytes=999)
            ok, _ = users_service.set_user_quota(u.id, None)
            assert ok is True
            assert users_service.get_user_by_id(u.id).max_quota_bytes is None

    def test_set_user_quota_negative_fails(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-sq3")
            ok, msg = users_service.set_user_quota(u.id, -1)
            assert ok is False
            assert "negativa" in msg.lower()

    def test_set_user_quota_user_not_found(self, app, db):
        with app.app_context():
            ok, msg = users_service.set_user_quota(9999, 100)
            assert ok is False


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLER
# ═══════════════════════════════════════════════════════════════════════════════

class TestUsersController:

    # ── Redirect when unauthenticated ────────────────────────────────────────

    def test_list_users_redirects_unauthenticated(self, client):
        resp = client.get("/usuarios/")
        assert resp.status_code in (302, 401)

    def test_user_detail_redirects_unauthenticated(self, client):
        resp = client.get("/usuarios/1")
        assert resp.status_code in (302, 401)

    # ── GET /usuarios/ ────────────────────────────────────────────────────────

    def test_list_users_renders_ok(self, auth_client):
        resp = auth_client.get("/usuarios/")
        assert resp.status_code == 200

    # ── GET /usuarios/buscar ──────────────────────────────────────────────────

    def test_search_returns_json(self, app, db, auth_client):
        with app.app_context():
            make_user(db, "oid-ctrl1", email="ctrl1@test.com")
        resp = auth_client.get("/usuarios/buscar")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "users" in data
        assert "total" in data

    def test_search_filters_by_q(self, app, db, auth_client):
        with app.app_context():
            make_user(db, "oid-ctrl2", email="findme@test.com")
            make_user(db, "oid-ctrl3", email="other@test.com")
        resp = auth_client.get("/usuarios/buscar?q=findme")
        data = resp.get_json()
        assert data["total"] == 1
        assert data["users"][0]["email"] == "findme@test.com"

    def test_search_empty_result(self, app, db, auth_client):
        with app.app_context():
            make_user(db, "oid-ctrl4", email="someone@test.com")
        resp = auth_client.get("/usuarios/buscar?q=nobody")
        data = resp.get_json()
        assert data["total"] == 0
        assert data["users"] == []

    # ── GET /usuarios/<id> ────────────────────────────────────────────────────

    def test_user_detail_ok(self, app, db, auth_client):
        with app.app_context():
            u = make_user(db, "oid-ctrl5")
            uid = u.id
        resp = auth_client.get(f"/usuarios/{uid}")
        assert resp.status_code == 200

    def test_user_detail_404(self, auth_client):
        resp = auth_client.get("/usuarios/999999")
        assert resp.status_code == 404

    # ── POST /usuarios/<id>/cuota ─────────────────────────────────────────────

    def test_set_quota_redirects_on_success(self, app, db, auth_client):
        with app.app_context():
            u = make_user(db, "oid-ctrl6")
            uid = u.id
        resp = auth_client.post(
            f"/usuarios/{uid}/cuota",
            data={"quota_value": "500", "quota_unit": "MB"},
        )
        assert resp.status_code == 302
        assert f"/usuarios/{uid}" in resp.headers["Location"]

    def test_set_quota_clears_quota_with_zero(self, app, db, auth_client):
        with app.app_context():
            u = make_user(db, "oid-ctrl7", max_quota_bytes=999)
            uid = u.id
        auth_client.post(
            f"/usuarios/{uid}/cuota",
            data={"quota_value": "0", "quota_unit": "MB"},
        )
        with app.app_context():
            refreshed = users_service.get_user_by_id(uid)
            assert refreshed.max_quota_bytes is None

    def test_set_quota_invalid_value_redirects(self, app, db, auth_client):
        with app.app_context():
            u = make_user(db, "oid-ctrl8")
            uid = u.id
        resp = auth_client.post(
            f"/usuarios/{uid}/cuota",
            data={"quota_value": "not-a-number", "quota_unit": "MB"},
        )
        # Should redirect back to the detail page
        assert resp.status_code == 302
