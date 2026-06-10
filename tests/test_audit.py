"""
tests/test_audit.py
-------------------
Tests para la pantalla /auditoria/ — filtros, categorías y resumen.

Run with:
    python -m pytest tests/test_audit.py -v
"""
import pytest
from datetime import datetime, timedelta, timezone

from app.config.extensions import db as _db
from app.model.entities.audit_log import AuditLog
from app.model.services.admin import admin_service


def _seed(db, *, action="login", actor="alice", level="info", detail=None, when=None):
    """Helper: crea un AuditLog con timestamp opcional."""
    log = AuditLog(action=action, actor=actor, level=level, detail=detail)
    if when:
        log.created_at = when
    db.session.add(log)
    db.session.commit()
    return log


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — categorización
# ═══════════════════════════════════════════════════════════════════════════════

class TestCategorization:

    def test_known_categories_exist(self):
        keys = set(admin_service.CATEGORIES.keys())
        assert keys == {"auth", "admin", "quota", "sync", "role"}

    def test_category_for_login(self):
        assert admin_service.category_for_action("login")  == "auth"
        assert admin_service.category_for_action("logout") == "auth"

    def test_category_for_role_changes(self):
        assert admin_service.category_for_action("role_assigned") == "role"
        assert admin_service.category_for_action("role_changed")  == "role"
        assert admin_service.category_for_action("role_removed")  == "role"

    def test_category_for_quota_change(self):
        assert admin_service.category_for_action("quota_change") == "quota"

    def test_category_for_sync(self):
        assert admin_service.category_for_action("sync_ok")    == "sync"
        assert admin_service.category_for_action("sync_error") == "sync"

    def test_category_for_unknown(self):
        assert admin_service.category_for_action("nonexistent_xyz") is None

    def test_label_for_known(self):
        assert admin_service.label_for_action("login") == "Inicio de sesión"
        assert admin_service.label_for_action("password_change") == "Cambio de contraseña"

    def test_label_for_unknown_humanizes(self):
        assert admin_service.label_for_action("foo_bar") == "Foo bar"


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — filtros y resumen
# ═══════════════════════════════════════════════════════════════════════════════

