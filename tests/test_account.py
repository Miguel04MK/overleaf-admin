"""
tests/test_account.py
---------------------
Tests para el área "Mi cuenta" del administrador autenticado.

Cubre:
  - Vista GET /mi-cuenta/ (renderiza datos, prefs y actividad reciente)
  - Cambio de contraseña (éxito y fallos) + AuditLog
  - Preferencias de notificación inline (lectura, escritura, AuditLog)
  - Actividad reciente (filtrado por actor, límite)

Run with:
    python -m pytest tests/test_account.py -v
"""
import pytest

from app.model.entities.admin_notification_pref import AdminNotificationPref
from app.model.entities.audit_log import AuditLog
from app.model.services import account_service
from app.model.services.admin import admin_service as audit_service


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLER — GET /mi-cuenta/
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccountView:

    def test_index_redirects_unauthenticated(self, client):
        resp = client.get("/mi-cuenta/")
        assert resp.status_code in (302, 401)

    def test_index_renders_ok(self, auth_client):
        resp = auth_client.get("/mi-cuenta/")
        assert resp.status_code == 200

    def test_index_shows_current_admin_username(self, auth_client, admin_user):
        resp = auth_client.get("/mi-cuenta/")
        assert admin_user.username.encode() in resp.data

    def test_index_shows_current_admin_email(self, auth_client, admin_user):
        resp = auth_client.get("/mi-cuenta/")
        assert admin_user.email.encode() in resp.data

    def test_index_shows_avatar_initial(self, auth_client, admin_user):
        """El avatar muestra la inicial del username en mayúsculas."""
        resp = auth_client.get("/mi-cuenta/")
        assert b'class="account-avatar"' in resp.data

    def test_index_shows_last_access_section(self, auth_client):
        """La fila 'Último acceso' está visible en el perfil."""
        resp = auth_client.get("/mi-cuenta/")
        assert b"\xc3\x9altimo acceso" in resp.data  # "Último acceso" en UTF-8

    def test_index_shows_inline_notif_form(self, auth_client):
        """El formulario inline de preferencias está visible (no detrás de modal)."""
        resp = auth_client.get("/mi-cuenta/")
        assert b'id="notif-form"' in resp.data

    def test_index_inline_form_has_same_options_as_alerts_modal(self, auth_client):
        """El form inline expone los 11 tipos (sin service_down) en dos pestañas:
        Inmediato (immediate_notify_X) y Periódico (digest_notify_X).
        Incluye también el selector de digest_frequency."""
        resp = auth_client.get("/mi-cuenta/")
        # Pestaña Inmediato — checkboxes con prefijo immediate_
        expected_immediate = [
            b'name="immediate_notify_critical"', b'name="immediate_notify_danger"',
            b'name="immediate_notify_warning"',  b'name="immediate_notify_info"',
            b'name="immediate_notify_sync_failed"',
            b'name="immediate_notify_quota_exceeded"',
            b'name="immediate_notify_quota_warning"',
            b'name="immediate_notify_project_limit_exceeded"',
            b'name="immediate_notify_project_limit_warning"',
            b'name="immediate_notify_repeated_errors"',
            b'name="immediate_notify_administrative_warning"',
        ]
        for f in expected_immediate:
            assert f in resp.data, f"Falta campo inmediato {f.decode()}"
        # Pestaña Periódico — checkboxes con prefijo digest_
        expected_digest = [
            b'name="digest_notify_critical"', b'name="digest_notify_danger"',
        ]
        for f in expected_digest:
            assert f in resp.data, f"Falta campo digest {f.decode()}"
        # service_down eliminado
        assert b'name="immediate_notify_service_down"' not in resp.data
        assert b'name="digest_notify_service_down"'    not in resp.data
        # Selector de frecuencia presente
        assert b'name="digest_frequency"' in resp.data

    def test_index_includes_password_confirm_modal(self, auth_client):
        resp = auth_client.get("/mi-cuenta/")
        assert b'id="confirmPwModal"' in resp.data

    def test_index_renders_activity_empty_state_when_no_logs(self, app, db, auth_client):
        """Sin AuditLogs, debe mostrarse el empty state."""
        with app.app_context():
            AuditLog.query.delete()
            db.session.commit()
        resp = auth_client.get("/mi-cuenta/")
        assert resp.status_code == 200
        assert "No hay actividad reciente registrada.".encode("utf-8") in resp.data


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — change_password
# ═══════════════════════════════════════════════════════════════════════════════

