"""
tests/test_admins.py
--------------------
Tests para /administradores/ — gestión de cuentas de administrador.

Cubre:
  - Vista GET
  - Crear admin (éxito, duplicados, validación)
  - Activar / desactivar (con guard de último admin)
  - Resetear contraseña
  - AuditLog en cada mutación

Run with:
    python -m pytest tests/test_admins.py -v
"""
import pytest

from app.config.extensions import db as _db
from app.model.entities.admin_user import AdminUser
from app.model.entities.audit_log import AuditLog
from app.model.services import admins_service


def _make_admin(db, username, email=None, password="testpass123", active=True):
    a = AdminUser(
        username=username,
        email=email or f"{username}@test.com",
        is_active=active,
    )
    a.set_password(password)
    db.session.add(a)
    db.session.commit()
    return a


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — lecturas
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdminsServiceReads:

    def test_get_all_admins_includes_fixture(self, app, db, admin_user):
        with app.app_context():
            rows = admins_service.get_all_admins()
            assert len(rows) >= 1
            assert any(r["username"] == admin_user.username for r in rows)

    def test_get_all_admins_sorts_active_first(self, app, db, admin_user):
        with app.app_context():
            _make_admin(db, "inactive_one", active=False)
            _make_admin(db, "active_one",   active=True)
            rows = admins_service.get_all_admins()
            # Todos los activos antes que cualquier inactivo
            first_inactive_idx = next((i for i, r in enumerate(rows) if not r["is_active"]), None)
            if first_inactive_idx is not None:
                assert all(r["is_active"] for r in rows[:first_inactive_idx])

    def test_get_all_admins_includes_audit_count(self, app, db, admin_user):
        from app.model.services.admin import admin_service as audit_service
        with app.app_context():
            audit_service.log_action(action="login", actor=admin_user.username)
            audit_service.log_action(action="login", actor=admin_user.username)
            rows = admins_service.get_all_admins()
            mine = next(r for r in rows if r["username"] == admin_user.username)
            assert mine["audit_count"] >= 2

    def test_get_stats(self, app, db, admin_user):
        with app.app_context():
            _make_admin(db, "active_a",   active=True)
            _make_admin(db, "inactive_a", active=False)
            stats = admins_service.get_stats()
            assert stats["total"] == 3       # fixture + 2
            assert stats["active"] == 2      # fixture + active_a
            assert stats["inactive"] == 1

    def test_count_active(self, app, db, admin_user):
        with app.app_context():
            assert admins_service.count_active_admins() == 1
            _make_admin(db, "other", active=True)
            assert admins_service.count_active_admins() == 2

    def test_get_recent_admin_activity_only_admin_actors(self, app, db, admin_user):
        """El aside sólo debe mostrar logs cuyo actor es un AdminUser conocido."""
        from app.model.services.admin import admin_service as audit_service
        with app.app_context():
            audit_service.log_action(action="login", actor=admin_user.username)
            audit_service.log_action(action="sync_ok", actor="system")  # NO es admin
            audit_service.log_action(action="login", actor="ghost")     # actor inexistente
            rows = admins_service.get_recent_admin_activity()
            actors = {r["actor"] for r in rows}
            assert admin_user.username in actors
            assert "system" not in actors
            assert "ghost" not in actors

    def test_get_recent_admin_activity_orders_descending(self, app, db, admin_user):
        from app.model.services.admin import admin_service as audit_service
        with app.app_context():
            for i in range(5):
                audit_service.log_action(action="login", actor=admin_user.username,
                                         detail=f"event {i}")
            rows = admins_service.get_recent_admin_activity(limit=10)
            # Ordenados desc → el primero es el último loggeado
            assert rows[0]["created_at"] >= rows[-1]["created_at"]

    def test_get_recent_admin_activity_translates_action(self, app, db, admin_user):
        from app.model.services.admin import admin_service as audit_service
        with app.app_context():
            audit_service.log_action(action="password_change", actor=admin_user.username)
            rows = admins_service.get_recent_admin_activity()
            assert rows[0]["action_label"] == "Cambio de contraseña"

    def test_includes_last_password_change_at(self, app, db, admin_user):
        from app.model.services.admin import admin_service as audit_service
        with app.app_context():
            audit_service.log_action(action="password_change", actor=admin_user.username)
            rows = admins_service.get_all_admins()
            mine = next(r for r in rows if r["username"] == admin_user.username)
            assert mine["last_password_change_at"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — create_admin
# ═══════════════════════════════════════════════════════════════════════════════

class TestCreateAdmin:

    def test_create_ok(self, app, db, admin_user):
        with app.app_context():
            ok, msg = admins_service.create_admin(
                username="newadmin", email="new@test.com",
                password="abcdefgh", confirm_password="abcdefgh",
                actor=admin_user.username,
            )
            assert ok is True
            found = AdminUser.query.filter_by(username="newadmin").first()
            assert found is not None
            assert found.check_password("abcdefgh") is True
            assert found.is_active is True

    def test_create_inactive(self, app, db, admin_user):
        with app.app_context():
            admins_service.create_admin(
                username="dormant", email="d@test.com",
                password="abcdefgh", confirm_password="abcdefgh",
                is_active=False,
                actor=admin_user.username,
            )
            found = AdminUser.query.filter_by(username="dormant").first()
            assert found.is_active is False

    def test_create_duplicate_username(self, app, db, admin_user):
        with app.app_context():
            ok, msg = admins_service.create_admin(
                username=admin_user.username, email="other@test.com",
                password="abcdefgh", confirm_password="abcdefgh",
                actor=admin_user.username,
            )
            assert ok is False
            assert "usuario" in msg.lower() and ("existe" in msg.lower() or "duplicad" in msg.lower())

    def test_create_duplicate_email(self, app, db, admin_user):
        with app.app_context():
            ok, msg = admins_service.create_admin(
                username="newadmin2", email=admin_user.email,
                password="abcdefgh", confirm_password="abcdefgh",
                actor=admin_user.username,
            )
            assert ok is False
            assert "email" in msg.lower()

    def test_create_password_too_short(self, app, db, admin_user):
        with app.app_context():
            ok, msg = admins_service.create_admin(
                username="newadmin3", email="3@test.com",
                password="abc", confirm_password="abc",
                actor=admin_user.username,
            )
            assert ok is False
            assert "8" in msg

    def test_create_password_mismatch(self, app, db, admin_user):
        with app.app_context():
            ok, msg = admins_service.create_admin(
                username="newadmin4", email="4@test.com",
                password="abcdefgh", confirm_password="OTHEROTHER",
                actor=admin_user.username,
            )
            assert ok is False

    def test_create_invalid_email(self, app, db, admin_user):
        with app.app_context():
            ok, msg = admins_service.create_admin(
                username="badmail", email="notanemail",
                password="abcdefgh", confirm_password="abcdefgh",
                actor=admin_user.username,
            )
            assert ok is False

    def test_create_writes_audit_log(self, app, db, admin_user):
        with app.app_context():
            admins_service.create_admin(
                username="audited", email="audit@test.com",
                password="abcdefgh", confirm_password="abcdefgh",
                actor=admin_user.username,
            )
            log = (
                AuditLog.query
                .filter_by(action="admin_create", actor=admin_user.username)
                .first()
            )
            assert log is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — set_admin_active (con guard)
# ═══════════════════════════════════════════════════════════════════════════════

class TestSetAdminActive:

    def test_deactivate_other_ok(self, app, db, admin_user):
        with app.app_context():
            other = _make_admin(db, "other", active=True)
            ok, msg = admins_service.set_admin_active(
                other.id, False,
                actor=admin_user.username, actor_id=admin_user.id,
            )
            assert ok is True
            refreshed = _db.session.get(AdminUser, other.id)
            assert refreshed.is_active is False

    def test_activate_ok(self, app, db, admin_user):
        with app.app_context():
            other = _make_admin(db, "dormant2", active=False)
            ok, msg = admins_service.set_admin_active(
                other.id, True,
                actor=admin_user.username, actor_id=admin_user.id,
            )
            assert ok is True

    def test_cannot_deactivate_last_active(self, app, db, admin_user):
        """Solo queda el admin del fixture activo: no se puede desactivar (cae en el guard
        de "propia cuenta" antes del "último activo", pero el resultado es el mismo)."""
        with app.app_context():
            ok, _ = admins_service.set_admin_active(
                admin_user.id, False,
                actor=admin_user.username, actor_id=admin_user.id,
            )
            assert ok is False
            refreshed = _db.session.get(AdminUser, admin_user.id)
            assert refreshed.is_active is True

    def test_cannot_deactivate_self_even_with_others_active(self, app, db, admin_user):
        """REGLA NUEVA: nadie se desactiva a sí mismo, ni siquiera si hay más admins activos."""
        with app.app_context():
            _make_admin(db, "buddy", active=True)
            ok, msg = admins_service.set_admin_active(
                admin_user.id, False,
                actor=admin_user.username, actor_id=admin_user.id,
            )
            assert ok is False
            assert "propia" in msg.lower()
            refreshed = _db.session.get(AdminUser, admin_user.id)
            assert refreshed.is_active is True

    def test_cannot_deactivate_last_active_other(self, app, db, admin_user):
        """Si soy 'sysop' y el único activo es 'otro', no puedo desactivar a 'otro'."""
        with app.app_context():
            other = _make_admin(db, "lonely", active=True)
            # Desactivamos al del fixture para que sólo quede 'lonely' activo
            _db.session.get(AdminUser, admin_user.id).is_active = False
            _db.session.commit()
            ok, msg = admins_service.set_admin_active(
                other.id, False,
                actor=admin_user.username, actor_id=admin_user.id,
            )
            assert ok is False
            assert "último" in msg.lower() or "ultimo" in msg.lower()

    def test_same_state_noop(self, app, db, admin_user):
        with app.app_context():
            ok, msg = admins_service.set_admin_active(
                admin_user.id, True,
                actor=admin_user.username, actor_id=admin_user.id,
            )
            assert ok is False
            assert "ya" in msg.lower()

    def test_not_found(self, app, db, admin_user):
        with app.app_context():
            ok, _ = admins_service.set_admin_active(
                99999, False,
                actor=admin_user.username, actor_id=admin_user.id,
            )
            assert ok is False

    def test_writes_audit_log_on_disable(self, app, db, admin_user):
        with app.app_context():
            other = _make_admin(db, "other2", active=True)
            admins_service.set_admin_active(
                other.id, False,
                actor=admin_user.username, actor_id=admin_user.id,
            )
            log = AuditLog.query.filter_by(action="admin_disable").first()
            assert log is not None

    def test_writes_audit_log_on_enable(self, app, db, admin_user):
        with app.app_context():
            other = _make_admin(db, "off", active=False)
            admins_service.set_admin_active(
                other.id, True,
                actor=admin_user.username, actor_id=admin_user.id,
            )
            log = AuditLog.query.filter_by(action="admin_enable").first()
            assert log is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — reset_admin_password
# ═══════════════════════════════════════════════════════════════════════════════

class TestResetAdminPassword:

    def test_reset_ok(self, app, db, admin_user):
        with app.app_context():
            other = _make_admin(db, "rstme", password="oldpass123")
            ok, _ = admins_service.reset_admin_password(
                other.id, "brandnew99", "brandnew99",
                actor=admin_user.username,
            )
            assert ok is True
            refreshed = _db.session.get(AdminUser, other.id)
            assert refreshed.check_password("brandnew99") is True

    def test_reset_too_short(self, app, db, admin_user):
        with app.app_context():
            other = _make_admin(db, "rstme2")
            ok, msg = admins_service.reset_admin_password(
                other.id, "abc", "abc",
                actor=admin_user.username,
            )
            assert ok is False
            assert "8" in msg

    def test_reset_mismatch(self, app, db, admin_user):
        with app.app_context():
            other = _make_admin(db, "rstme3")
            ok, _ = admins_service.reset_admin_password(
                other.id, "abcdefgh", "DIFFERENT",
                actor=admin_user.username,
            )
            assert ok is False

    def test_reset_not_found(self, app, db, admin_user):
        with app.app_context():
            ok, _ = admins_service.reset_admin_password(
                99999, "abcdefgh", "abcdefgh",
                actor=admin_user.username,
            )
            assert ok is False

    def test_reset_writes_audit_log(self, app, db, admin_user):
        with app.app_context():
            other = _make_admin(db, "rstme4")
            admins_service.reset_admin_password(
                other.id, "abcdefgh", "abcdefgh",
                actor=admin_user.username,
            )
            log = AuditLog.query.filter_by(
                action="admin_password_reset", actor=admin_user.username
            ).first()
            assert log is not None


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLER — /administradores/
# ═══════════════════════════════════════════════════════════════════════════════

class TestAdminsController:

    def test_index_redirects_unauthenticated(self, client):
        resp = client.get("/administradores/")
        assert resp.status_code in (302, 401)

    def test_index_renders_ok(self, auth_client):
        resp = auth_client.get("/administradores/")
        assert resp.status_code == 200

    def test_index_shows_current_admin(self, auth_client, admin_user):
        resp = auth_client.get("/administradores/")
        assert admin_user.username.encode() in resp.data

    def test_index_marks_current_user_as_self(self, auth_client):
        resp = auth_client.get("/administradores/")
        assert b"admin-row-self" in resp.data
        # El badge "Tú" sólo se renderiza para la card propia
        assert "Tú".encode("utf-8") in resp.data

    def test_index_uses_cards_not_table(self, auth_client):
        """Confirmamos que la pantalla usa cards (sin <table> en el listado)."""
        resp = auth_client.get("/administradores/")
        assert b'id="admins-list"' in resp.data
        assert b'admin-card' in resp.data
        assert b'<table' not in resp.data  # Ya no hay tabla en el listado

    def test_index_does_not_show_old_header_block(self, auth_client):
        """El bloque "Administradores / Gestiona las cuentas internas…" debe haberse
        eliminado del contenido (sólo queda en la topbar)."""
        resp = auth_client.get("/administradores/")
        # El subtítulo del bloque viejo
        assert "Gestiona las cuentas internas".encode("utf-8") not in resp.data

    def test_self_deactivate_button_disabled(self, auth_client, admin_user):
        """En la card propia, el botón Desactivar debe estar deshabilitado."""
        resp = auth_client.get("/administradores/")
        # El tooltip aparece sólo en la card propia
        assert "No puedes desactivar tu propia cuenta".encode("utf-8") in resp.data

    def test_search_input_present(self, auth_client):
        resp = auth_client.get("/administradores/")
        assert b'id="admin-search"' in resp.data

    def test_search_and_create_button_in_same_group(self, auth_client):
        """El buscador y el botón "Nuevo" están unidos en el mismo input-group."""
        resp = auth_client.get("/administradores/")
        assert b"search-create-group" in resp.data

    def test_index_shows_audit_aside(self, app, db, auth_client, admin_user):
        """El aside derecho con la actividad de los admins debe estar presente
        y mostrar la acción de algún admin (no de "system")."""
        from app.model.services.admin import admin_service as audit_service
        with app.app_context():
            audit_service.log_action(action="login", actor=admin_user.username)
            audit_service.log_action(action="sync_ok", actor="system")
        resp = auth_client.get("/administradores/")
        assert b"admins-aside" in resp.data
        assert "Actividad de administradores".encode("utf-8") in resp.data
        # El log del admin aparece, el de system no
        assert admin_user.username.encode() in resp.data

    def test_create_endpoint_persists(self, app, db, auth_client):
        resp = auth_client.post("/administradores/nuevo", data={
            "username": "fromhttp", "email": "http@test.com",
            "password": "abcdefgh", "confirm_password": "abcdefgh",
            "is_active": "y",
        })
        assert resp.status_code == 302
        with app.app_context():
            assert AdminUser.query.filter_by(username="fromhttp").first() is not None

    def test_create_endpoint_validates(self, auth_client):
        resp = auth_client.post("/administradores/nuevo", data={})
        assert resp.status_code == 302  # form inválido → redirige con flash

    def test_deactivate_endpoint_with_other_admin(self, app, db, auth_client, admin_user):
        with app.app_context():
            other = _make_admin(db, "deact_me", active=True)
            oid = other.id
        resp = auth_client.post(f"/administradores/{oid}/desactivar")
        assert resp.status_code == 302
        with app.app_context():
            refreshed = _db.session.get(AdminUser, oid)
            assert refreshed.is_active is False

    def test_deactivate_endpoint_blocks_last_admin(self, app, db, auth_client, admin_user):
        """Si soy el último admin activo, el endpoint no debe desactivarme."""
        resp = auth_client.post(f"/administradores/{admin_user.id}/desactivar")
        assert resp.status_code == 302
        with app.app_context():
            refreshed = _db.session.get(AdminUser, admin_user.id)
            assert refreshed.is_active is True

    def test_deactivate_endpoint_blocks_self_even_with_others(self, app, db, auth_client, admin_user):
        """El endpoint debe bloquear que el usuario actual se desactive a sí mismo,
        haya o no haya otros admins activos."""
        with app.app_context():
            _make_admin(db, "extra", active=True)
        resp = auth_client.post(f"/administradores/{admin_user.id}/desactivar")
        assert resp.status_code == 302
        with app.app_context():
            refreshed = _db.session.get(AdminUser, admin_user.id)
            assert refreshed.is_active is True

    def test_reset_password_endpoint(self, app, db, auth_client):
        with app.app_context():
            other = _make_admin(db, "res_me", password="oldpass99")
            oid = other.id
        resp = auth_client.post(f"/administradores/{oid}/reset-password", data={
            "new_password": "freshpass1", "confirm_password": "freshpass1",
        })
        assert resp.status_code == 302
        with app.app_context():
            refreshed = _db.session.get(AdminUser, oid)
            assert refreshed.check_password("freshpass1") is True
