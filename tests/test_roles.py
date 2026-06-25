"""
tests/test_roles.py
-------------------
Tests for the Roles domain: entity, service (queries + mutations) and controller.

The roles_service plays the role of DAO here — there is no separate roles_dao
module; all queries are implemented directly in the service layer.

Run with:
    python -m pytest tests/test_roles.py -v
"""
import pytest
from datetime import datetime, timezone

from app.model.entities.role import Role, ROLE_PRESETS, MB, GB
from app.model.entities.role_change_log import RoleChangeLog
from app.model.services import roles_service
from tests.conftest import make_user, make_project, make_role


# ═══════════════════════════════════════════════════════════════════════════════
# ENTITY — Role
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoleEntity:

    def _role(self, **kwargs):
        defaults = dict(name="testrole", color="secondary")
        defaults.update(kwargs)
        return Role(**defaults)

    # ── storage_quota_fmt ────────────────────────────────────────────────────

    def test_quota_fmt_unlimited(self):
        r = self._role(storage_quota_bytes=None)
        assert r.storage_quota_fmt == "Ilimitado"

    def test_quota_fmt_bytes(self):
        r = self._role(storage_quota_bytes=512)
        assert "512" in r.storage_quota_fmt and "B" in r.storage_quota_fmt

    def test_quota_fmt_mb(self):
        r = self._role(storage_quota_bytes=500 * MB)
        assert "MB" in r.storage_quota_fmt

    def test_quota_fmt_gb(self):
        r = self._role(storage_quota_bytes=5 * GB)
        assert "GB" in r.storage_quota_fmt

    # ── max_projects_fmt ──────────────────────────────────────────────────────

    def test_max_projects_fmt_unlimited(self):
        r = self._role(max_projects=None)
        assert r.max_projects_fmt == "Ilimitado"

    def test_max_projects_fmt_number(self):
        r = self._role(max_projects=20)
        assert r.max_projects_fmt == "20"

    # ── repr ─────────────────────────────────────────────────────────────────

    def test_repr_contains_name(self):
        r = self._role(name="profesor")
        assert "profesor" in repr(r)

    # ── ROLE_PRESETS ──────────────────────────────────────────────────────────

    def test_presets_define_three_roles(self):
        assert set(ROLE_PRESETS.keys()) == {"alumno", "profesor", "admin"}

    def test_alumno_preset_is_default(self):
        assert ROLE_PRESETS["alumno"]["is_default"] is True

    def test_profesor_not_default(self):
        assert ROLE_PRESETS["profesor"]["is_default"] is False

    def test_admin_has_unlimited_quota(self):
        assert ROLE_PRESETS["admin"]["storage_quota_bytes"] is None

    def test_admin_has_unlimited_projects(self):
        assert ROLE_PRESETS["admin"]["max_projects"] is None

    def test_alumno_quota_is_500mb(self):
        assert ROLE_PRESETS["alumno"]["storage_quota_bytes"] == 500 * MB

    def test_profesor_quota_is_5gb(self):
        assert ROLE_PRESETS["profesor"]["storage_quota_bytes"] == 5 * GB


# ═══════════════════════════════════════════════════════════════════════════════
# ENTITY — RoleChangeLog
# ═══════════════════════════════════════════════════════════════════════════════

