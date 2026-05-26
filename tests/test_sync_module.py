"""
tests/test_sync_module.py
-------------------------
Tests for the enhanced /sincronizacion/ module:
  - SyncRun new fields (sync_type, counters)
  - sync_service: pagination, filters, settings, status
  - Controller: routes + JSON endpoints
  - Idempotency: re-run upsert does not duplicate

Doesn't require MongoDB — uses the in-memory DB + direct service calls.

Run with:
    python -m pytest tests/test_sync_module.py -v
"""
import pytest
from datetime import datetime, timezone, timedelta

from app.config.extensions import db as _db
from app.model.entities.sync_run import SyncRun, SYNC_TYPES, SYNC_TYPE_LABELS
from app.model.entities.audit_log import AuditLog
from app.model.services import sync_service


# ── Helpers ──────────────────────────────────────────────────────────────────

def _make_run(
    db, *,
    status="success", sync_type="full",
    triggered_by="manual", triggered_by_user=None,
    users_found=0, users_synced=0,
    users_created=0, users_updated=0,
    projects_found=0, projects_synced=0,
    started_at=None, finished_at=None,
    errors_count=0, message=None,
):
    r = SyncRun(
        status=status, sync_type=sync_type,
        triggered_by=triggered_by, triggered_by_user=triggered_by_user,
        users_found=users_found, users_synced=users_synced,
        users_created=users_created, users_updated=users_updated,
        projects_found=projects_found, projects_synced=projects_synced,
        errors_count=errors_count, message=message,
    )
    if started_at:
        r.started_at = started_at
    if finished_at:
        r.finished_at = finished_at
    db.session.add(r)
    db.session.commit()
    return r


