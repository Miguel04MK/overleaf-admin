"""
tests/test_alerts.py
--------------------
Tests for the Alerts module: model, service and controller.

Run with:
    python -m pytest tests/test_alerts.py -v
"""
import pytest
from datetime import datetime, timezone

from app.model.entities.system_alert import SystemAlert
from app.model.entities.sync_run import SyncRun
from app.model.entities.audit_log import AuditLog
from app.model.services import alerts_service
from tests.conftest import make_user, make_project


# ── Helpers ───────────────────────────────────────────────────────────────────

def make_alert(db, type="quota_warning", level="warning",
               title="Test", message="Test message",
               entity_type=None, entity_id=None,
               is_read=False, is_resolved=False):
    a = SystemAlert(
        type=type, level=level, title=title, message=message,
        entity_type=entity_type, entity_id=entity_id,
        is_read=is_read, is_resolved=is_resolved,
    )
    db.session.add(a)
    db.session.commit()
    return a


def make_sync_run(db, status="success", message=None):
    r = SyncRun(status=status, triggered_by="manual", message=message)
    db.session.add(r)
    db.session.commit()
    return r


# ═══════════════════════════════════════════════════════════════════════════════
# MODEL
# ═══════════════════════════════════════════════════════════════════════════════

class TestSystemAlertModel:

    def test_defaults_unread_unresolved(self, app, db):
        with app.app_context():
            a = make_alert(db)
            assert a.is_read is False
            assert a.is_resolved is False

    def test_type_label_known(self, app, db):
        with app.app_context():
            a = make_alert(db, type="quota_exceeded")
            assert a.type_label == "Cuota excedida"

    def test_type_label_unknown_falls_back(self, app, db):
        with app.app_context():
            a = make_alert(db, type="unknown_type")
            assert a.type_label == "unknown_type"

    def test_level_badge_class_warning(self, app, db):
        with app.app_context():
            a = make_alert(db, level="warning")
            assert "warning" in a.level_badge_class

    def test_level_badge_class_danger(self, app, db):
        with app.app_context():
            a = make_alert(db, level="danger")
            assert "danger" in a.level_badge_class

    def test_extra_data_empty_when_none(self, app, db):
        with app.app_context():
            a = make_alert(db)
            assert a.extra_data == {}

    def test_extra_data_round_trip(self, app, db):
        import json
        with app.app_context():
            a = make_alert(db)
            a.extra_data_json = json.dumps({"quota_percent": 85.5})
            db.session.commit()
            assert a.extra_data["quota_percent"] == 85.5

    def test_repr_contains_type(self, app, db):
        with app.app_context():
            a = make_alert(db, type="sync_failed")
            assert "sync_failed" in repr(a)

    def test_level_label_in_spanish(self, app, db):
        with app.app_context():
            assert make_alert(db, level="critical").level_label == "Crítico"
            assert make_alert(db, level="danger").level_label   == "Peligro"
            assert make_alert(db, level="warning").level_label  == "Aviso"
            assert make_alert(db, level="info").level_label     == "Información"

    def test_resolution_comment_persisted(self, app, db):
        with app.app_context():
            a = make_alert(db)
            a.resolution_comment = "Revisado, era temporal."
            db.session.commit()
            refreshed = db.session.get(SystemAlert, a.id)
            assert refreshed.resolution_comment == "Revisado, era temporal."

    def test_resolution_comment_none_by_default(self, app, db):
        with app.app_context():
            a = make_alert(db)
            assert a.resolution_comment is None

    def test_project_limit_warning_type_label(self, app, db):
        with app.app_context():
            a = make_alert(db, type="project_limit_warning")
            assert "proyectos" in a.type_label.lower()


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — read helpers
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlertsServiceRead:

    def test_get_active_count(self, app, db):
        with app.app_context():
            make_alert(db, is_resolved=False)
            make_alert(db, is_resolved=False)
            make_alert(db, is_resolved=True)
            assert alerts_service.get_active_count() == 2

    def test_get_unread_count(self, app, db):
        with app.app_context():
            make_alert(db, is_read=False, is_resolved=False)
            make_alert(db, is_read=True,  is_resolved=False)
            make_alert(db, is_read=False, is_resolved=True)
            assert alerts_service.get_unread_count() == 1

    def test_get_critical_count(self, app, db):
        with app.app_context():
            make_alert(db, level="danger",  is_resolved=False)
            make_alert(db, level="critical", is_resolved=False)
            make_alert(db, level="warning", is_resolved=False)
            make_alert(db, level="danger",  is_resolved=True)
            assert alerts_service.get_critical_count() == 2

    def test_get_recent_alerts_limit(self, app, db):
        with app.app_context():
            for i in range(10):
                make_alert(db, title=f"Alert {i}", is_resolved=False)
            result = alerts_service.get_recent_alerts(limit=3)
            assert len(result) == 3

    def test_get_alerts_page_filter_active(self, app, db):
        with app.app_context():
            make_alert(db, is_resolved=False)
            make_alert(db, is_resolved=True)
            pagination = alerts_service.get_alerts_page(status="active")
            assert pagination.total == 1

    def test_get_alerts_page_filter_resolved(self, app, db):
        with app.app_context():
            make_alert(db, is_resolved=False)
            make_alert(db, is_resolved=True)
            pagination = alerts_service.get_alerts_page(status="resolved")
            assert pagination.total == 1

    def test_get_alerts_page_filter_level(self, app, db):
        with app.app_context():
            make_alert(db, level="danger")
            make_alert(db, level="warning")
            pagination = alerts_service.get_alerts_page(level="danger")
            assert pagination.total == 1

    def test_get_alerts_page_filter_q(self, app, db):
        with app.app_context():
            make_alert(db, title="cuota usuario x", message="msg a")
            make_alert(db, title="otro titulo",     message="msg b")
            pagination = alerts_service.get_alerts_page(q="cuota")
            assert pagination.total == 1


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — state mutations
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlertsServiceMutations:

    def test_mark_as_read(self, app, db):
        with app.app_context():
            a = make_alert(db, is_read=False)
            ok, _ = alerts_service.mark_as_read(a.id, actor="admin")
            assert ok is True
            refreshed = db.session.get(SystemAlert, a.id)
            assert refreshed.is_read is True

    def test_mark_as_read_not_found(self, app, db):
        with app.app_context():
            ok, msg = alerts_service.mark_as_read(9999, actor="admin")
            assert ok is False
            assert "no encontrada" in msg.lower()

    def test_mark_as_resolved(self, app, db):
        with app.app_context():
            a = make_alert(db, is_resolved=False)
            ok, _ = alerts_service.mark_as_resolved(a.id, actor="admin")
            assert ok is True
            refreshed = db.session.get(SystemAlert, a.id)
            assert refreshed.is_resolved is True
            assert refreshed.resolved_by == "admin"
            assert refreshed.resolved_at is not None

    def test_mark_as_resolved_already_resolved(self, app, db):
        with app.app_context():
            a = make_alert(db, is_resolved=True)
            ok, msg = alerts_service.mark_as_resolved(a.id, actor="admin")
            assert ok is False

    def test_reopen_alert(self, app, db):
        with app.app_context():
            a = make_alert(db, is_resolved=True)
            ok, _ = alerts_service.reopen_alert(a.id, actor="admin")
            assert ok is True
            refreshed = db.session.get(SystemAlert, a.id)
            assert refreshed.is_resolved is False
            assert refreshed.resolved_by is None

    def test_reopen_not_resolved_fails(self, app, db):
        with app.app_context():
            a = make_alert(db, is_resolved=False)
            ok, _ = alerts_service.reopen_alert(a.id, actor="admin")
            assert ok is False

    def test_mark_as_read_writes_audit_log(self, app, db):
        with app.app_context():
            a = make_alert(db)
            alerts_service.mark_as_read(a.id, actor="testadmin")
            log = AuditLog.query.filter_by(action="alert_mark_read").first()
            assert log is not None
            assert log.actor == "testadmin"

    def test_mark_as_resolved_writes_audit_log(self, app, db):
        with app.app_context():
            a = make_alert(db)
            alerts_service.mark_as_resolved(a.id, actor="testadmin")
            log = AuditLog.query.filter_by(action="alert_resolve").first()
            assert log is not None

    def test_mark_as_resolved_saves_comment(self, app, db):
        with app.app_context():
            a = make_alert(db)
            alerts_service.mark_as_resolved(a.id, actor="admin", comment="Era temporal.")
            refreshed = db.session.get(SystemAlert, a.id)
            assert refreshed.resolution_comment == "Era temporal."
            assert refreshed.resolved_by == "admin"
            assert refreshed.resolved_at is not None

    def test_mark_as_resolved_without_comment(self, app, db):
        with app.app_context():
            a = make_alert(db)
            alerts_service.mark_as_resolved(a.id, actor="admin")
            refreshed = db.session.get(SystemAlert, a.id)
            assert refreshed.resolution_comment is None

    def test_mark_as_resolved_comment_in_audit_log(self, app, db):
        with app.app_context():
            a = make_alert(db)
            alerts_service.mark_as_resolved(a.id, actor="admin", comment="Revisado OK.")
            log = AuditLog.query.filter_by(action="alert_resolve").first()
            assert log is not None
            assert "Revisado OK." in log.detail

    def test_reopen_keeps_resolution_comment(self, app, db):
        with app.app_context():
            a = make_alert(db, is_resolved=True)
            a.resolution_comment = "Comentario previo."
            db.session.commit()
            alerts_service.reopen_alert(a.id, actor="admin")
            refreshed = db.session.get(SystemAlert, a.id)
            assert refreshed.is_resolved is False
            # Comment preserved as audit trail
            assert refreshed.resolution_comment == "Comentario previo."


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — generators
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlertsGenerators:

    def test_quota_warning_alert_created(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-aw1", max_quota_bytes=1000)
            make_project(db, "proj-aw1", owner=u, size_bytes=850)
            alerts_service.generate_quota_alerts()
            alert = SystemAlert.query.filter_by(
                type="quota_warning", entity_id=str(u.id), is_resolved=False
            ).first()
            assert alert is not None
            assert alert.level == "warning"

    def test_quota_exceeded_alert_created(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-ae1", max_quota_bytes=1000)
            make_project(db, "proj-ae1", owner=u, size_bytes=1100)
            alerts_service.generate_quota_alerts()
            alert = SystemAlert.query.filter_by(
                type="quota_exceeded", entity_id=str(u.id), is_resolved=False
            ).first()
            assert alert is not None
            assert alert.level == "danger"

    def test_quota_no_alert_under_threshold(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-an1", max_quota_bytes=1000)
            make_project(db, "proj-an1", owner=u, size_bytes=500)
            alerts_service.generate_quota_alerts()
            count = SystemAlert.query.filter(
                SystemAlert.entity_id == str(u.id),
                SystemAlert.is_resolved == False,  # noqa: E712
            ).count()
            assert count == 0

    def test_no_duplicate_on_recalculate(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-nd1", max_quota_bytes=1000)
            make_project(db, "proj-nd1", owner=u, size_bytes=900)
            alerts_service.generate_quota_alerts()
            alerts_service.generate_quota_alerts()
            count = SystemAlert.query.filter_by(
                type="quota_warning", entity_id=str(u.id), is_resolved=False
            ).count()
            assert count == 1

    def test_quota_warning_auto_resolved_when_fixed(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-ar1", max_quota_bytes=1000)
            p = make_project(db, "proj-ar1", owner=u, size_bytes=900)
            alerts_service.generate_quota_alerts()
            # Now drop usage below threshold
            p.size_bytes = 100
            db.session.commit()
            alerts_service.generate_quota_alerts()
            active = SystemAlert.query.filter_by(
                type="quota_warning", entity_id=str(u.id), is_resolved=False
            ).first()
            assert active is None

    def test_sync_failed_alert_created(self, app, db):
        with app.app_context():
            make_sync_run(db, status="error", message="Connection refused")
            alerts_service.generate_sync_alerts()
            alert = SystemAlert.query.filter_by(
                type="sync_failed", is_resolved=False
            ).first()
            assert alert is not None

    def test_sync_ok_auto_resolves_alert(self, app, db):
        with app.app_context():
            make_sync_run(db, status="error")
            alerts_service.generate_sync_alerts()
            assert SystemAlert.query.filter_by(type="sync_failed", is_resolved=False).count() == 1
            make_sync_run(db, status="success")
            alerts_service.generate_sync_alerts()
            assert SystemAlert.query.filter_by(type="sync_failed", is_resolved=False).count() == 0

    def test_audit_repeated_errors_alert(self, app, db):
        with app.app_context():
            for _ in range(6):
                db.session.add(AuditLog(
                    actor="system", action="some_error",
                    level="error", detail="boom",
                ))
            db.session.commit()
            alerts_service.generate_audit_alerts()
            alert = SystemAlert.query.filter_by(
                type="repeated_errors", is_resolved=False
            ).first()
            assert alert is not None

    def test_audit_no_alert_under_threshold(self, app, db):
        with app.app_context():
            for _ in range(3):
                db.session.add(AuditLog(
                    actor="system", action="some_error", level="error"
                ))
            db.session.commit()
            alerts_service.generate_audit_alerts()
            assert SystemAlert.query.filter_by(type="repeated_errors").count() == 0

    def test_recalculate_writes_audit_log(self, app, db):
        with app.app_context():
            alerts_service.recalculate_alerts(actor="testadmin")
            log = AuditLog.query.filter_by(action="alerts_recalculate").first()
            assert log is not None
            assert log.actor == "testadmin"

    def test_project_limit_warning_created(self, app, db):
        with app.app_context():
            from tests.conftest import make_role
            r = make_role(db, "LimWarn", max_projects=5)
            u = make_user(db, "oid-plw1", role=r)
            for i in range(4):  # 4/5 = 80 %
                make_project(db, f"proj-plw{i}", owner=u)
            alerts_service.generate_project_limit_alerts()
            alert = SystemAlert.query.filter_by(
                type="project_limit_warning", entity_id=str(u.id), is_resolved=False
            ).first()
            assert alert is not None
            assert alert.level == "warning"

    def test_project_limit_warning_not_created_below_threshold(self, app, db):
        with app.app_context():
            from tests.conftest import make_role
            r = make_role(db, "LimWarnOk", max_projects=5)
            u = make_user(db, "oid-plw2", role=r)
            for i in range(3):  # 3/5 = 60 % — below 80 %
                make_project(db, f"proj-plwok{i}", owner=u)
            alerts_service.generate_project_limit_alerts()
            assert SystemAlert.query.filter_by(
                type="project_limit_warning", entity_id=str(u.id), is_resolved=False
            ).count() == 0

    def test_project_limit_warning_auto_resolved_when_exceeded(self, app, db):
        """When user crosses the limit, warning resolves and exceeded fires."""
        with app.app_context():
            from tests.conftest import make_role
            r = make_role(db, "LimWarnEx", max_projects=5)
            u = make_user(db, "oid-plwex", role=r)
            for i in range(4):
                make_project(db, f"proj-plwex{i}", owner=u)
            alerts_service.generate_project_limit_alerts()
            assert SystemAlert.query.filter_by(
                type="project_limit_warning", entity_id=str(u.id), is_resolved=False
            ).count() == 1
            make_project(db, "proj-plwex4-extra", owner=u)
            make_project(db, "proj-plwex5-extra", owner=u)
            alerts_service.generate_project_limit_alerts()
            assert SystemAlert.query.filter_by(
                type="project_limit_warning", entity_id=str(u.id), is_resolved=False
            ).count() == 0
            assert SystemAlert.query.filter_by(
                type="project_limit_exceeded", entity_id=str(u.id), is_resolved=False
            ).count() == 1


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLER
# ═══════════════════════════════════════════════════════════════════════════════

class TestAlertsController:

    def test_list_redirects_unauthenticated(self, client):
        resp = client.get("/alertas/")
        assert resp.status_code in (302, 401)

    def test_list_renders_ok(self, auth_client):
        resp = auth_client.get("/alertas/")
        assert resp.status_code == 200

    def test_list_shows_summary_cards(self, auth_client):
        resp = auth_client.get("/alertas/")
        assert b"Alertas activas" in resp.data

    def test_search_returns_json(self, auth_client):
        resp = auth_client.get("/alertas/buscar")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "alerts" in data
        assert "total" in data

    def test_recalculate_redirects(self, auth_client):
        resp = auth_client.post("/alertas/recalcular")
        assert resp.status_code == 302
        assert "/alertas/" in resp.headers["Location"]

    def test_recalculate_writes_audit_log(self, app, db, auth_client):
        auth_client.post("/alertas/recalcular")
        with app.app_context():
            log = AuditLog.query.filter_by(action="alerts_recalculate").first()
            assert log is not None

    def test_mark_read_redirects(self, app, db, auth_client):
        with app.app_context():
            a = make_alert(db)
            aid = a.id
        resp = auth_client.post(f"/alertas/{aid}/leer")
        assert resp.status_code == 302

    def test_mark_read_updates_state(self, app, db, auth_client):
        with app.app_context():
            a = make_alert(db, is_read=False)
            aid = a.id
        auth_client.post(f"/alertas/{aid}/leer")
        with app.app_context():
            refreshed = db.session.get(SystemAlert, aid)
            assert refreshed.is_read is True

    def test_resolve_redirects(self, app, db, auth_client):
        with app.app_context():
            a = make_alert(db)
            aid = a.id
        resp = auth_client.post(f"/alertas/{aid}/resolver")
        assert resp.status_code == 302

    def test_resolve_updates_state(self, app, db, auth_client):
        with app.app_context():
            a = make_alert(db, is_resolved=False)
            aid = a.id
        auth_client.post(f"/alertas/{aid}/resolver")
        with app.app_context():
            refreshed = db.session.get(SystemAlert, aid)
            assert refreshed.is_resolved is True

    def test_reopen_updates_state(self, app, db, auth_client):
        with app.app_context():
            a = make_alert(db, is_resolved=True)
            aid = a.id
        auth_client.post(f"/alertas/{aid}/reabrir")
        with app.app_context():
            refreshed = db.session.get(SystemAlert, aid)
            assert refreshed.is_resolved is False

    def test_dashboard_includes_alert_count(self, app, db, auth_client):
        with app.app_context():
            make_alert(db, is_resolved=False)
        resp = auth_client.get("/")
        assert resp.status_code == 200
        # The dashboard shows the alert block when there are active alerts
        assert b"Alertas recientes" in resp.data

    def test_list_no_longer_triggers_recalculate(self, app, db, auth_client):
        """Loading the alerts page must NOT call recalculate (no audit log written)."""
        auth_client.get("/alertas/")
        with app.app_context():
            log = AuditLog.query.filter_by(action="alerts_recalculate").first()
            assert log is None

    def test_search_no_longer_triggers_recalculate(self, app, db, auth_client):
        """The AJAX search endpoint must NOT trigger recalculation."""
        auth_client.get("/alertas/buscar")
        with app.app_context():
            log = AuditLog.query.filter_by(action="alerts_recalculate").first()
            assert log is None

    def test_search_default_returns_all_statuses(self, app, db, auth_client):
        """Default search (no filters) must return both active and resolved alerts."""
        with app.app_context():
            make_alert(db, is_resolved=False)
            make_alert(db, is_resolved=True)
        resp = auth_client.get("/alertas/buscar")
        data = resp.get_json()
        assert data["total"] == 2

    def test_search_status_active_filters_correctly(self, app, db, auth_client):
        with app.app_context():
            make_alert(db, is_resolved=False)
            make_alert(db, is_resolved=True)
        resp = auth_client.get("/alertas/buscar?status=active")
        data = resp.get_json()
        assert data["total"] == 1

    def test_search_status_resolved_filters_correctly(self, app, db, auth_client):
        with app.app_context():
            make_alert(db, is_resolved=False)
            make_alert(db, is_resolved=True)
        resp = auth_client.get("/alertas/buscar?status=resolved")
        data = resp.get_json()
        assert data["total"] == 1

    def test_resolve_with_comment_persists(self, app, db, auth_client):
        with app.app_context():
            a = make_alert(db, is_resolved=False)
            aid = a.id
        auth_client.post(
            f"/alertas/{aid}/resolver",
            data={"comment": "Revisado."},
        )
        with app.app_context():
            refreshed = db.session.get(SystemAlert, aid)
            assert refreshed.is_resolved is True
            assert refreshed.resolution_comment == "Revisado."

    def test_resolve_json_with_comment(self, app, db, auth_client):
        import json as _json
        with app.app_context():
            a = make_alert(db, is_resolved=False)
            aid = a.id
        resp = auth_client.post(
            f"/alertas/{aid}/resolver",
            data=_json.dumps({"comment": "JSON comment."}),
            content_type="application/json",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        with app.app_context():
            refreshed = db.session.get(SystemAlert, aid)
            assert refreshed.resolution_comment == "JSON comment."

    def test_detail_endpoint_returns_json(self, app, db, auth_client):
        with app.app_context():
            a = make_alert(db)
            aid = a.id
        resp = auth_client.get(f"/alertas/{aid}", headers={"Accept": "application/json"})
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["id"] == aid
        assert "level_label" in data
        assert "resolution_comment" in data
        assert "resolved_at" in data
        assert "detail_url" in data

    def test_detail_endpoint_404_for_unknown(self, auth_client):
        resp = auth_client.get("/alertas/99999", headers={"Accept": "application/json"})
        assert resp.status_code == 404

    def test_level_labels_in_search_response(self, app, db, auth_client):
        with app.app_context():
            make_alert(db, level="critical")
            make_alert(db, level="danger")
            make_alert(db, level="warning")
            make_alert(db, level="info")
        resp = auth_client.get("/alertas/buscar")
        data = resp.get_json()
        labels = {a["level_label"] for a in data["alerts"]}
        assert "Crítico"     in labels
        assert "Peligro"     in labels
        assert "Aviso"       in labels
        assert "Información" in labels

    def test_resolved_alert_shows_who_and_when(self, app, db, auth_client):
        with app.app_context():
            a = make_alert(db, is_resolved=False)
            alerts_service.mark_as_resolved(a.id, actor="superadmin", comment="OK")
        resp = auth_client.get("/alertas/buscar")
        data = resp.get_json()
        resolved = next(x for x in data["alerts"] if x["is_resolved"])
        assert resolved["resolved_by"] == "superadmin"
        assert resolved["resolved_at"] is not None
        assert resolved["resolution_comment"] == "OK"

    def test_search_response_has_no_resolved_count(self, auth_client):
        """resolved_count was removed from summary; search response should not include it."""
        resp = auth_client.get("/alertas/buscar")
        data = resp.get_json()
        assert "resolved_count" not in data


# ═══════════════════════════════════════════════════════════════════════════════
# EVENT-DRIVEN CHECK FUNCTIONS
# ═══════════════════════════════════════════════════════════════════════════════

class TestEventDrivenChecks:

    # ── check_user_quota ──────────────────────────────────────────────────────

    def test_check_user_quota_creates_warning_alert(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-cq1", max_quota_bytes=1000)
            make_project(db, "proj-cq1", owner=u, size_bytes=850)
            alerts_service.check_user_quota(u.id)
            alert = SystemAlert.query.filter_by(
                type="quota_warning", entity_id=str(u.id), is_resolved=False
            ).first()
            assert alert is not None

    def test_check_user_quota_creates_exceeded_alert(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-cq2", max_quota_bytes=1000)
            make_project(db, "proj-cq2", owner=u, size_bytes=1100)
            alerts_service.check_user_quota(u.id)
            alert = SystemAlert.query.filter_by(
                type="quota_exceeded", entity_id=str(u.id), is_resolved=False
            ).first()
            assert alert is not None

    def test_check_user_quota_resolves_when_no_quota_set(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-cq3", max_quota_bytes=1000)
            make_project(db, "proj-cq3", owner=u, size_bytes=900)
            alerts_service.generate_quota_alerts()
            assert SystemAlert.query.filter_by(
                type="quota_warning", entity_id=str(u.id), is_resolved=False
            ).count() == 1
            # Remove quota limit
            u.max_quota_bytes = None
            db.session.commit()
            alerts_service.check_user_quota(u.id)
            assert SystemAlert.query.filter_by(
                type="quota_warning", entity_id=str(u.id), is_resolved=False
            ).count() == 0

    def test_check_user_quota_noop_for_unknown_user(self, app, db):
        with app.app_context():
            alerts_service.check_user_quota(99999)
            assert SystemAlert.query.count() == 0

    def test_check_user_quota_no_duplicate_on_repeated_calls(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-cq4", max_quota_bytes=1000)
            make_project(db, "proj-cq4", owner=u, size_bytes=900)
            alerts_service.check_user_quota(u.id)
            alerts_service.check_user_quota(u.id)
            assert SystemAlert.query.filter_by(
                type="quota_warning", entity_id=str(u.id), is_resolved=False
            ).count() == 1

    # ── check_user_project_limit ──────────────────────────────────────────────

    def test_check_user_project_limit_creates_alert(self, app, db):
        with app.app_context():
            from tests.conftest import make_role
            r = make_role(db, "Limitado", max_projects=1)
            u = make_user(db, "oid-cp1", role=r)
            make_project(db, "proj-cp1a", owner=u)
            make_project(db, "proj-cp1b", owner=u)
            alerts_service.check_user_project_limit(u.id)
            alert = SystemAlert.query.filter_by(
                type="project_limit_exceeded", entity_id=str(u.id), is_resolved=False
            ).first()
            assert alert is not None

    def test_check_user_project_limit_resolves_when_within_limit(self, app, db):
        with app.app_context():
            from tests.conftest import make_role
            r = make_role(db, "LimitadoB", max_projects=2)
            u = make_user(db, "oid-cp2", role=r)
            make_project(db, "proj-cp2a", owner=u)
            make_project(db, "proj-cp2b", owner=u)
            make_project(db, "proj-cp2c", owner=u)
            alerts_service.check_user_project_limit(u.id)
            assert SystemAlert.query.filter_by(
                type="project_limit_exceeded", entity_id=str(u.id), is_resolved=False
            ).count() == 1
            # Remove one project
            from app.model.entities.overleaf_project import OverleafProject
            extra = OverleafProject.query.filter_by(overleaf_id="proj-cp2c").first()
            db.session.delete(extra)
            db.session.commit()
            alerts_service.check_user_project_limit(u.id)
            assert SystemAlert.query.filter_by(
                type="project_limit_exceeded", entity_id=str(u.id), is_resolved=False
            ).count() == 0

    def test_check_user_project_limit_noop_for_unknown_user(self, app, db):
        with app.app_context():
            alerts_service.check_user_project_limit(99999)
            assert SystemAlert.query.count() == 0

    # ── check_role_users ──────────────────────────────────────────────────────

    def test_check_role_users_creates_alerts_for_all_users(self, app, db):
        with app.app_context():
            from tests.conftest import make_role
            r = make_role(db, "GrupoTest", max_projects=1)
            u1 = make_user(db, "oid-cr1", role=r, max_quota_bytes=1000)
            u2 = make_user(db, "oid-cr2", role=r, max_quota_bytes=1000)
            make_project(db, "proj-cr1a", owner=u1)
            make_project(db, "proj-cr1b", owner=u1)
            make_project(db, "proj-cr2a", owner=u2)
            make_project(db, "proj-cr2b", owner=u2)
            alerts_service.check_role_users(r.id)
            count = SystemAlert.query.filter_by(
                type="project_limit_exceeded", is_resolved=False
            ).count()
            assert count == 2

    def test_check_role_users_noop_for_unknown_role(self, app, db):
        with app.app_context():
            alerts_service.check_role_users(99999)
            assert SystemAlert.query.count() == 0

    def test_check_role_users_resolves_when_limit_raised(self, app, db):
        with app.app_context():
            from tests.conftest import make_role
            r = make_role(db, "GrupoFlex", max_projects=1)
            u = make_user(db, "oid-cr3", role=r)
            make_project(db, "proj-cr3a", owner=u)
            make_project(db, "proj-cr3b", owner=u)
            alerts_service.check_role_users(r.id)
            assert SystemAlert.query.filter_by(
                type="project_limit_exceeded", is_resolved=False
            ).count() == 1
            r.max_projects = 10
            db.session.commit()
            alerts_service.check_role_users(r.id)
            assert SystemAlert.query.filter_by(
                type="project_limit_exceeded", is_resolved=False
            ).count() == 0

    # ── check_last_sync ───────────────────────────────────────────────────────

    def test_check_last_sync_creates_alert_on_error(self, app, db):
        with app.app_context():
            make_sync_run(db, status="error", message="Timeout")
            alerts_service.check_last_sync()
            alert = SystemAlert.query.filter_by(
                type="sync_failed", is_resolved=False
            ).first()
            assert alert is not None

    def test_check_last_sync_resolves_on_success(self, app, db):
        with app.app_context():
            make_sync_run(db, status="error")
            alerts_service.check_last_sync()
            assert SystemAlert.query.filter_by(
                type="sync_failed", is_resolved=False
            ).count() == 1
            make_sync_run(db, status="success")
            alerts_service.check_last_sync()
            assert SystemAlert.query.filter_by(
                type="sync_failed", is_resolved=False
            ).count() == 0


# ═══════════════════════════════════════════════════════════════════════════════
# DEDUPLICATION — _upsert behaviour
# ═══════════════════════════════════════════════════════════════════════════════

class TestDeduplication:
    """
    Tests for the _upsert() deduplication logic.

    Key rules:
      • Same (type, entity_type, entity_id) + active → update in-place, no new row.
      • If the existing alert is resolved and the condition recurs → brand new alert.
      • Different entity_id / type → separate alerts.
    """

    def _upsert(self, type_="service_down", level="critical",
                title="Test", message="msg",
                entity_type=None, entity_id=None):
        return alerts_service._upsert(
            type=type_, level=level, title=title, message=message,
            entity_type=entity_type, entity_id=entity_id,
        )

    def test_first_upsert_creates_one_row(self, app, db):
        with app.app_context():
            a = self._upsert("service_down", entity_type="system", entity_id="mongo")
            assert a.id is not None
            assert SystemAlert.query.count() == 1

    def test_second_upsert_same_key_no_duplicate(self, app, db):
        with app.app_context():
            a1 = self._upsert("service_down", entity_type="system", entity_id="mongo")
            a2 = self._upsert("service_down", entity_type="system", entity_id="mongo")
            assert a1.id == a2.id
            assert SystemAlert.query.count() == 1

    def test_upsert_updates_message_in_place(self, app, db):
        with app.app_context():
            self._upsert("service_down", message="First",
                         entity_type="system", entity_id="mongo")
            a2 = self._upsert("service_down", message="Updated",
                               entity_type="system", entity_id="mongo")
            assert a2.message == "Updated"
            assert SystemAlert.query.count() == 1

    def test_upsert_creates_new_row_after_resolved_service_down(self, app, db):
        with app.app_context():
            a1 = self._upsert("service_down",
                               entity_type="system", entity_id="mongo")
            a1.is_resolved = True
            db.session.commit()

            a2 = self._upsert("service_down",
                               entity_type="system", entity_id="mongo")
            assert a2.id != a1.id
            assert SystemAlert.query.count() == 2

    def test_upsert_creates_new_row_after_resolved_sync_failed(self, app, db):
        with app.app_context():
            a1 = self._upsert("sync_failed",
                               entity_type="system", entity_id="latest")
            a1.is_resolved = True
            db.session.commit()

            a2 = self._upsert("sync_failed",
                               entity_type="system", entity_id="latest")
            assert a2.id != a1.id
            assert SystemAlert.query.count() == 2

    def test_different_entity_ids_are_separate(self, app, db):
        with app.app_context():
            a1 = self._upsert("quota_exceeded", entity_type="user", entity_id="u1")
            a2 = self._upsert("quota_exceeded", entity_type="user", entity_id="u2")
            assert a1.id != a2.id
            assert SystemAlert.query.count() == 2

    def test_different_types_are_separate(self, app, db):
        with app.app_context():
            a1 = self._upsert("quota_warning",  entity_type="user", entity_id="u1")
            a2 = self._upsert("quota_exceeded", entity_type="user", entity_id="u1")
            assert a1.id != a2.id
            assert SystemAlert.query.count() == 2


# ═══════════════════════════════════════════════════════════════════════════════
# BACKEND PAGINATION — get_alerts_page
# ═══════════════════════════════════════════════════════════════════════════════

class TestBackendPagination:

    def _seed(self, db, count=25):
        levels = ["critical", "danger", "warning", "info"]
        for i in range(count):
            make_alert(db, level=levels[i % 4],
                       type=("service_down" if i % 2 == 0 else "sync_failed"),
                       title=f"Alert {i}")

    def test_first_page_returns_per_page_rows(self, app, db):
        with app.app_context():
            self._seed(db, 25)
            page = alerts_service.get_alerts_page(page=1, per_page=10, status="all")
            assert len(page.items) == 10
            assert page.total == 25
            assert page.pages == 3

    def test_last_page_returns_remainder(self, app, db):
        with app.app_context():
            self._seed(db, 25)
            page = alerts_service.get_alerts_page(page=3, per_page=10, status="all")
            assert len(page.items) == 5

    def test_pages_are_disjoint(self, app, db):
        with app.app_context():
            self._seed(db, 20)
            p1 = {a.id for a in alerts_service.get_alerts_page(page=1, per_page=10, status="all").items}
            p2 = {a.id for a in alerts_service.get_alerts_page(page=2, per_page=10, status="all").items}
            assert p1.isdisjoint(p2)

    def test_page_beyond_range_returns_empty(self, app, db):
        with app.app_context():
            self._seed(db, 5)
            page = alerts_service.get_alerts_page(page=99, per_page=10, status="all")
            assert page.items == []

    def test_sort_active_before_resolved(self, app, db):
        with app.app_context():
            make_alert(db, type="sync_failed",  is_resolved=True)   # resolved first
            make_alert(db, type="service_down", is_resolved=False)  # active second
            page = alerts_service.get_alerts_page(status="all")
            # Active must come first regardless of insertion order
            assert not page.items[0].is_resolved
            assert page.items[1].is_resolved

    def test_sort_critical_before_danger(self, app, db):
        with app.app_context():
            make_alert(db, level="danger",   is_resolved=False)
            make_alert(db, level="critical", is_resolved=False)
            page = alerts_service.get_alerts_page(status="active")
            assert page.items[0].level == "critical"
            assert page.items[1].level == "danger"

    def test_search_endpoint_returns_pagination_metadata(self, app, db, auth_client):
        with app.app_context():
            self._seed(db, 15)
        resp = auth_client.get(
            "/alertas/buscar?page=2&per_page=5&status=all",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["page"] == 2
        assert data["per_page"] == 5
        assert "pages" in data
        assert "has_next" in data
        assert "has_prev" in data
        assert len(data["alerts"]) <= 5


# ═══════════════════════════════════════════════════════════════════════════════
# BULK MUTATIONS
# ═══════════════════════════════════════════════════════════════════════════════

class TestBulkMutations:

    def test_mark_many_read_count(self, app, db):
        with app.app_context():
            a1 = make_alert(db, type="service_down")
            a2 = make_alert(db, type="sync_failed")
            count = alerts_service.mark_many_read([a1.id, a2.id], actor="admin")
            assert count == 2

    def test_mark_many_read_sets_flag(self, app, db):
        with app.app_context():
            a = make_alert(db, is_read=False)
            alerts_service.mark_many_read([a.id], actor="admin")
            db.session.refresh(a)
            assert a.is_read is True

    def test_mark_many_read_skips_already_read(self, app, db):
        with app.app_context():
            a = make_alert(db, is_read=True)
            count = alerts_service.mark_many_read([a.id], actor="admin")
            assert count == 0

    def test_mark_many_read_ignores_unknown_ids(self, app, db):
        with app.app_context():
            count = alerts_service.mark_many_read([99999], actor="admin")
            assert count == 0

    def test_resolve_many_count(self, app, db):
        with app.app_context():
            a1 = make_alert(db, is_resolved=False)
            a2 = make_alert(db, is_resolved=False, type="sync_failed")
            count = alerts_service.resolve_many([a1.id, a2.id], actor="admin")
            assert count == 2

    def test_resolve_many_sets_fields(self, app, db):
        with app.app_context():
            a = make_alert(db, is_resolved=False)
            alerts_service.resolve_many([a.id], actor="admin", comment="done")
            db.session.refresh(a)
            assert a.is_resolved is True
            assert a.is_read is True
            assert a.resolved_by == "admin"
            assert a.resolution_comment == "done"
            assert a.resolved_at is not None

    def test_resolve_many_skips_already_resolved(self, app, db):
        with app.app_context():
            a = make_alert(db, is_resolved=True)
            count = alerts_service.resolve_many([a.id], actor="admin")
            assert count == 0

    def test_reopen_many_count(self, app, db):
        with app.app_context():
            a = make_alert(db, is_resolved=True)
            count = alerts_service.reopen_many([a.id], actor="admin")
            assert count == 1

    def test_reopen_many_clears_fields(self, app, db):
        with app.app_context():
            a = make_alert(db, is_resolved=True)
            alerts_service.reopen_many([a.id], actor="admin")
            db.session.refresh(a)
            assert a.is_resolved is False
            assert a.resolved_at is None
            assert a.resolved_by is None

    def test_reopen_many_skips_active(self, app, db):
        with app.app_context():
            a = make_alert(db, is_resolved=False)
            count = alerts_service.reopen_many([a.id], actor="admin")
            assert count == 0

    def test_bulk_read_http_endpoint(self, app, db, auth_client):
        with app.app_context():
            a = make_alert(db, is_read=False)
            aid = a.id
        resp = auth_client.post(
            "/alertas/bulk/leer",
            json={"ids": [aid]},
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        assert resp.get_json()["updated"] == 1

    def test_bulk_resolve_http_endpoint(self, app, db, auth_client):
        with app.app_context():
            a = make_alert(db, is_resolved=False)
            aid = a.id
        resp = auth_client.post(
            "/alertas/bulk/resolver",
            json={"ids": [aid], "comment": "bulk done"},
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_bulk_reopen_http_endpoint(self, app, db, auth_client):
        with app.app_context():
            a = make_alert(db, is_resolved=True)
            aid = a.id
        resp = auth_client.post(
            "/alertas/bulk/reabrir",
            json={"ids": [aid]},
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True


# ═══════════════════════════════════════════════════════════════════════════════
# CONFIGURABLE THRESHOLDS
# ═══════════════════════════════════════════════════════════════════════════════

class TestThresholds:

    def test_get_thresholds_returns_all_default_keys(self, app, db):
        with app.app_context():
            from app.model.entities.app_setting import DEFAULT_THRESHOLDS
            data = alerts_service.get_thresholds()
            for key in DEFAULT_THRESHOLDS:
                assert key in data
                assert "value" in data[key]
                assert "description" in data[key]

    def test_get_thresholds_uses_hardcoded_defaults_when_no_db_row(self, app, db):
        with app.app_context():
            from app.model.entities.app_setting import DEFAULT_THRESHOLDS
            data = alerts_service.get_thresholds()
            for key, (default_val, _) in DEFAULT_THRESHOLDS.items():
                assert data[key]["value"] == int(default_val)

    def test_update_thresholds_persists_value(self, app, db):
        with app.app_context():
            alerts_service.update_thresholds(
                {"alert.quota_warning_pct": 75}, actor="admin"
            )
            data = alerts_service.get_thresholds()
            assert data["alert.quota_warning_pct"]["value"] == 75

    def test_update_thresholds_overwrites_on_second_call(self, app, db):
        with app.app_context():
            alerts_service.update_thresholds({"alert.sync_max_hours": 12}, actor="a")
            alerts_service.update_thresholds({"alert.sync_max_hours": 48}, actor="a")
            data = alerts_service.get_thresholds()
            assert data["alert.sync_max_hours"]["value"] == 48

    def test_update_thresholds_ignores_unknown_keys(self, app, db):
        with app.app_context():
            from app.model.entities.app_setting import AppSetting
            alerts_service.update_thresholds(
                {"alert.does_not_exist": 99}, actor="admin"
            )
            assert AppSetting.query.filter_by(key="alert.does_not_exist").first() is None

    def test_threshold_helper_returns_default_when_no_row(self, app, db):
        with app.app_context():
            val = alerts_service._threshold("alert.quota_warning_pct", 80)
            assert val == 80

    def test_threshold_helper_returns_db_value_when_row_present(self, app, db):
        with app.app_context():
            from app.model.entities.app_setting import AppSetting
            db.session.add(AppSetting(key="alert.quota_warning_pct", value="65"))
            db.session.commit()
            val = alerts_service._threshold("alert.quota_warning_pct", 80)
            assert val == 65

    def test_get_config_endpoint(self, app, db, auth_client):
        resp = auth_client.get(
            "/alertas/configuracion",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "thresholds" in data

    def test_post_config_endpoint_saves_value(self, app, db, auth_client):
        resp = auth_client.post(
            "/alertas/configuracion",
            json={"alert.quota_warning_pct": 90},
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True
        with app.app_context():
            data = alerts_service.get_thresholds()
            assert data["alert.quota_warning_pct"]["value"] == 90


# ═══════════════════════════════════════════════════════════════════════════════
# NOTIFICATION PREFERENCES — should_notify + AdminNotificationPref
# ═══════════════════════════════════════════════════════════════════════════════

class TestNotificationPrefs:
    """Tests for notification_service.should_notify() and the pref endpoints."""

    from app.model.services.notification_service import should_notify as _sn

    # ── Default fallback (pref=None) ──────────────────────────────────────────

    def test_default_notifies_critical(self):
        from app.model.services.notification_service import should_notify
        assert should_notify(None, "quota_exceeded", "critical") is True

    def test_default_notifies_danger(self):
        from app.model.services.notification_service import should_notify
        assert should_notify(None, "administrative_warning", "danger") is True

    def test_default_notifies_known_type_regardless_of_level(self):
        from app.model.services.notification_service import should_notify
        # repeated_errors is in DEFAULT_TYPES → notify even for warning level
        assert should_notify(None, "repeated_errors", "warning") is True

    def test_default_no_notify_info_unknown_type(self):
        from app.model.services.notification_service import should_notify
        # info level + quota_warning type → neither in defaults
        assert should_notify(None, "quota_warning", "info") is False

    # ── With a real pref object ───────────────────────────────────────────────

    def _make_pref(self, db, **kwargs):
        from app.model.entities.admin_user import AdminUser
        from app.model.entities.admin_notification_pref import AdminNotificationPref
        admin = AdminUser(username="np_admin_" + str(id(kwargs)),
                         email=f"np_{id(kwargs)}@test.com")
        admin.set_password("x")
        db.session.add(admin)
        db.session.flush()
        pref = AdminNotificationPref(admin_id=admin.id)
        for k, v in kwargs.items():
            setattr(pref, k, v)
        db.session.add(pref)
        db.session.commit()
        return pref

    def test_level_true_notifies(self, app, db):
        from app.model.services.notification_service import should_notify
        with app.app_context():
            pref = self._make_pref(db, notify_critical=True,
                                   notify_service_down=False)
            assert should_notify(pref, "sync_failed", "critical") is True

    def test_type_true_notifies(self, app, db):
        from app.model.services.notification_service import should_notify
        with app.app_context():
            pref = self._make_pref(db, notify_info=False,
                                   notify_service_down=True)
            assert should_notify(pref, "service_down", "info") is True

    def test_both_false_no_notify(self, app, db):
        from app.model.services.notification_service import should_notify
        with app.app_context():
            pref = self._make_pref(
                db,
                notify_critical=False, notify_danger=False,
                notify_warning=False,  notify_info=False,
                notify_service_down=False, notify_sync_failed=False,
                notify_quota_exceeded=False, notify_quota_warning=False,
                notify_project_limit_exceeded=False,
                notify_project_limit_warning=False,
                notify_repeated_errors=False,
                notify_administrative_warning=False,
            )
            assert should_notify(pref, "service_down", "critical") is False

    def test_to_dict_has_all_boolean_fields(self, app, db):
        from app.model.entities.admin_notification_pref import AdminNotificationPref
        with app.app_context():
            pref = self._make_pref(db)
            d = pref.to_dict()
            for field in AdminNotificationPref.BOOLEAN_FIELDS:
                assert field in d

    def test_update_from_dict(self, app, db):
        with app.app_context():
            pref = self._make_pref(db, notify_info=False)
            pref.update_from_dict({"notify_info": True})
            db.session.commit()
            db.session.refresh(pref)
            assert pref.notify_info is True

    def test_update_from_dict_ignores_unknown_keys(self, app, db):
        with app.app_context():
            pref = self._make_pref(db)
            pref.update_from_dict({"totally_unknown_key": True})
            # Must not raise

    # ── HTTP endpoints ────────────────────────────────────────────────────────

    def test_get_notif_prefs_creates_defaults(self, app, db, auth_client):
        resp = auth_client.get(
            "/alertas/configuracion/notificaciones",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "notify_critical" in data["prefs"]

    def test_post_notif_prefs_saves(self, app, db, auth_client):
        resp = auth_client.post(
            "/alertas/configuracion/notificaciones",
            json={"notify_critical": False, "notify_info": True},
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        assert resp.get_json()["ok"] is True

    def test_notif_prefs_idempotent(self, app, db, auth_client):
        """Calling GET twice must not create duplicate rows."""
        from app.model.entities.admin_notification_pref import AdminNotificationPref
        auth_client.get("/alertas/configuracion/notificaciones",
                        headers={"Accept": "application/json"})
        auth_client.get("/alertas/configuracion/notificaciones",
                        headers={"Accept": "application/json"})
        with app.app_context():
            count = AdminNotificationPref.query.count()
            assert count == 1


# ═══════════════════════════════════════════════════════════════════════════════
# BATCH NOTIFICATION SYSTEM
# ═══════════════════════════════════════════════════════════════════════════════

class TestBatchNotifications:
    """
    Tests for the batch email notification pipeline:
    pending detection, no re-sends, per-admin filtering,
    summary generation, SMTP diagnostics, and HTTP endpoints.
    """

    # ── get_pending_alerts ────────────────────────────────────────────────────

    def test_pending_alerts_returns_unnotified(self, app, db):
        with app.app_context():
            a = make_alert(db, type="service_down")
            from app.model.services import notification_service
            pending = notification_service.get_pending_alerts()
            assert len(pending) == 1
            assert pending[0].id == a.id

    def test_pending_alerts_excludes_already_notified(self, app, db):
        with app.app_context():
            from datetime import datetime, timezone
            a = make_alert(db, type="service_down")
            a.email_notified_at = datetime.now(timezone.utc)
            db.session.commit()
            from app.model.services import notification_service
            pending = notification_service.get_pending_alerts()
            assert len(pending) == 0

    def test_pending_alerts_excludes_resolved(self, app, db):
        with app.app_context():
            make_alert(db, type="service_down", is_resolved=True)
            from app.model.services import notification_service
            pending = notification_service.get_pending_alerts()
            assert len(pending) == 0

    def test_pending_alerts_mixed(self, app, db):
        """Only unnotified + unresolved alerts are pending."""
        with app.app_context():
            from datetime import datetime, timezone
            a_pending = make_alert(db, type="service_down")
            a_notified = make_alert(db, type="sync_failed")
            a_notified.email_notified_at = datetime.now(timezone.utc)
            a_resolved = make_alert(db, type="quota_exceeded", is_resolved=True)
            db.session.commit()

            from app.model.services import notification_service
            pending = notification_service.get_pending_alerts()
            assert len(pending) == 1
            assert pending[0].id == a_pending.id

    # ── No re-sends ──────────────────────────────────────────────────────────

    def test_send_summary_marks_notified_at(self, app, db):
        """After send_summary_emails, alerts get email_notified_at set."""
        with app.app_context():
            from app.model.entities.admin_user import AdminUser
            admin = AdminUser(username="emailadm", email="emailadm@test.com")
            admin.set_password("x")
            db.session.add(admin)
            db.session.commit()

            a = make_alert(db, type="service_down", level="critical")
            assert a.email_notified_at is None

            from app.model.services import notification_service
            notification_service.send_summary_emails(actor="test")
            db.session.refresh(a)
            assert a.email_notified_at is not None

    def test_second_send_summary_does_not_re_send(self, app, db):
        """Running send_summary_emails twice should not re-send already notified alerts."""
        with app.app_context():
            from app.model.entities.admin_user import AdminUser
            admin = AdminUser(username="emailadm2", email="emailadm2@test.com")
            admin.set_password("x")
            db.session.add(admin)
            db.session.commit()

            make_alert(db, type="service_down", level="critical")

            from app.model.services import notification_service
            r1 = notification_service.send_summary_emails(actor="test")
            assert r1["alerts_notified"] == 1

            r2 = notification_service.send_summary_emails(actor="test")
            assert r2["alerts_notified"] == 0
            assert "No hay alertas pendientes" in r2["details"][0]

    # ── Per-admin preference filtering in batch ──────────────────────────────

    def test_send_summary_respects_admin_prefs(self, app, db):
        """Admin with all notifications OFF gets skipped (0 alerts match)."""
        with app.app_context():
            from app.model.entities.admin_user import AdminUser
            from app.model.entities.admin_notification_pref import AdminNotificationPref
            admin = AdminUser(username="nopref", email="nopref@test.com")
            admin.set_password("x")
            db.session.add(admin)
            db.session.flush()

            # All notifications disabled
            pref = AdminNotificationPref(admin_id=admin.id)
            for field in AdminNotificationPref.BOOLEAN_FIELDS:
                setattr(pref, field, False)
            db.session.add(pref)
            db.session.commit()

            make_alert(db, type="service_down", level="critical")

            from app.model.services import notification_service
            result = notification_service.send_summary_emails(actor="test")
            assert result["sent"] == 0
            assert result["skipped"] == 1

    def test_send_summary_filters_by_type_pref(self, app, db):
        """Admin who only wants quota_exceeded should not get service_down alerts."""
        with app.app_context():
            from app.model.entities.admin_user import AdminUser
            from app.model.entities.admin_notification_pref import AdminNotificationPref
            admin = AdminUser(username="typepref", email="typepref@test.com")
            admin.set_password("x")
            db.session.add(admin)
            db.session.flush()

            pref = AdminNotificationPref(admin_id=admin.id)
            for field in AdminNotificationPref.BOOLEAN_FIELDS:
                setattr(pref, field, False)
            pref.notify_quota_exceeded = True
            db.session.add(pref)
            db.session.commit()

            # Only service_down alerts exist — should not match quota_exceeded pref
            make_alert(db, type="service_down", level="warning")

            from app.model.services import notification_service
            result = notification_service.send_summary_emails(actor="test")
            assert result["sent"] == 0
            assert result["skipped"] == 1

    def test_send_summary_skips_admin_without_email(self, app, db):
        """Admin with no email address gets skipped."""
        with app.app_context():
            from app.model.entities.admin_user import AdminUser
            admin = AdminUser(username="noemail", email="")
            admin.set_password("x")
            db.session.add(admin)
            db.session.commit()

            make_alert(db, type="service_down", level="critical")

            from app.model.services import notification_service
            result = notification_service.send_summary_emails(actor="test")
            assert result["skipped"] >= 1

    def test_send_summary_empty_when_no_pending(self, app, db):
        """No pending alerts → immediate return with zero counts."""
        with app.app_context():
            from app.model.services import notification_service
            result = notification_service.send_summary_emails(actor="test")
            assert result["sent"] == 0
            assert result["alerts_notified"] == 0

    # ── Summary content generation ───────────────────────────────────────────

    def test_build_summary_subject(self, app, db):
        with app.app_context():
            from app.model.services.notification_service import _build_summary_subject
            a1 = make_alert(db, type="service_down", level="critical")
            a2 = make_alert(db, type="sync_failed", level="warning")
            subject = _build_summary_subject([a1, a2])
            assert "[Overleaf Admin]" in subject
            assert "critico" in subject.lower()
            assert "aviso" in subject.lower()

    def test_build_summary_body_contains_admin_name(self, app, db):
        with app.app_context():
            from app.model.services.notification_service import _build_summary_body
            a = make_alert(db, type="service_down", level="critical",
                          title="MongoDB caido", message="No responde")
            body = _build_summary_body([a], "TestAdmin")
            assert "TestAdmin" in body
            assert "MongoDB caido" in body
            assert "No responde" in body
            assert "Critico" in body

    def test_build_summary_body_contains_link(self, app, db):
        with app.app_context():
            from app.model.services.notification_service import _build_summary_body
            a = make_alert(db, type="service_down", level="critical")
            body = _build_summary_body([a], "admin")
            assert "/alertas/" in body

    # ── SMTP diagnostics ─────────────────────────────────────────────────────

    def test_diagnose_smtp_returns_expected_keys(self, app, db):
        with app.app_context():
            from app.model.services import notification_service
            diag = notification_service.diagnose_smtp()
            for key in ("mock", "host", "port", "user", "from", "tls",
                        "base_url", "issues", "ready"):
                assert key in diag

    def test_diagnose_smtp_mock_mode_is_ready(self, app, db):
        """In mock mode, ready should always be True."""
        with app.app_context():
            from app.model.services import notification_service
            diag = notification_service.diagnose_smtp()
            # Default test env has SMTP_MOCK=true
            if diag["mock"]:
                assert diag["ready"] is True

    def test_diagnose_smtp_password_masked(self, app, db):
        with app.app_context():
            from app.model.services import notification_service
            diag = notification_service.diagnose_smtp()
            assert diag["password"] in ("****", "(vacio)")

    # ── SMTP not configured does not break ───────────────────────────────────

    def test_send_summary_with_mock_smtp_succeeds(self, app, db):
        """With SMTP_MOCK=true (default), send_summary should succeed."""
        with app.app_context():
            from app.model.entities.admin_user import AdminUser
            admin = AdminUser(username="mockadm", email="mockadm@test.com")
            admin.set_password("x")
            db.session.add(admin)
            db.session.commit()

            make_alert(db, type="service_down", level="critical")

            from app.model.services import notification_service
            result = notification_service.send_summary_emails(actor="test")
            # In mock mode, emails are "sent" (logged), no errors
            assert result["errors"] == 0
            assert result["sent"] >= 1

    def test_send_test_email_mock_mode(self, app, db):
        """send_test_email in mock mode returns success."""
        with app.app_context():
            from app.model.services import notification_service
            ok, msg = notification_service.send_test_email("someone@test.com")
            assert ok is True
            assert "MOCK" in msg or "mock" in msg.lower() or "simulado" in msg.lower()

    # ── HTTP endpoints ───────────────────────────────────────────────────────

    def test_email_diagnostics_endpoint(self, app, db, auth_client):
        resp = auth_client.get(
            "/alertas/email/diagnostico",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "mock" in data
        assert "ready" in data
        assert "pending_alerts" in data

    def test_send_test_email_endpoint(self, app, db, auth_client):
        resp = auth_client.post(
            "/alertas/email/prueba",
            json={"email": "test@example.com"},
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True

    def test_send_summary_endpoint(self, app, db, auth_client):
        with app.app_context():
            make_alert(db, type="service_down", level="critical")
        resp = auth_client.post(
            "/alertas/email/resumen",
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 200
        data = resp.get_json()
        assert data["ok"] is True
        assert "sent" in data
        assert "alerts_notified" in data

    def test_send_test_email_endpoint_empty_email(self, app, db, auth_client):
        """When an explicitly empty email is provided, returns 400."""
        resp = auth_client.post(
            "/alertas/email/prueba",
            json={"email": ""},
            headers={"Accept": "application/json"},
        )
        assert resp.status_code == 400