class TestRoleChangeLogEntity:

    def test_repr_contains_action(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-log1")
            default = roles_service.get_default_role()
            log = RoleChangeLog(
                user_id=u.id,
                role_to_id=default.id,
                action="assigned",
                changed_by="system",
                changed_at=datetime.now(timezone.utc),
            )
            db.session.add(log)
            db.session.commit()
            assert "assigned" in repr(log)

    def test_log_stores_reason(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-log2")
            default = roles_service.get_default_role()
            log = RoleChangeLog(
                user_id=u.id,
                role_to_id=default.id,
                action="assigned",
                changed_by="admin",
                changed_at=datetime.now(timezone.utc),
                reason="Test reason",
            )
            db.session.add(log)
            db.session.commit()
            assert log.reason == "Test reason"


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Queries (acting as DAO)
# ═══════════════════════════════════════════════════════════════════════════════

class TestRolesServiceQueries:

    # ── seed_default_roles ────────────────────────────────────────────────────

    def test_seed_creates_three_roles(self, app, db):
        with app.app_context():
            roles = roles_service.get_all_roles()
            names = {r.name for r in roles}
            assert names == {"alumno", "profesor", "admin"}

    def test_seed_is_idempotent(self, app, db):
        with app.app_context():
            roles_service.seed_default_roles()
            roles_service.seed_default_roles()
            assert len(roles_service.get_all_roles()) == 3

    # ── get_all_roles ─────────────────────────────────────────────────────────

    def test_get_all_roles_returns_list(self, app, db):
        with app.app_context():
            roles = roles_service.get_all_roles()
            assert isinstance(roles, list)
            assert len(roles) >= 3

    def test_get_all_roles_default_first(self, app, db):
        with app.app_context():
            roles = roles_service.get_all_roles()
            # is_default=True roles come first (ORDER BY is_default DESC)
            assert roles[0].is_default is True

    # ── get_role_by_id ────────────────────────────────────────────────────────

    def test_get_role_by_id_found(self, app, db):
        with app.app_context():
            default = roles_service.get_default_role()
            result = roles_service.get_role_by_id(default.id)
            assert result is not None
            assert result.id == default.id

    def test_get_role_by_id_not_found(self, app, db):
        with app.app_context():
            assert roles_service.get_role_by_id(9999) is None

    # ── get_role_by_name ──────────────────────────────────────────────────────

    def test_get_role_by_name_found(self, app, db):
        with app.app_context():
            result = roles_service.get_role_by_name("alumno")
            assert result is not None
            assert result.name == "alumno"

    def test_get_role_by_name_not_found(self, app, db):
        with app.app_context():
            assert roles_service.get_role_by_name("nonexistent") is None

    def test_get_role_by_name_case_insensitive(self, app, db):
        with app.app_context():
            result = roles_service.get_role_by_name("ALUMNO")
            assert result is not None

    # ── get_default_role ──────────────────────────────────────────────────────

    def test_get_default_role_returns_alumno(self, app, db):
        with app.app_context():
            default = roles_service.get_default_role()
            assert default is not None
            assert default.is_default is True

    # ── get_effective_role ────────────────────────────────────────────────────

    def test_get_effective_role_returns_assigned_role(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-eff1", role=profesor)
            effective = roles_service.get_effective_role(u)
            assert effective.name == "profesor"

    def test_get_effective_role_falls_back_to_default(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-eff2")  # no role assigned
            effective = roles_service.get_effective_role(u)
            assert effective is not None
            assert effective.is_default is True

    # ── get_role_stats ────────────────────────────────────────────────────────

    def test_get_role_stats_counts_users(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            make_user(db, "oid-rs1", role=profesor)
            make_user(db, "oid-rs2", role=profesor)
            stats = roles_service.get_role_stats_by_id()
            assert stats.get(profesor.id, 0) == 2

    def test_get_role_stats_null_role_counted_in_default(self, app, db):
        with app.app_context():
            # Users with no role assigned → count under default role
            make_user(db, "oid-rs3")  # role_id = NULL
            default = roles_service.get_default_role()
            stats = roles_service.get_role_stats_by_id()
            assert stats.get(default.id, 0) >= 1

    def test_get_role_stats_empty_db_returns_dict(self, app, db):
        with app.app_context():
            stats = roles_service.get_role_stats()
            assert isinstance(stats, dict)

    # ── get_role_change_logs ──────────────────────────────────────────────────

    def test_get_role_change_logs_empty(self, app, db):
        with app.app_context():
            pagination = roles_service.get_role_change_logs()
            assert pagination.total == 0

    def test_get_role_change_logs_after_assign(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-logs1")
            roles_service.assign_role(u.id, profesor.id, actor="admin")
            pagination = roles_service.get_role_change_logs()
            assert pagination.total == 1

    def test_get_role_change_logs_filter_by_user(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u1 = make_user(db, "oid-logs2")
            u2 = make_user(db, "oid-logs3")
            roles_service.assign_role(u1.id, profesor.id, actor="admin")
            roles_service.assign_role(u2.id, profesor.id, actor="admin")
            pagination = roles_service.get_role_change_logs(user_id=u1.id)
            assert pagination.total == 1
            assert pagination.items[0].user_id == u1.id

    # ── search_users_for_role ─────────────────────────────────────────────────

    def test_search_users_for_role_finds_by_email(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            make_user(db, "oid-sur1", email="searchable@test.com", role=profesor)
            results = roles_service.search_users_for_role(profesor.id, "searchable")
            assert len(results) == 1
            assert results[0]["email"] == "searchable@test.com"

    def test_search_users_for_role_has_role_flag_true(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            make_user(db, "oid-sur2", email="has_it@test.com", role=profesor)
            results = roles_service.search_users_for_role(profesor.id, "has_it")
            assert results[0]["has_role"] is True

    def test_search_users_for_role_has_role_flag_false(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            alumno = roles_service.get_role_by_name("alumno")
            make_user(db, "oid-sur3", email="different@test.com", role=alumno)
            results = roles_service.search_users_for_role(profesor.id, "different")
            assert results[0]["has_role"] is False

    def test_search_users_for_role_default_includes_null_role(self, app, db):
        with app.app_context():
            default = roles_service.get_default_role()
            make_user(db, "oid-sur4", email="norole@test.com")  # role_id = NULL
            results = roles_service.search_users_for_role(default.id, "norole")
            assert len(results) == 1
            assert results[0]["has_role"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Mutations
# ═══════════════════════════════════════════════════════════════════════════════

class TestRolesServiceMutations:

    # ── assign_role ───────────────────────────────────────────────────────────

    def test_assign_role_ok(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-ar1")
            ok, msg = roles_service.assign_role(u.id, profesor.id, actor="admin")
            assert ok is True
            refreshed = roles_service.get_role_by_id(profesor.id)
            u_refreshed = db.session.get(u.__class__, u.id)
            assert u_refreshed.role_id == profesor.id

    def test_assign_role_also_sets_quota(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-ar2")
            roles_service.assign_role(u.id, profesor.id, actor="admin")
            from app.model.entities.overleaf_user import OverleafUser
            refreshed = db.session.get(OverleafUser, u.id)
            assert refreshed.max_quota_bytes == profesor.storage_quota_bytes

    def test_assign_role_creates_audit_log(self, app, db):
        """Un usuario con role_id=NULL pero con rol por defecto existente
        es semánticamente "cambiado de default a X", no "asignado por primera vez".
        El bug previo registraba "Sin rol → X" en estos casos."""
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            default  = roles_service.get_default_role()  # alumno
            u = make_user(db, "oid-ar3")  # role_id=NULL pero default existe
            roles_service.assign_role(u.id, profesor.id, actor="testactor")
            log = roles_service.get_role_change_logs(user_id=u.id).items[0]
            assert log.changed_by == "testactor"
            # Con el fix, debe quedar como "changed" desde el rol efectivo (default)
            assert log.action == "changed"
            assert log.role_from_id == default.id
            assert log.role_from_name == default.name
            assert log.role_to_id == profesor.id

    def test_assign_role_uses_effective_old_role_for_log(self, app, db):
        """Bug fix: el log debe mostrar el rol EFECTIVO (con fallback al default)
        no None. Si user.role_id es NULL pero existe rol por defecto, role_from_id
        del log debe apuntar al default — no "Sin rol → X"."""
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            default  = roles_service.get_default_role()
            # Caso 1: usuario sin rol explícito (role_id=NULL)
            u = make_user(db, "oid-bug1")
            assert u.role_id is None
            roles_service.assign_role(u.id, profesor.id, actor="admin")
            log = roles_service.get_role_change_logs(user_id=u.id).items[0]
            assert log.role_from_id == default.id, (
                "role_from debe ser el rol efectivo (default), no None"
            )
            assert log.role_from_name == default.name

    def test_assign_role_rejects_assigning_default_to_implicit_default_user(self, app, db):
        """Si un usuario tiene role_id=NULL (efectivamente default) y le
        asignas el default, debe rechazarse: ya lo tiene."""
        with app.app_context():
            default = roles_service.get_default_role()
            u = make_user(db, "oid-bug2")  # role_id=NULL
            ok, msg = roles_service.assign_role(u.id, default.id, actor="admin")
            assert ok is False
            assert "ya tiene" in msg.lower()

    def test_assign_role_same_role_fails(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-ar4", role=profesor)
            ok, msg = roles_service.assign_role(u.id, profesor.id, actor="admin")
            assert ok is False
            assert "ya tiene" in msg.lower()

    def test_assign_role_user_not_found(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            ok, msg = roles_service.assign_role(9999, profesor.id, actor="admin")
            assert ok is False

    def test_assign_role_role_not_found(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-ar5")
            ok, msg = roles_service.assign_role(u.id, 9999, actor="admin")
            assert ok is False

    def test_assign_role_stores_reason(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-ar6")
            roles_service.assign_role(u.id, profesor.id, actor="admin", reason="Upgrade")
            log = roles_service.get_role_change_logs(user_id=u.id).items[0]
            assert log.reason == "Upgrade"

    # ── remove_role ───────────────────────────────────────────────────────────

    def test_remove_role_resets_to_default(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            default = roles_service.get_default_role()
            u = make_user(db, "oid-rr1", role=profesor)
            ok, msg = roles_service.remove_role(u.id, actor="admin")
            assert ok is True
            from app.model.entities.overleaf_user import OverleafUser
            refreshed = db.session.get(OverleafUser, u.id)
            assert refreshed.role_id == default.id

    def test_remove_role_also_resets_quota(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            default = roles_service.get_default_role()
            u = make_user(db, "oid-rr2", role=profesor)
            roles_service.remove_role(u.id, actor="admin")
            from app.model.entities.overleaf_user import OverleafUser
            refreshed = db.session.get(OverleafUser, u.id)
            assert refreshed.max_quota_bytes == default.storage_quota_bytes

    def test_remove_role_creates_audit_log(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-rr3", role=profesor)
            roles_service.remove_role(u.id, actor="remover")
            log = roles_service.get_role_change_logs(user_id=u.id).items[0]
            assert log.action == "removed"
            assert log.changed_by == "remover"

    def test_remove_role_user_already_default_fails(self, app, db):
        with app.app_context():
            default = roles_service.get_default_role()
            u = make_user(db, "oid-rr4", role=default)
            ok, msg = roles_service.remove_role(u.id, actor="admin")
            assert ok is False

    def test_remove_role_user_without_role_fails(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-rr5")  # role_id = NULL
            ok, msg = roles_service.remove_role(u.id, actor="admin")
            assert ok is False

    def test_remove_role_user_not_found(self, app, db):
        with app.app_context():
            ok, msg = roles_service.remove_role(9999, actor="admin")
            assert ok is False

    # ── last-admin safety guard ───────────────────────────────────────────────

    def test_cannot_reassign_last_admin(self, app, db):
        with app.app_context():
            admin_role = roles_service.get_role_by_name("admin")
            alumno_role = roles_service.get_role_by_name("alumno")
            # Assign admin role to a user (making them the only admin)
            u = make_user(db, "oid-la1")
            roles_service.assign_role(u.id, admin_role.id, actor="system")
            # Try to move them away from admin — should be blocked
            ok, msg = roles_service.assign_role(u.id, alumno_role.id, actor="system")
            assert ok is False
            assert "último" in msg.lower() or "admin" in msg.lower()

    def test_cannot_remove_last_admin(self, app, db):
        with app.app_context():
            admin_role = roles_service.get_role_by_name("admin")
            u = make_user(db, "oid-la2")
            roles_service.assign_role(u.id, admin_role.id, actor="system")
            ok, msg = roles_service.remove_role(u.id, actor="system")
            assert ok is False

    def test_can_reassign_admin_when_multiple_exist(self, app, db):
        with app.app_context():
            admin_role = roles_service.get_role_by_name("admin")
            alumno_role = roles_service.get_role_by_name("alumno")
            u1 = make_user(db, "oid-la3")
            u2 = make_user(db, "oid-la4")
            roles_service.assign_role(u1.id, admin_role.id, actor="system")
            roles_service.assign_role(u2.id, admin_role.id, actor="system")
            # Now u1 can be moved away because u2 is still admin
            ok, _ = roles_service.assign_role(u1.id, alumno_role.id, actor="system")
            assert ok is True

    # ── update_role_config ────────────────────────────────────────────────────

    def test_update_role_config_description(self, app, db):
        with app.app_context():
            alumno = roles_service.get_role_by_name("alumno")
            ok, _ = roles_service.update_role_config(
                alumno.id, description="Nueva descripción",
                storage_quota_bytes=alumno.storage_quota_bytes,
                max_projects=alumno.max_projects,
            )
            assert ok is True
            refreshed = roles_service.get_role_by_id(alumno.id)
            assert refreshed.description == "Nueva descripción"

    def test_update_role_config_quota(self, app, db):
        with app.app_context():
            alumno = roles_service.get_role_by_name("alumno")
            new_quota = 1 * GB
            ok, _ = roles_service.update_role_config(
                alumno.id,
                description=alumno.description,
                storage_quota_bytes=new_quota,
                max_projects=alumno.max_projects,
            )
            assert ok is True
            assert roles_service.get_role_by_id(alumno.id).storage_quota_bytes == new_quota

    def test_update_role_config_max_projects(self, app, db):
        with app.app_context():
            alumno = roles_service.get_role_by_name("alumno")
            ok, _ = roles_service.update_role_config(
                alumno.id,
                description=alumno.description,
                storage_quota_bytes=alumno.storage_quota_bytes,
                max_projects=99,
            )
            assert ok is True
            assert roles_service.get_role_by_id(alumno.id).max_projects == 99

    def test_update_role_config_not_found(self, app, db):
        with app.app_context():
            ok, msg = roles_service.update_role_config(
                9999, description="x", storage_quota_bytes=None, max_projects=None
            )
            assert ok is False

    # ── update_role_config: is_default ────────────────────────────────────────

    def test_update_promotes_to_default_and_unsets_previous(self, app, db):
        with app.app_context():
            prev_default = roles_service.get_default_role()  # 'alumno'
            profesor     = roles_service.get_role_by_name("profesor")
            ok, _ = roles_service.update_role_config(
                profesor.id,
                description=profesor.description,
                storage_quota_bytes=profesor.storage_quota_bytes,
                max_projects=profesor.max_projects,
                is_default=True,
            )
            assert ok is True
            from app.model.entities.role import Role
            assert db.session.get(Role, profesor.id).is_default is True
            assert db.session.get(Role, prev_default.id).is_default is False

    def test_update_cannot_unset_default(self, app, db):
        """Si se intenta desmarcar el rol por defecto actual, debe fallar."""
        with app.app_context():
            default = roles_service.get_default_role()
            ok, msg = roles_service.update_role_config(
                default.id,
                description=default.description,
                storage_quota_bytes=default.storage_quota_bytes,
                max_projects=default.max_projects,
                is_default=False,
            )
            assert ok is False
            assert "por defecto" in msg.lower()
            from app.model.entities.role import Role
            assert db.session.get(Role, default.id).is_default is True

    def test_update_keeps_default_when_omitted(self, app, db):
        """is_default=None → no se toca el flag."""
        with app.app_context():
            default = roles_service.get_default_role()
            ok, _ = roles_service.update_role_config(
                default.id,
                description="cambio",
                storage_quota_bytes=default.storage_quota_bytes,
                max_projects=default.max_projects,
                # is_default omitido → None
            )
            assert ok is True
            from app.model.entities.role import Role
            assert db.session.get(Role, default.id).is_default is True

    # ── create_role ───────────────────────────────────────────────────────────

    def test_create_role_ok(self, app, db):
        with app.app_context():
            ok, msg, role = roles_service.create_role(
                name="doctorado", description="PhD students",
                storage_quota_bytes=10 * GB, max_projects=80,
                is_default=False, color="info", actor="admin",
            )
            assert ok is True
            assert role is not None
            assert role.name == "doctorado"
            assert role.storage_quota_bytes == 10 * GB
            assert role.max_projects == 80

    def test_create_role_normalizes_to_lowercase(self, app, db):
        with app.app_context():
            ok, _, role = roles_service.create_role(
                name="DocTorAdo", description=None,
                storage_quota_bytes=None, max_projects=None,
                actor="admin",
            )
            assert ok is True
            assert role.name == "doctorado"

    def test_create_role_duplicate_name_fails(self, app, db):
        with app.app_context():
            # 'alumno' ya existe del seed
            ok, msg, role = roles_service.create_role(
                name="alumno", description=None,
                storage_quota_bytes=None, max_projects=None,
                actor="admin",
            )
            assert ok is False
            assert role is None
            assert "existe" in msg.lower()

    def test_create_role_duplicate_case_insensitive(self, app, db):
        with app.app_context():
            ok, _, _ = roles_service.create_role(
                name="ALUMNO", description=None,
                storage_quota_bytes=None, max_projects=None,
                actor="admin",
            )
            assert ok is False

    def test_create_role_empty_name_fails(self, app, db):
        with app.app_context():
            ok, msg, _ = roles_service.create_role(
                name="   ", description=None,
                storage_quota_bytes=None, max_projects=None,
                actor="admin",
            )
            assert ok is False
            assert "obligatorio" in msg.lower()

    def test_create_role_negative_quota_fails(self, app, db):
        with app.app_context():
            ok, msg, _ = roles_service.create_role(
                name="negroles", description=None,
                storage_quota_bytes=-1, max_projects=None,
                actor="admin",
            )
            assert ok is False
            assert "negativa" in msg.lower()

    def test_create_role_invalid_max_projects_fails(self, app, db):
        with app.app_context():
            ok, msg, _ = roles_service.create_role(
                name="zeroproj", description=None,
                storage_quota_bytes=None, max_projects=0,
                actor="admin",
            )
            assert ok is False

    def test_create_role_unlimited_quota_and_projects(self, app, db):
        with app.app_context():
            ok, _, role = roles_service.create_role(
                name="unlimited", description=None,
                storage_quota_bytes=None, max_projects=None,
                actor="admin",
            )
            assert ok is True
            assert role.storage_quota_bytes is None
            assert role.max_projects is None

    def test_create_role_as_default_unsets_previous(self, app, db):
        with app.app_context():
            prev_default = roles_service.get_default_role()
            assert prev_default is not None  # 'alumno' por seed
            ok, _, new_role = roles_service.create_role(
                name="newdef", description=None,
                storage_quota_bytes=None, max_projects=None,
                is_default=True, actor="admin",
            )
            assert ok is True
            assert new_role.is_default is True
            # El anterior ya no es default
            from app.model.entities.role import Role
            prev = db.session.get(Role, prev_default.id)
            assert prev.is_default is False

    def test_create_role_writes_audit_log(self, app, db):
        from app.model.entities.audit_log import AuditLog
        with app.app_context():
            roles_service.create_role(
                name="audited", description=None,
                storage_quota_bytes=None, max_projects=None,
                actor="admin",
            )
            log = AuditLog.query.filter_by(action="role_create", actor="admin").first()
            assert log is not None
            assert "audited" in (log.detail or "")

    def test_role_name_exists_helper(self, app, db):
        with app.app_context():
            assert roles_service.role_name_exists("alumno") is True
            assert roles_service.role_name_exists("ALUMNO") is True  # case-insensitive
            assert roles_service.role_name_exists("nonexistent") is False
            assert roles_service.role_name_exists("") is False

    # ── delete_role ───────────────────────────────────────────────────────────

    def test_delete_role_ok(self, app, db):
        """Rol nuevo sin usuarios y no-default: se puede eliminar."""
        with app.app_context():
            _, _, role = roles_service.create_role(
                name="temporal", description=None,
                storage_quota_bytes=None, max_projects=None,
                actor="admin",
            )
            rid = role.id
            ok, msg = roles_service.delete_role(rid, actor="admin")
            assert ok is True
            assert roles_service.get_role_by_id(rid) is None

    def test_delete_role_writes_audit_log(self, app, db):
        from app.model.entities.audit_log import AuditLog
        with app.app_context():
            _, _, role = roles_service.create_role(
                name="todelete", description=None,
                storage_quota_bytes=None, max_projects=None,
                actor="admin",
            )
            roles_service.delete_role(role.id, actor="admin")
            log = AuditLog.query.filter_by(action="role_delete", actor="admin").first()
            assert log is not None
            assert "todelete" in (log.detail or "")

    def test_delete_role_blocks_default(self, app, db):
        with app.app_context():
            default = roles_service.get_default_role()
            ok, msg = roles_service.delete_role(default.id, actor="admin")
            assert ok is False
            assert "por defecto" in msg.lower()
            assert roles_service.get_role_by_id(default.id) is not None

    def test_delete_role_reassigns_users_to_default(self, app, db):
        """Si el rol tiene usuarios, deben reasignarse al rol por defecto
        (NUEVA política — antes se bloqueaba)."""
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            default  = roles_service.get_default_role()
            u1 = make_user(db, "oid-del-u1", role=profesor)
            u2 = make_user(db, "oid-del-u2", role=profesor)
            u1_id, u2_id = u1.id, u2.id

            ok, msg = roles_service.delete_role(profesor.id, actor="admin")
            assert ok is True
            assert "reasignad" in msg.lower()
            assert roles_service.get_role_by_id(profesor.id) is None

            # Los usuarios ahora tienen el rol por defecto
            from app.model.entities.overleaf_user import OverleafUser
            r1 = db.session.get(OverleafUser, u1_id)
            r2 = db.session.get(OverleafUser, u2_id)
            assert r1.role_id == default.id
            assert r2.role_id == default.id

    def test_delete_role_creates_role_change_log_per_user(self, app, db):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-del-log", role=profesor)
            uid = u.id
            roles_service.delete_role(profesor.id, actor="admin")
            logs = RoleChangeLog.query.filter_by(user_id=uid).all()
            assert len(logs) >= 1
            # El log creado por el borrado refleja la reasignación
            reassign = next(
                (l for l in logs if "reasignad" in (l.reason or "").lower()),
                None,
            )
            assert reassign is not None
            assert reassign.changed_by == "admin"

    def test_delete_role_migrates_quota_when_matched(self, app, db):
        """Un usuario cuya cuota era exactamente la del rol borrado debe
        migrarse a la del rol por defecto. Si tenía override personalizado,
        se respeta."""
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            default  = roles_service.get_default_role()
            # u1: hereda la cuota del rol → debe migrar a la del default
            u1 = make_user(
                db, "oid-del-q1", role=profesor,
                max_quota_bytes=profesor.storage_quota_bytes,
            )
            # u2: override personalizado → se conserva
            u2 = make_user(
                db, "oid-del-q2", role=profesor,
                max_quota_bytes=999_999,
            )
            u1_id, u2_id = u1.id, u2.id

            roles_service.delete_role(profesor.id, actor="admin")

            from app.model.entities.overleaf_user import OverleafUser
            r1 = db.session.get(OverleafUser, u1_id)
            r2 = db.session.get(OverleafUser, u2_id)
            assert r1.max_quota_bytes == default.storage_quota_bytes
            assert r2.max_quota_bytes == 999_999  # respetado

    def test_delete_role_not_found(self, app, db):
        with app.app_context():
            ok, msg = roles_service.delete_role(99999, actor="admin")
            assert ok is False
            assert "no encontrado" in msg.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLER
# ═══════════════════════════════════════════════════════════════════════════════

class TestRolesController:

    # ── Redirect when unauthenticated ────────────────────────────────────────

    def test_list_roles_redirects_unauthenticated(self, client):
        resp = client.get("/roles/")
        assert resp.status_code in (302, 401)

    def test_role_detail_redirects_unauthenticated(self, client):
        resp = client.get("/roles/1")
        assert resp.status_code in (302, 401)

    def test_audit_log_redirects_unauthenticated(self, client):
        resp = client.get("/roles/auditoria")
        assert resp.status_code in (302, 401)

    # ── GET /roles/ ───────────────────────────────────────────────────────────

    def test_list_roles_renders_ok(self, auth_client):
        resp = auth_client.get("/roles/")
        assert resp.status_code == 200

    # ── GET /roles/<id> ───────────────────────────────────────────────────────

    def test_role_detail_ok(self, app, db, auth_client):
        with app.app_context():
            alumno = roles_service.get_role_by_name("alumno")
            rid = alumno.id
        resp = auth_client.get(f"/roles/{rid}")
        assert resp.status_code == 200

    def test_role_detail_404(self, auth_client):
        resp = auth_client.get("/roles/999999")
        assert resp.status_code == 404

    # ── GET /roles/auditoria ──────────────────────────────────────────────────

    def test_audit_log_renders_ok(self, auth_client):
        resp = auth_client.get("/roles/auditoria")
        assert resp.status_code == 200

    def test_audit_log_filter_by_action(self, auth_client):
        resp = auth_client.get("/roles/auditoria?action=assigned")
        assert resp.status_code == 200

    def test_audit_log_invalid_action_ignored(self, auth_client):
        # Invalid action should be silently ignored (set to None in controller)
        resp = auth_client.get("/roles/auditoria?action=invalid_action")
        assert resp.status_code == 200

    # ── GET /roles/<id>/buscar-usuarios ───────────────────────────────────────

    def test_search_users_for_role_returns_json(self, app, db, auth_client):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            make_user(db, "oid-ctrl-s1", email="findme@test.com", role=profesor)
            rid = profesor.id
        resp = auth_client.get(f"/roles/{rid}/buscar-usuarios?q=findme")
        assert resp.status_code == 200
        data = resp.get_json()
        assert isinstance(data, list)
        assert data[0]["email"] == "findme@test.com"

    def test_search_users_for_role_short_query_returns_empty(self, app, db, auth_client):
        with app.app_context():
            alumno = roles_service.get_role_by_name("alumno")
            rid = alumno.id
        # q < 2 chars → empty list (controller guard)
        resp = auth_client.get(f"/roles/{rid}/buscar-usuarios?q=a")
        assert resp.status_code == 200
        assert resp.get_json() == []

    def test_search_users_for_role_nonexistent_role_404(self, auth_client):
        resp = auth_client.get("/roles/999999/buscar-usuarios?q=test")
        assert resp.status_code == 404

    # ── POST /roles/<id>/editar ───────────────────────────────────────────────

    def test_update_role_config_redirects_on_success(self, app, db, auth_client):
        with app.app_context():
            alumno = roles_service.get_role_by_name("alumno")
            rid = alumno.id
        resp = auth_client.post(
            f"/roles/{rid}/editar",
            data={
                "description": "Updated description",
                "quota_value": "600",
                "quota_unit": "MB",
                "max_projects": "25",
            },
        )
        assert resp.status_code == 302
        assert f"/roles/{rid}" in resp.headers["Location"]

    def test_update_role_config_persists_changes(self, app, db, auth_client):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            rid = profesor.id
        auth_client.post(
            f"/roles/{rid}/editar",
            data={
                "description": "Nuevo texto",
                "quota_value": "10",
                "quota_unit": "GB",
                "max_projects": "100",
            },
        )
        with app.app_context():
            updated = roles_service.get_role_by_id(rid)
            assert updated.description == "Nuevo texto"
            assert updated.max_projects == 100

    def test_update_role_config_404_for_missing_role(self, auth_client):
        resp = auth_client.post(
            "/roles/999999/editar",
            data={"description": "x", "quota_value": "1", "quota_unit": "MB"},
        )
        assert resp.status_code == 404

    # ── POST /roles/<id>/gestionar-usuario ────────────────────────────────────

    def test_gestionar_usuario_assign_redirects(self, app, db, auth_client):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-gu1")
            rid, uid = profesor.id, u.id
        resp = auth_client.post(
            f"/roles/{rid}/gestionar-usuario",
            data={"user_id": str(uid), "action": "assign"},
        )
        assert resp.status_code == 302
        assert f"/roles/{rid}" in resp.headers["Location"]

    def test_gestionar_usuario_assign_persists(self, app, db, auth_client):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-gu2")
            rid, uid = profesor.id, u.id
        auth_client.post(
            f"/roles/{rid}/gestionar-usuario",
            data={"user_id": str(uid), "action": "assign"},
        )
        with app.app_context():
            from app.model.entities.overleaf_user import OverleafUser
            refreshed = db.session.get(OverleafUser, uid)
            assert refreshed.role_id == rid

    def test_gestionar_usuario_no_user_id_redirects(self, app, db, auth_client):
        with app.app_context():
            alumno = roles_service.get_role_by_name("alumno")
            rid = alumno.id
        resp = auth_client.post(
            f"/roles/{rid}/gestionar-usuario",
            data={"action": "assign"},
        )
        assert resp.status_code == 302

    def test_gestionar_usuario_ajax_returns_json(self, app, db, auth_client):
        """Con X-Requested-With el endpoint devuelve JSON (sin redirect ni
        flash), para que el modal pueda aplicar cambios en lote."""
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-ajax1")
            rid, uid = profesor.id, u.id
        resp = auth_client.post(
            f"/roles/{rid}/gestionar-usuario",
            data={"user_id": str(uid), "action": "assign"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 200
        body = resp.get_json()
        assert body["ok"] is True
        with app.app_context():
            from app.model.entities.overleaf_user import OverleafUser
            assert db.session.get(OverleafUser, uid).role_id == rid

    def test_gestionar_usuario_ajax_no_user_id_returns_400(self, app, db, auth_client):
        with app.app_context():
            rid = roles_service.get_role_by_name("alumno").id
        resp = auth_client.post(
            f"/roles/{rid}/gestionar-usuario",
            data={"action": "assign"},
            headers={"X-Requested-With": "XMLHttpRequest"},
        )
        assert resp.status_code == 400
        assert resp.get_json()["ok"] is False

    # ── POST /roles/asignar/<user_id> ─────────────────────────────────────────

    def test_asignar_redirects_to_user_detail(self, app, db, auth_client):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-asig1")
            rid, uid = profesor.id, u.id
        resp = auth_client.post(
            f"/roles/asignar/{uid}",
            data={"role_id": str(rid), "action": "assign"},
        )
        assert resp.status_code == 302
        assert f"/usuarios/{uid}" in resp.headers["Location"]

    def test_asignar_remove_action_resets_to_default(self, app, db, auth_client):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-asig2", role=profesor)
            uid = u.id
        auth_client.post(
            f"/roles/asignar/{uid}",
            data={"action": "remove"},
        )
        with app.app_context():
            from app.model.entities.overleaf_user import OverleafUser
            refreshed = db.session.get(OverleafUser, uid)
            default = roles_service.get_default_role()
            assert refreshed.role_id == default.id


    # ── New role card + modal + POST /crear ─────────────────────────────────

    def test_list_renders_new_role_card(self, auth_client):
        resp = auth_client.get("/roles/")
        assert "Nuevo rol".encode("utf-8") in resp.data
        assert b"new-role-card" in resp.data

    def test_list_renders_create_role_modal(self, auth_client):
        resp = auth_client.get("/roles/")
        assert b'id="createRoleModal"' in resp.data
        # El form apunta a la ruta correcta
        assert b'action="/roles/crear"' in resp.data

    def test_list_uses_roles_grid_not_old_hardcoded_loop(self, auth_client):
        resp = auth_client.get("/roles/")
        assert b'class="roles-grid"' in resp.data
        # El bucle viejo ya no existe
        assert b"ROLE_ORDER" not in resp.data

    def test_create_endpoint_creates_role(self, app, db, auth_client):
        resp = auth_client.post("/roles/crear", data={
            "name": "doctorado", "description": "PhD users",
            "color": "info",
            "quota_value": "10", "quota_unit": "GB",
            "max_projects": "80",
        })
        assert resp.status_code == 302
        with app.app_context():
            r = roles_service.get_role_by_name("doctorado")
            assert r is not None
            assert r.storage_quota_bytes == 10 * GB
            assert r.max_projects == 80

    def test_create_endpoint_with_unlimited(self, app, db, auth_client):
        auth_client.post("/roles/crear", data={
            "name": "ilimitado", "description": "x",
            "color": "secondary",
            "quota_unlimited": "y",
            "projects_unlimited": "y",
        })
        with app.app_context():
            r = roles_service.get_role_by_name("ilimitado")
            assert r is not None
            assert r.storage_quota_bytes is None
            assert r.max_projects is None

    def test_create_endpoint_rejects_duplicate(self, app, db, auth_client):
        auth_client.post("/roles/crear", data={
            "name": "alumno",  # ya existe del seed
            "color": "secondary",
            "quota_unlimited": "y",
            "projects_unlimited": "y",
        })
        # No se crea ningún rol nuevo con ese nombre (ya existía, sigue siendo 1)
        with app.app_context():
            n = Role.query.filter_by(name="alumno").count()
            assert n == 1

    def test_create_endpoint_rejects_missing_quota(self, app, db, auth_client):
        """Si no se marca 'ilimitado' debe darse valor numérico."""
        resp = auth_client.post("/roles/crear", data={
            "name": "incompleto",
            "color": "secondary",
            # quota_value vacío, sin marcar ilimitado
            "projects_unlimited": "y",
        })
        assert resp.status_code == 302  # redirige con flash de error
        with app.app_context():
            assert roles_service.get_role_by_name("incompleto") is None

    # ── delete role: botón + endpoint ───────────────────────────────────────

    def test_detail_renders_delete_button(self, app, db, auth_client):
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            rid = profesor.id
        resp = auth_client.get(f"/roles/{rid}")
        assert b'id="confirmDeleteRoleModal"' in resp.data
        assert b'data-bs-target="#confirmDeleteRoleModal"' in resp.data
        assert b'bi-trash' in resp.data

    def test_delete_endpoint_deletes_empty_role(self, app, db, auth_client):
        with app.app_context():
            _, _, role = roles_service.create_role(
                name="todelete_http", description=None,
                storage_quota_bytes=None, max_projects=None,
                actor="admin",
            )
            rid = role.id
        resp = auth_client.post(f"/roles/{rid}/eliminar")
        assert resp.status_code == 302
        assert "/roles/" in resp.headers["Location"]  # redirige al listado
        with app.app_context():
            assert roles_service.get_role_by_id(rid) is None

    def test_delete_endpoint_blocks_default(self, app, db, auth_client):
        with app.app_context():
            default = roles_service.get_default_role()
            rid = default.id
        resp = auth_client.post(f"/roles/{rid}/eliminar")
        assert resp.status_code == 302
        # Falla → redirige al detalle, no al listado
        assert f"/roles/{rid}" in resp.headers["Location"]
        with app.app_context():
            assert roles_service.get_role_by_id(rid) is not None

    def test_delete_endpoint_reassigns_users_and_deletes(self, app, db, auth_client):
        """Endpoint: con usuarios asignados, los reasigna al default y borra el rol."""
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            default  = roles_service.get_default_role()
            u = make_user(db, "oid-delc1", role=profesor)
            rid, uid, did = profesor.id, u.id, default.id
        resp = auth_client.post(f"/roles/{rid}/eliminar")
        assert resp.status_code == 302
        assert "/roles/" in resp.headers["Location"]
        with app.app_context():
            assert roles_service.get_role_by_id(rid) is None
            from app.model.entities.overleaf_user import OverleafUser
            refreshed = db.session.get(OverleafUser, uid)
            assert refreshed.role_id == did