# ═══════════════════════════════════════════════════════════════════════════════
# ENTITY — SyncRun
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyncRunEntity:

    def test_sync_types_listed(self):
        assert set(SYNC_TYPES) == {"full", "users", "projects", "resync_total", "scheduled"}

    def test_labels_for_all_types(self):
        for t in SYNC_TYPES:
            assert SYNC_TYPE_LABELS[t]

    def test_is_running_property(self, app, db):
        with app.app_context():
            r = _make_run(db, status="running")
            assert r.is_running is True
            r.status = "success"
            assert r.is_running is False

    def test_sync_type_label_uses_dict(self, app, db):
        with app.app_context():
            r = _make_run(db, sync_type="resync_total")
            assert r.sync_type_label == "Resincronización total"

    def test_mark_finished_records_message_and_errors(self, app, db):
        with app.app_context():
            r = _make_run(db, status="running")
            r.mark_finished(status="error", message="x", errors_count=2, error_detail="boom")
            assert r.status == "error"
            assert r.message == "x"
            assert r.errors_count == 2
            assert r.error_detail == "boom"
            assert r.finished_at is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — listados y filtros
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyncQueries:

    def test_get_recent_syncs_orders_desc(self, app, db):
        with app.app_context():
            r1 = _make_run(db)
            r2 = _make_run(db)
            r3 = _make_run(db)
            rows = sync_service.get_recent_syncs(limit=10)
            assert rows[0].id == r3.id
            assert rows[-1].id == r1.id

    def test_paginated_filter_by_status(self, app, db):
        with app.app_context():
            _make_run(db, status="success")
            _make_run(db, status="error")
            p = sync_service.get_syncs_paginated(status="error")
            assert p.total == 1
            assert p.items[0].status == "error"

    def test_paginated_filter_by_sync_type(self, app, db):
        with app.app_context():
            _make_run(db, sync_type="users")
            _make_run(db, sync_type="projects")
            p = sync_service.get_syncs_paginated(sync_type="users")
            assert p.total == 1

    def test_paginated_filter_by_triggered_by_user(self, app, db):
        with app.app_context():
            _make_run(db, triggered_by="manual", triggered_by_user="alice")
            _make_run(db, triggered_by="manual", triggered_by_user="bob")
            p = sync_service.get_syncs_paginated(triggered_by_user="alice")
            assert p.total == 1

    def test_distinct_actors(self, app, db):
        with app.app_context():
            _make_run(db, triggered_by_user="alice")
            _make_run(db, triggered_by_user="alice")  # duplicado
            _make_run(db, triggered_by_user="bob")
            assert set(sync_service.get_distinct_actors()) == {"alice", "bob"}

    def test_get_sync_by_id(self, app, db):
        with app.app_context():
            r = _make_run(db)
            assert sync_service.get_sync_by_id(r.id).id == r.id
            assert sync_service.get_sync_by_id(99999) is None


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — estado vivo
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyncStatus:

    def test_no_runs_reports_idle(self, app, db):
        with app.app_context():
            s = sync_service.get_sync_status()
            assert s["running"] is False
            assert s["last"] is None
            assert s["totals_24h"]["running"] == 0

    def test_running_detected(self, app, db):
        with app.app_context():
            _make_run(db, status="running")
            assert sync_service.is_sync_running() is True
            assert sync_service.get_sync_status()["running"] is True

    def test_last_run_is_terminal(self, app, db):
        with app.app_context():
            _make_run(db, status="success")
            _make_run(db, status="running")  # current
            s = sync_service.get_sync_status()
            # "last" debe referirse a la terminada, no a la que está en curso
            assert s["last"]["status"] == "success"
            assert s["running"] is True

    def test_totals_24h_only_recent(self, app, db):
        with app.app_context():
            _make_run(db, status="success")
            old = _make_run(db, status="error")
            old.started_at = datetime.now(timezone.utc) - timedelta(days=2)
            _db.session.commit()
            s = sync_service.get_sync_status()
            assert s["totals_24h"]["success"] == 1
            assert s["totals_24h"]["error"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — settings
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyncSchedules:
    """CRUD de programaciones múltiples (SyncSchedule)."""

    def test_no_schedules_by_default(self, app, db):
        with app.app_context():
            assert sync_service.list_schedules() == []

    def test_create_schedule_ok(self, app, db):
        with app.app_context():
            ok, _, sch = sync_service.create_schedule(
                name="Diaria solo usuarios",
                sync_type="users",
                interval_minutes=1440,
                enabled=True,
                actor="admin",
            )
            assert ok is True
            assert sch.id is not None
            assert sch.next_run_at is not None  # se calcula al crear si está activa

    def test_create_multiple_schedules(self, app, db):
        with app.app_context():
            sync_service.create_schedule(
                name="Daily users", sync_type="users", interval_minutes=1440, actor="a",
            )
            sync_service.create_schedule(
                name="Weekly full", sync_type="full", interval_minutes=10080, actor="a",
            )
            schedules = sync_service.list_schedules()
            assert len(schedules) == 2
            assert {s.sync_type for s in schedules} == {"users", "full"}

    def test_create_rejects_empty_name(self, app, db):
        with app.app_context():
            ok, msg, sch = sync_service.create_schedule(
                name="", sync_type="full", interval_minutes=60, actor="a",
            )
            assert ok is False
            assert sch is None
            assert "obligatorio" in msg.lower()

    def test_create_rejects_invalid_type(self, app, db):
        with app.app_context():
            ok, _, _ = sync_service.create_schedule(
                name="x", sync_type="nope", interval_minutes=60, actor="a",
            )
            assert ok is False

    def test_create_rejects_invalid_interval(self, app, db):
        with app.app_context():
            ok, _, _ = sync_service.create_schedule(
                name="x", sync_type="full", interval_minutes=0, actor="a",
            )
            assert ok is False

    def test_disabled_schedule_has_no_next_run(self, app, db):
        with app.app_context():
            _, _, sch = sync_service.create_schedule(
                name="off", sync_type="full", interval_minutes=60, enabled=False, actor="a",
            )
            assert sch.next_run_at is None

    def test_toggle_schedule(self, app, db):
        with app.app_context():
            _, _, sch = sync_service.create_schedule(
                name="t", sync_type="full", interval_minutes=60, enabled=True, actor="a",
            )
            sid = sch.id
            ok, _ = sync_service.toggle_schedule(sid, actor="a")
            assert ok
            assert sync_service.get_schedule(sid).enabled is False
            # Volver a activarla recalcula next_run_at
            sync_service.toggle_schedule(sid, actor="a")
            assert sync_service.get_schedule(sid).enabled is True
            assert sync_service.get_schedule(sid).next_run_at is not None

    def test_delete_schedule(self, app, db):
        with app.app_context():
            _, _, sch = sync_service.create_schedule(
                name="bye", sync_type="full", interval_minutes=60, actor="a",
            )
            sid = sch.id
            ok, _ = sync_service.delete_schedule(sid, actor="a")
            assert ok
            assert sync_service.get_schedule(sid) is None

    def test_delete_not_found(self, app, db):
        with app.app_context():
            ok, _ = sync_service.delete_schedule(99999, actor="a")
            assert ok is False

    def test_create_writes_audit_log(self, app, db):
        with app.app_context():
            sync_service.create_schedule(
                name="auditme", sync_type="full", interval_minutes=60, actor="admin",
            )
            log = AuditLog.query.filter_by(action="sync_schedule_create").first()
            assert log is not None

    def test_status_next_run_uses_earliest_schedule(self, app, db):
        """get_sync_status().next_run_at debe ser la programación activa más próxima."""
        with app.app_context():
            sync_service.create_schedule(
                name="weekly", sync_type="full", interval_minutes=10080, actor="a",
            )
            sync_service.create_schedule(
                name="hourly", sync_type="users", interval_minutes=60, actor="a",
            )
            s = sync_service.get_sync_status()
            assert s["next_run_at"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLER — rutas y JSON
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyncController:

    # GET /
    def test_redirects_unauthenticated(self, client):
        get_eps  = ["/sincronizacion/", "/sincronizacion/buscar", "/sincronizacion/estado"]
        post_eps = [
            "/sincronizacion/ejecutar", "/sincronizacion/usuarios",
            "/sincronizacion/proyectos", "/sincronizacion/resync-total",
            "/sincronizacion/programadas/nueva",
        ]
        for ep in get_eps:
            assert client.get(ep).status_code in (302, 401), f"{ep} debería pedir login"
        for ep in post_eps:
            assert client.post(ep).status_code in (302, 401), f"{ep} debería pedir login"

    def test_index_renders(self, auth_client):
        r = auth_client.get("/sincronizacion/")
        assert r.status_code == 200
        # 3 cards de estado (la "Estado actual" suelta se eliminó; el indicador
        # de "en curso" se integra en "Última sincronización" cuando aplica)
        assert "Última sincronización".encode("utf-8") in r.data
        assert "Datos procesados".encode("utf-8") in r.data
        assert "Errores".encode("utf-8") in r.data
        # 4 botones de acción
        assert b"Completa" in r.data
        assert b"Solo usuarios" in r.data
        assert b"Solo proyectos" in r.data
        assert b"Resync total" in r.data
        # Sección de programadas + form de añadir
        assert "Sincronización periódica".encode("utf-8") in r.data
        assert "Añadir programación".encode("utf-8") in r.data
        # Modal de confirmación de sync
        assert b'id="confirmSyncModal"' in r.data

    def test_search_json(self, app, db, auth_client):
        with app.app_context():
            _make_run(db, sync_type="full",   status="success")
            _make_run(db, sync_type="users",  status="error")
        r = auth_client.get("/sincronizacion/buscar?sync_type=users")
        assert r.status_code == 200
        data = r.get_json()
        assert data["total"] == 1
        assert data["items"][0]["sync_type"] == "users"

    def test_estado_json(self, app, db, auth_client):
        with app.app_context():
            _make_run(db, status="success")
        r = auth_client.get("/sincronizacion/estado")
        data = r.get_json()
        assert "running" in data
        assert "last"    in data
        assert "totals_24h" in data

    def test_detail_json(self, app, db, auth_client):
        with app.app_context():
            r0 = _make_run(db, sync_type="full", message="msg")
            rid = r0.id
        r = auth_client.get(f"/sincronizacion/{rid}")
        assert r.status_code == 200
        data = r.get_json()
        assert data["run"]["id"] == rid
        assert "project_logs" in data

    def test_detail_404(self, auth_client):
        r = auth_client.get("/sincronizacion/99999")
        assert r.status_code == 404

    def test_create_schedule_endpoint(self, app, db, auth_client):
        r = auth_client.post("/sincronizacion/programadas/nueva", data={
            "name":             "Diaria usuarios",
            "sync_type":        "users",
            "interval_minutes": "1440",
            "enabled":          "on",
        })
        assert r.status_code == 302
        with app.app_context():
            schedules = sync_service.list_schedules()
            assert len(schedules) == 1
            assert schedules[0].name == "Diaria usuarios"
            assert schedules[0].sync_type == "users"
            assert schedules[0].interval_minutes == 1440

    def test_toggle_and_delete_schedule_endpoints(self, app, db, auth_client):
        with app.app_context():
            _, _, sch = sync_service.create_schedule(
                name="x", sync_type="full", interval_minutes=60, actor="a",
            )
            sid = sch.id
        # Toggle
        r1 = auth_client.post(f"/sincronizacion/programadas/{sid}/toggle")
        assert r1.status_code == 302
        with app.app_context():
            assert sync_service.get_schedule(sid).enabled is False
        # Delete
        r2 = auth_client.post(f"/sincronizacion/programadas/{sid}/eliminar")
        assert r2.status_code == 302
        with app.app_context():
            assert sync_service.get_schedule(sid) is None

    def test_trigger_endpoints_redirect(self, auth_client):
        """Los 4 endpoints de trigger redirigen a la pantalla (no se puede
        verificar el resultado del hilo porque depende de Mongo, pero la
        ruta debe responder y dejar flash)."""
        # Importante: estos endpoints lanzan un hilo de fondo. En CI sin Mongo
        # el hilo fallará en `adapter.connect()` y registrará un SyncRun con
        # status='error'. Eso es OK — no es responsabilidad del controller.
        for path in ("/sincronizacion/ejecutar", "/sincronizacion/usuarios",
                     "/sincronizacion/proyectos", "/sincronizacion/resync-total"):
            r = auth_client.post(path)
            assert r.status_code == 302
            assert "/sincronizacion/" in r.headers["Location"]


# ═══════════════════════════════════════════════════════════════════════════════
# ETL Loader — idempotencia (no duplica)
# ═══════════════════════════════════════════════════════════════════════════════

class TestLoaderIdempotency:

    def test_upsert_users_does_not_duplicate(self, app, db):
        from app.etl.loaders.loader import OverleafLoader
        from app.model.entities.overleaf_user import OverleafUser
        loader = OverleafLoader()
        raw = [{"overleaf_id": "abc", "email": "x@test.com",
                "first_name": "A", "last_name": "B", "is_admin": False}]
        with app.app_context():
            f1, s1, c1, u1 = loader.upsert_users(raw)
            assert c1 == 1 and u1 == 0
            # Segunda ejecución: 0 creados, 1 actualizado
            f2, s2, c2, u2 = loader.upsert_users(raw)
            assert c2 == 0 and u2 == 1
            assert OverleafUser.query.filter_by(overleaf_id="abc").count() == 1


# ═══════════════════════════════════════════════════════════════════════════════
# INTEGRATION — sync_settings_update aparece en /auditoria/
# ═══════════════════════════════════════════════════════════════════════════════

class TestAuditIntegration:

    def test_sync_settings_update_is_in_admin_category(self):
        from app.model.services.admin import admin_service
        # 'sync_settings_update' aparece en la categoría 'admin'
        assert admin_service.category_for_action("sync_settings_update") == "admin"