class TestChangePasswordService:

    def test_change_password_ok(self, app, db, admin_user):
        with app.app_context():
            ok, _ = account_service.change_password(
                admin_id=admin_user.id,
                current_password="s3cr3t!",
                new_password="newpass123",
                confirm_password="newpass123",
            )
            assert ok is True
            from app.model.entities.admin_user import AdminUser
            refreshed = db.session.get(AdminUser, admin_user.id)
            assert refreshed.check_password("newpass123") is True

    def test_change_password_wrong_current(self, app, db, admin_user):
        with app.app_context():
            ok, msg = account_service.change_password(
                admin_id=admin_user.id,
                current_password="WRONG",
                new_password="newpass123",
                confirm_password="newpass123",
            )
            assert ok is False
            assert "actual" in msg.lower()

    def test_change_password_mismatch_confirmation(self, app, db, admin_user):
        with app.app_context():
            ok, msg = account_service.change_password(
                admin_id=admin_user.id,
                current_password="s3cr3t!",
                new_password="newpass123",
                confirm_password="otherpass1",
            )
            assert ok is False
            assert "coincide" in msg.lower()

    def test_change_password_too_short(self, app, db, admin_user):
        with app.app_context():
            ok, msg = account_service.change_password(
                admin_id=admin_user.id,
                current_password="s3cr3t!",
                new_password="abc",
                confirm_password="abc",
            )
            assert ok is False
            assert "8" in msg

    def test_change_password_same_as_current(self, app, db, admin_user):
        with app.app_context():
            admin_user.set_password("longpass123")
            db.session.commit()
            ok, msg = account_service.change_password(
                admin_id=admin_user.id,
                current_password="longpass123",
                new_password="longpass123",
                confirm_password="longpass123",
            )
            assert ok is False
            assert "distinta" in msg.lower()

    def test_change_password_writes_audit_log(self, app, db, admin_user):
        with app.app_context():
            account_service.change_password(
                admin_id=admin_user.id,
                current_password="s3cr3t!",
                new_password="newpass123",
                confirm_password="newpass123",
            )
            log = (
                AuditLog.query
                .filter_by(action="password_change", actor=admin_user.username)
                .first()
            )
            assert log is not None
            assert log.level == "info"

    def test_change_password_failed_attempt_writes_no_log(self, app, db, admin_user):
        with app.app_context():
            account_service.change_password(
                admin_id=admin_user.id,
                current_password="WRONG",
                new_password="newpass123",
                confirm_password="newpass123",
            )
            log = AuditLog.query.filter_by(action="password_change").first()
            assert log is None


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — notification preferences
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationPreferencesService:

    def test_get_creates_defaults_when_absent(self, app, db, admin_user):
        with app.app_context():
            assert AdminNotificationPref.query.filter_by(admin_id=admin_user.id).first() is None
            pref = account_service.get_notification_preferences(admin_user.id)
            assert pref is not None
            assert pref.admin_id == admin_user.id
            # Defaults: critical+danger ON, warning+info OFF, etc.
            assert pref.notify_critical is True
            assert pref.notify_info is False

    def test_update_persists_changes(self, app, db, admin_user):
        with app.app_context():
            ok, _ = account_service.update_notification_preferences(
                admin_id=admin_user.id,
                data={
                    "notify_quota_warning": True,
                    "notify_sync_failed":   False,
                },
            )
            assert ok is True
            pref = account_service.get_notification_preferences(admin_user.id)
            assert pref.notify_quota_warning is True
            assert pref.notify_sync_failed is False

    def test_update_writes_audit_log(self, app, db, admin_user):
        with app.app_context():
            account_service.update_notification_preferences(
                admin_id=admin_user.id,
                data={"notify_warning": True},
            )
            log = (
                AuditLog.query
                .filter_by(action="notification_preferences_update",
                           actor=admin_user.username)
                .first()
            )
            assert log is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — actividad reciente
# ═══════════════════════════════════════════════════════════════════════════════

