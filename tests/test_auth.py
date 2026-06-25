"""
tests/test_auth.py
------------------
Tests para el módulo de autenticación tras el rediseño:
  - Login por username (compatibilidad)
  - Login por email (nuevo)
  - Email case-insensitive
  - Rechaza inactivos
  - Rechaza password incorrecta
  - Rechaza usuario inexistente
  - Trim de espacios
  - Pantalla de login renderiza el nuevo split layout

Run with:
    python -m pytest tests/test_auth.py -v
"""
import pytest

from app.model.entities.admin_user import AdminUser
from app.model.entities.audit_log import AuditLog
from app.model.services import auth_service


def _make_admin(db, username="alice", email="alice@test.com",
                password="passw0rd!", active=True):
    a = AdminUser(username=username, email=email.lower(), is_active=active)
    a.set_password(password)
    db.session.add(a)
    db.session.commit()
    return a


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — authenticate()
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuthenticate:

    def test_login_with_username(self, app, db):
        with app.app_context():
            _make_admin(db, username="alice", email="alice@test.com",
                        password="passw0rd!")
            user = auth_service.authenticate("alice", "passw0rd!")
            assert user is not None
            assert user.username == "alice"

    def test_login_with_email(self, app, db):
        with app.app_context():
            _make_admin(db, username="alice", email="alice@test.com",
                        password="passw0rd!")
            user = auth_service.authenticate("alice@test.com", "passw0rd!")
            assert user is not None
            assert user.username == "alice"

    def test_email_case_insensitive(self, app, db):
        with app.app_context():
            _make_admin(db, email="alice@test.com")
            # Probamos con diferentes capitalizaciones
            assert auth_service.authenticate("ALICE@test.com", "passw0rd!") is not None
            assert auth_service.authenticate("Alice@Test.com", "passw0rd!") is not None

    def test_username_is_case_sensitive(self, app, db):
        """El username NO se trata como case-insensitive (solo el email).
        Si queremos cambiarlo, se hace explícitamente."""
        with app.app_context():
            _make_admin(db, username="alice")
            assert auth_service.authenticate("alice", "passw0rd!") is not None
            # Caps en username no encajan
            assert auth_service.authenticate("ALICE", "passw0rd!") is None

    def test_strips_whitespace(self, app, db):
        with app.app_context():
            _make_admin(db, username="alice", email="alice@test.com")
            assert auth_service.authenticate("  alice  ", "passw0rd!") is not None
            assert auth_service.authenticate(" alice@test.com ", "passw0rd!") is not None

    def test_wrong_password_rejected(self, app, db):
        with app.app_context():
            _make_admin(db, username="alice", password="correct!")
            assert auth_service.authenticate("alice", "wrong") is None

    def test_unknown_user_rejected(self, app, db):
        with app.app_context():
            assert auth_service.authenticate("ghost", "anything") is None
            assert auth_service.authenticate("ghost@nope.com", "anything") is None

    def test_inactive_user_rejected(self, app, db):
        with app.app_context():
            _make_admin(db, username="off", active=False)
            assert auth_service.authenticate("off", "passw0rd!") is None

    def test_empty_inputs_rejected(self, app, db):
        with app.app_context():
            _make_admin(db, username="alice")
            assert auth_service.authenticate("", "passw0rd!") is None
            assert auth_service.authenticate("alice", "") is None
            assert auth_service.authenticate(None, "passw0rd!") is None
            assert auth_service.authenticate("   ", "passw0rd!") is None


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLER — POST /auth/login con username o email
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoginEndpoint:

    def test_login_renders_split_layout(self, client):
        """La nueva pantalla tiene los dos paneles."""
        r = client.get("/auth/login")
        assert r.status_code == 200
        assert b"login-split" in r.data
        assert b"login-left"  in r.data
        assert b"login-right" in r.data
        # Label nuevo: "Usuario o email"
        assert "Usuario o email".encode("utf-8") in r.data

    def test_login_post_with_username(self, app, db, client):
        with app.app_context():
            _make_admin(db, username="alice", email="alice@test.com",
                        password="passw0rd!")
        r = client.post("/auth/login", data={
            "username": "alice", "password": "passw0rd!",
        }, follow_redirects=False)
        # Login OK → redirige al dashboard
        assert r.status_code == 302
        assert "/dashboard" in r.headers["Location"] or r.headers["Location"].endswith("/")

    def test_login_post_with_email(self, app, db, client):
        with app.app_context():
            _make_admin(db, username="alice", email="alice@test.com",
                        password="passw0rd!")
        r = client.post("/auth/login", data={
            "username": "alice@test.com", "password": "passw0rd!",
        }, follow_redirects=False)
        assert r.status_code == 302

    def test_login_post_with_email_uppercase(self, app, db, client):
        with app.app_context():
            _make_admin(db, username="alice", email="alice@test.com",
                        password="passw0rd!")
        r = client.post("/auth/login", data={
            "username": "ALICE@TEST.COM", "password": "passw0rd!",
        }, follow_redirects=False)
        assert r.status_code == 302

    def test_login_post_wrong_password(self, app, db, client):
        with app.app_context():
            _make_admin(db, username="alice", password="correct!")
        r = client.post("/auth/login", data={
            "username": "alice", "password": "wrong",
        }, follow_redirects=True)
        # Se queda en /auth/login con un flash genérico
        assert r.status_code == 200
        assert "Credenciales incorrectas".encode("utf-8") in r.data

    def test_login_post_inactive_user(self, app, db, client):
        with app.app_context():
            _make_admin(db, username="off", active=False)
        r = client.post("/auth/login", data={
            "username": "off", "password": "passw0rd!",
        }, follow_redirects=True)
        assert "Credenciales incorrectas".encode("utf-8") in r.data

    def test_login_writes_audit_log(self, app, db, client):
        with app.app_context():
            _make_admin(db, username="alice")
        client.post("/auth/login", data={
            "username": "alice", "password": "passw0rd!",
        }, follow_redirects=False)
        with app.app_context():
            log = AuditLog.query.filter_by(action="login", actor="alice").first()
            assert log is not None

    def test_login_updates_last_login_at(self, app, db, client):
        with app.app_context():
            a = _make_admin(db, username="alice")
            assert a.last_login_at is None
            aid = a.id
        client.post("/auth/login", data={
            "username": "alice", "password": "passw0rd!",
        }, follow_redirects=False)
        with app.app_context():
            from app.config.extensions import db as _db
            refreshed = _db.session.get(AdminUser, aid)
            assert refreshed.last_login_at is not None