class TestFilteredLogs:

    def test_no_filters_returns_all(self, app, db):
        with app.app_context():
            _seed(db, action="login",   actor="a")
            _seed(db, action="sync_ok", actor="system")
            p = admin_service.get_filtered_logs()
            assert p.total == 2

    def test_filter_by_category(self, app, db):
        with app.app_context():
            _seed(db, action="login",        actor="a")  # auth
            _seed(db, action="sync_ok",      actor="system")  # sync
            _seed(db, action="role_changed", actor="a")  # role
            p = admin_service.get_filtered_logs(category="sync")
            assert p.total == 1
            assert p.items[0].action == "sync_ok"

    def test_filter_by_level(self, app, db):
        with app.app_context():
            _seed(db, action="login",     level="info")
            _seed(db, action="sync_error", level="error")
            p = admin_service.get_filtered_logs(level="error")
            assert p.total == 1
            assert p.items[0].level == "error"

    def test_filter_by_actor(self, app, db):
        with app.app_context():
            _seed(db, action="login", actor="alice")
            _seed(db, action="login", actor="bob")
            p = admin_service.get_filtered_logs(actor="alice")
            assert p.total == 1
            assert p.items[0].actor == "alice"

    def test_filter_search_matches_actor_and_detail(self, app, db):
        with app.app_context():
            _seed(db, action="login", actor="alice",  detail="por la mañana")
            _seed(db, action="login", actor="bobby",  detail="por la tarde")
            p_actor  = admin_service.get_filtered_logs(search="alice")
            assert p_actor.total == 1
            p_detail = admin_service.get_filtered_logs(search="tarde")
            assert p_detail.total == 1

    def test_filter_last_24h(self, app, db):
        with app.app_context():
            recent = _seed(db, action="login", actor="r")
            # Fuerza uno antiguo
            old = _seed(db, action="login", actor="o")
            old.created_at = datetime.now(timezone.utc) - timedelta(days=3)
            _db.session.commit()
            p = admin_service.get_filtered_logs(last_24h=True)
            assert p.total == 1
            assert p.items[0].actor == "r"

    def test_filter_combined(self, app, db):
        with app.app_context():
            _seed(db, action="login",       actor="alice", level="info")
            _seed(db, action="sync_error",  actor="system", level="error")
            _seed(db, action="login",       actor="alice", level="error")
            # Buscamos los errores de alice (solo el login con level=error)
            p = admin_service.get_filtered_logs(actor="alice", level="error")
            assert p.total == 1
            assert p.items[0].action == "login"


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — resumen y actores
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditSummary:

    def test_counts_per_category(self, app, db):
        with app.app_context():
            _seed(db, action="login")                     # auth
            _seed(db, action="logout")                    # auth
            _seed(db, action="sync_ok",  actor="system")  # sync
            _seed(db, action="role_changed")              # role
            _seed(db, action="quota_change")              # quota
            s = admin_service.get_audit_summary()
            assert s["by_category"]["auth"]  == 2
            assert s["by_category"]["sync"]  == 1
            assert s["by_category"]["role"]  == 1
            assert s["by_category"]["quota"] == 1
            assert s["by_category"]["admin"] == 0
            assert s["total"] == 5

    def test_counts_errors(self, app, db):
        with app.app_context():
            _seed(db, action="login",       level="info")
            _seed(db, action="sync_error",  level="error")
            _seed(db, action="sync_error",  level="error")
            s = admin_service.get_audit_summary()
            assert s["errors"] == 2

    def test_last_24h_count(self, app, db):
        with app.app_context():
            _seed(db, action="login", actor="recent")
            old = _seed(db, action="login", actor="old")
            old.created_at = datetime.now(timezone.utc) - timedelta(days=2)
            _db.session.commit()
            s = admin_service.get_audit_summary()
            assert s["last_24h"] == 1

    def test_distinct_actors(self, app, db):
        with app.app_context():
            _seed(db, action="login", actor="alice")
            _seed(db, action="login", actor="alice")  # duplicado
            _seed(db, action="login", actor="bob")
            actors = admin_service.get_distinct_actors()
            assert set(actors) == {"alice", "bob"}


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLER — GET /auditoria/
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditController:

    def test_redirects_unauthenticated(self, client):
        resp = client.get("/auditoria/")
        assert resp.status_code in (302, 401)

    def test_renders_ok_empty(self, auth_client):
        resp = auth_client.get("/auditoria/")
        assert resp.status_code == 200

    def test_renders_summary_chips(self, auth_client):
        """Los chips de categoría deben aparecer en el HTML."""
        resp = auth_client.get("/auditoria/")
        # Etiquetas de las 5 categorías
        for label in ("Acceso", "Administración", "Cuotas",
                      "Sincronización", "Cambios de rol"):
            assert label.encode("utf-8") in resp.data

    def test_renders_filter_form(self, auth_client):
        """El formulario expone los 6 controles de filtrado. Tras la refactor
        Categoría/Nivel/Actor pasaron a ser `<select>` planos (sin id, basta con
        que aparezca el `name=`), y Desde/Hasta están dentro de un dropdown."""
        resp = auth_client.get("/auditoria/")
        assert b'id="f-q"' in resp.data
        assert b'name="category"' in resp.data
        assert b'name="level"'    in resp.data
        assert b'name="actor"'    in resp.data
        assert b'name="date_from"' in resp.data
        assert b'name="date_to"'   in resp.data

    def test_renders_humanized_actions(self, app, db, auth_client):
        with app.app_context():
            _seed(db, action="login", actor="alice")
        resp = auth_client.get("/auditoria/")
        assert "Inicio de sesión".encode("utf-8") in resp.data

    def test_filter_by_category_via_url(self, app, db, auth_client):
        with app.app_context():
            _seed(db, action="login",      actor="a")
            _seed(db, action="sync_error", actor="system", level="error")
        # Filtra por sync — sólo aparece sync_error, no login
        resp = auth_client.get("/auditoria/?category=sync")
        assert b"sync_error" in resp.data
        # "Inicio de sesión" NO debe aparecer
        assert "Inicio de sesión".encode("utf-8") not in resp.data

    def test_filter_by_level_via_url(self, app, db, auth_client):
        with app.app_context():
            _seed(db, action="login",      level="info")
            _seed(db, action="sync_error", level="error")
        resp = auth_client.get("/auditoria/?level=error")
        assert b"sync_error" in resp.data
        # El login info no debe aparecer
        assert "Inicio de sesión".encode("utf-8") not in resp.data

    def test_filter_search_via_url(self, app, db, auth_client):
        with app.app_context():
            _seed(db, action="login", actor="alice", detail="needle_unique_xyz")
            _seed(db, action="login", actor="alice", detail="haystack_unique_qqq")
        resp = auth_client.get("/auditoria/?q=needle")
        assert b"needle_unique_xyz" in resp.data
        # Detail unique strings nunca aparecen en dropdowns, sólo en la tabla
        assert b"haystack_unique_qqq" not in resp.data

    def test_no_results_shows_friendly_message(self, auth_client):
        resp = auth_client.get("/auditoria/?q=xyznotfound")
        assert resp.status_code == 200
        assert "Ningún registro coincide".encode("utf-8") in resp.data


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION — cuota / rol generan AuditLog
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditIntegration:

    def test_set_user_quota_writes_audit_log(self, app, db):
        from app.model.services import users_service
        from tests.conftest import make_user
        with app.app_context():
            u = make_user(db, "oid-audit-quota")
            users_service.set_user_quota(u.id, 1_000_000, actor="admin")
            log = AuditLog.query.filter_by(action="quota_change").first()
            assert log is not None
            assert log.actor == "admin"

    def test_assign_role_writes_audit_log(self, app, db):
        from app.model.services import roles_service
        from tests.conftest import make_user
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-audit-role")
            roles_service.assign_role(u.id, profesor.id, actor="admin")
            log = AuditLog.query.filter(
                AuditLog.action.in_(["role_assigned", "role_changed"])
            ).first()
            assert log is not None
            assert log.actor == "admin"

    def test_remove_role_writes_audit_log(self, app, db):
        from app.model.services import roles_service
        from tests.conftest import make_user
        with app.app_context():
            profesor = roles_service.get_role_by_name("profesor")
            u = make_user(db, "oid-audit-rem", role=profesor)
            roles_service.remove_role(u.id, actor="admin")
            log = AuditLog.query.filter_by(action="role_removed").first()
            assert log is not None
            assert log.actor == "admin"