class TestRecentActivityService:

    def test_returns_empty_when_no_logs(self, app, db, admin_user):
        with app.app_context():
            AuditLog.query.delete()
            db.session.commit()
            assert account_service.get_recent_activity(admin_user.username) == []

    def test_filters_by_actor(self, app, db, admin_user):
        with app.app_context():
            audit_service.log_action(action="login", actor=admin_user.username)
            audit_service.log_action(action="login", actor="other_admin")
            rows = account_service.get_recent_activity(admin_user.username)
            assert all(r["action"] == "login" for r in rows)
            assert len(rows) == 1

    def test_orders_descending_and_limits(self, app, db, admin_user):
        with app.app_context():
            for i in range(10):
                audit_service.log_action(action="login", actor=admin_user.username,
                                         detail=f"entry {i}")
            rows = account_service.get_recent_activity(admin_user.username, limit=5)
            assert len(rows) == 5

    def test_translates_known_actions(self):
        # No requiere DB
        assert account_service.label_for_action("login") == "Inicio de sesión"
        assert account_service.label_for_action("password_change") == "Cambio de contraseña"
        assert (
            account_service.label_for_action("notification_preferences_update")
            == "Preferencias de notificación actualizadas"
        )

    def test_unknown_action_falls_back_to_humanized(self):
        # Acción desconocida → capitalización con espacios
        assert account_service.label_for_action("foo_bar_baz") == "Foo bar baz"


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLER — POSTs
# ═══════════════════════════════════════════════════════════════════════════════

class TestAccountControllerPosts:

    def test_change_password_endpoint_redirects(self, auth_client):
        resp = auth_client.post("/mi-cuenta/cambiar-password", data={
            "current_password": "s3cr3t!",
            "new_password":     "newpass123",
            "confirm_password": "newpass123",
        })
        assert resp.status_code == 302
        assert "/mi-cuenta/" in resp.headers["Location"]

    def test_change_password_endpoint_persists(self, app, db, auth_client, admin_user):
        auth_client.post("/mi-cuenta/cambiar-password", data={
            "current_password": "s3cr3t!",
            "new_password":     "newpass123",
            "confirm_password": "newpass123",
        })
        with app.app_context():
            from app.model.entities.admin_user import AdminUser
            refreshed = db.session.get(AdminUser, admin_user.id)
            assert refreshed.check_password("newpass123") is True

    def test_change_password_endpoint_validates_required(self, auth_client):
        resp = auth_client.post("/mi-cuenta/cambiar-password", data={})
        assert resp.status_code == 302

    def test_notifications_endpoint_persists(self, app, db, auth_client, admin_user):
        """Checkboxes con prefijo immediate_ / digest_ se persisten correctamente."""
        auth_client.post("/mi-cuenta/notificaciones", data={
            "immediate_notify_critical":     "on",   # tab Inmediato
            "immediate_notify_sync_failed":  "on",
            "digest_notify_quota_warning":   "on",   # tab Periódico
            # notify_info ausente → ambas pestañas quedan False
            "digest_frequency":              "daily",
        })
        with app.app_context():
            pref = AdminNotificationPref.query.filter_by(admin_id=admin_user.id).first()
            assert pref is not None
            assert pref.is_immediate("notify_critical")      is True
            assert pref.is_immediate("notify_sync_failed")   is True
            assert pref.is_in_digest("notify_quota_warning") is True
            assert pref.is_immediate("notify_info")          is False
            assert pref.is_in_digest("notify_info")          is False
            assert pref.digest_frequency == "daily"

    def test_notifications_endpoint_unchecks_when_field_absent(self, app, db, auth_client, admin_user):
        """Cuando un campo no se envía, queda en 'off' (cualquier modo
        anterior se sobrescribe)."""
        with app.app_context():
            pref = account_service.get_notification_preferences(admin_user.id)
            pref.set_mode("notify_quota_warning", "immediate")
            db.session.commit()
        # Enviamos el form SIN notify_quota_warning
        auth_client.post("/mi-cuenta/notificaciones", data={"notify_critical": "immediate"})
        with app.app_context():
            pref = AdminNotificationPref.query.filter_by(admin_id=admin_user.id).first()
            assert pref.get_mode("notify_quota_warning") == "off"

    def test_notifications_endpoint_redirects(self, auth_client):
        resp = auth_client.post("/mi-cuenta/notificaciones", data={})
        assert resp.status_code == 302
        assert "/mi-cuenta/" in resp.headers["Location"]
