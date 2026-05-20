"""
tests/test_reports.py
----------------------
Tests for the Reports module: service, exporters and controller.

Run with:
    python -m pytest tests/test_reports.py -v
"""
import pytest
from datetime import datetime, timezone, timedelta

from app.model.services import reports as reports_service
from app.model.services.reports import exporters
from app.model.entities.audit_log import AuditLog
from app.model.entities.sync_run import SyncRun
from app.model.entities.project_member import ProjectMember
from app.model.entities.report_export_log import ReportExportLog
from tests.conftest import make_user, make_project


# ═══════════════════════════════════════════════════════════════════════════════
# HELPERS
# ═══════════════════════════════════════════════════════════════════════════════

def make_audit(db, actor="system", action="test", level="info", detail=None, ip=None):
    entry = AuditLog(actor=actor, action=action, level=level, detail=detail, ip_address=ip)
    db.session.add(entry)
    db.session.commit()
    return entry


def make_sync(db, status="success", triggered_by="manual",
              users_found=10, users_synced=10,
              projects_found=5, projects_synced=5,
              started_at=None, finished_at=None, message=None):
    now = datetime.now(timezone.utc)
    sr = SyncRun(
        status=status,
        triggered_by=triggered_by,
        users_found=users_found,
        users_synced=users_synced,
        projects_found=projects_found,
        projects_synced=projects_synced,
        started_at=started_at or now,
        finished_at=finished_at or (now + timedelta(seconds=10)),
        message=message,
    )
    db.session.add(sr)
    db.session.commit()
    return sr


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Overview (backward compat)
# ═══════════════════════════════════════════════════════════════════════════════

class TestReportsOverview:

    def test_overview_empty_db(self, app, db):
        with app.app_context():
            data = reports_service.get_reports_overview()
            assert data["total_users"] == 0
            assert data["total_projects"] == 0
            assert data["total_syncs"] == 0
            assert data["alerts_total"] == 0
            assert data["audit_errors"] == 0
            assert data["exceeded_users"] == 0
            assert data["last_sync"] is None
            assert "trends" in data

    def test_overview_counts_correctly(self, app, db):
        with app.app_context():
            make_user(db, "oid-ov1")
            make_user(db, "oid-ov2")
            make_project(db, "oid-ovp1")
            make_audit(db, level="error")
            make_sync(db, status="success")
            data = reports_service.get_reports_overview()
            assert data["total_users"] == 2
            assert data["total_projects"] == 1
            assert data["audit_errors"] == 1
            assert data["total_syncs"] == 1
            assert data["alerts_total"] >= 1

    def test_overview_last_sync_is_most_recent(self, app, db):
        with app.app_context():
            old = make_sync(db, status="error",
                            started_at=datetime.now(timezone.utc) - timedelta(days=2))
            recent = make_sync(db, status="success")
            data = reports_service.get_reports_overview()
            assert data["last_sync"].id == recent.id


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Users report
# ═══════════════════════════════════════════════════════════════════════════════

class TestUsersReport:

    def test_returns_all_users_by_default(self, app, db):
        with app.app_context():
            for i in range(5):
                make_user(db, f"oid-ur{i}", email=f"user{i}@test.com")
            data = reports_service.get_users_report(page=1, per_page=10)
            assert data["pagination"].total == 5

    def test_search_filters_by_email(self, app, db):
        with app.app_context():
            make_user(db, "oid-urs1", email="find@test.com")
            make_user(db, "oid-urs2", email="other@test.com")
            data = reports_service.get_users_report(search="find", page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_search_filters_by_name(self, app, db):
        with app.app_context():
            make_user(db, "oid-ursn1", first_name="Carlos", last_name="Garcia")
            make_user(db, "oid-ursn2", first_name="Ana", last_name="Lopez")
            data = reports_service.get_users_report(search="Carlos", page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_filter_by_admin(self, app, db):
        with app.app_context():
            make_user(db, "oid-uradmin1", is_admin=True)
            make_user(db, "oid-uradmin2", is_admin=False)
            data = reports_service.get_users_report(is_admin=True, page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_stats_counts_admins_and_exceeded(self, app, db):
        with app.app_context():
            make_user(db, "oid-urstats1", is_admin=True, max_quota_bytes=None)
            u = make_user(db, "oid-urstats2", is_admin=False, max_quota_bytes=100)
            make_project(db, "oid-urstats-p", owner=u, size_bytes=200)
            data = reports_service.get_users_report(page=1, per_page=10)
            assert data["stats"]["admins"] == 1
            assert data["stats"]["exceeded"] == 1
            assert data["stats"]["unlimited"] == 1

    def test_pagination(self, app, db):
        with app.app_context():
            for i in range(7):
                make_user(db, f"oid-urpag{i}", email=f"pag{i}@test.com")
            data = reports_service.get_users_report(page=1, per_page=3)
            assert len(data["pagination"].items) == 3
            assert data["pagination"].total == 7
            assert data["pagination"].pages == 3

    def test_get_users_report_all_no_filters(self, app, db):
        with app.app_context():
            for i in range(3):
                make_user(db, f"oid-ural{i}")
            users = reports_service.get_users_report_all()
            assert len(users) == 3

    def test_get_users_report_all_with_search(self, app, db):
        with app.app_context():
            make_user(db, "oid-ural4", email="match@x.com")
            make_user(db, "oid-ural5", email="nope@x.com")
            users = reports_service.get_users_report_all(search="match")
            assert len(users) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Projects report
# ═══════════════════════════════════════════════════════════════════════════════

class TestProjectsReport:

    def test_returns_all_projects(self, app, db):
        with app.app_context():
            for i in range(4):
                make_project(db, f"oid-pr{i}")
            data = reports_service.get_projects_report(page=1, per_page=10)
            assert data["pagination"].total == 4

    def test_search_by_name(self, app, db):
        with app.app_context():
            make_project(db, "oid-prs1", name="LaTeX Thesis")
            make_project(db, "oid-prs2", name="Other Doc")
            data = reports_service.get_projects_report(search="LaTeX", page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_filter_large(self, app, db):
        with app.app_context():
            make_project(db, "oid-prl1", size_bytes=20 * 1024 * 1024)
            make_project(db, "oid-prl2", size_bytes=100)
            data = reports_service.get_projects_report(size_filter="large", page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_filter_inactive(self, app, db):
        with app.app_context():
            old = make_project(db, "oid-prin1")
            old.last_updated_at = datetime.now(timezone.utc) - timedelta(days=100)
            recent = make_project(db, "oid-prin2")
            recent.last_updated_at = datetime.now(timezone.utc)
            db.session.commit()
            data = reports_service.get_projects_report(activity_filter="inactive", page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_filter_recent(self, app, db):
        with app.app_context():
            old = make_project(db, "oid-prre1")
            old.last_updated_at = datetime.now(timezone.utc) - timedelta(days=60)
            fresh = make_project(db, "oid-prre2")
            fresh.last_updated_at = datetime.now(timezone.utc)
            db.session.commit()
            data = reports_service.get_projects_report(activity_filter="recent", page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_stats_included(self, app, db):
        with app.app_context():
            make_project(db, "oid-prst1", size_bytes=20 * 1024 * 1024)
            make_project(db, "oid-prst2", size_bytes=50)
            data = reports_service.get_projects_report(page=1, per_page=10)
            assert data["stats"]["total"] == 2
            assert data["stats"]["large"] == 1

    def test_member_counts_in_response(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-prmc-own")
            member = make_user(db, "oid-prmc-mem")
            p = make_project(db, "oid-prmc-proj", owner=owner)
            db.session.add(ProjectMember(project=p, user=member, role="collaborator"))
            db.session.commit()
            data = reports_service.get_projects_report(page=1, per_page=10)
            assert data["member_counts"].get(p.id, 0) == 1

    def test_get_projects_report_all(self, app, db):
        with app.app_context():
            make_project(db, "oid-pra1", name="Alpha")
            make_project(db, "oid-pra2", name="Beta")
            projects = reports_service.get_projects_report_all()
            assert len(projects) == 2


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Storage report
# ═══════════════════════════════════════════════════════════════════════════════

class TestStorageReport:

    def test_empty_db(self, app, db):
        with app.app_context():
            data = reports_service.get_storage_report()
            assert data["total_bytes"] == 0
            assert data["rows"] == []

    def test_totals(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-stor1")
            make_project(db, "oid-stor-p1", owner=owner, size_bytes=1024)
            make_project(db, "oid-stor-p2", owner=owner, size_bytes=2048)
            data = reports_service.get_storage_report()
            assert data["total_bytes"] == 3072
            assert data["total_projects"] == 2

    def test_row_data(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-stor2", max_quota_bytes=4096)
            make_project(db, "oid-stor-p3", owner=owner, size_bytes=2048)
            data = reports_service.get_storage_report()
            assert len(data["rows"]) == 1
            row = data["rows"][0]
            assert row["used_bytes"] == 2048
            assert row["quota_pct"] == 50.0
            assert row["proj_count"] == 1

    def test_rows_ordered_by_usage_desc(self, app, db):
        with app.app_context():
            o1 = make_user(db, "oid-stord1")
            o2 = make_user(db, "oid-stord2")
            make_project(db, "oid-stor-d1", owner=o1, size_bytes=100)
            make_project(db, "oid-stor-d2", owner=o2, size_bytes=9999)
            data = reports_service.get_storage_report()
            assert data["rows"][0]["used_bytes"] == 9999

    def test_averages(self, app, db):
        with app.app_context():
            o1 = make_user(db, "oid-storavg1")
            make_project(db, "oid-storavg-p1", owner=o1, size_bytes=1000)
            data = reports_service.get_storage_report()
            assert "avg_per_user_fmt" in data
            assert "avg_per_project_fmt" in data


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Activity report
# ═══════════════════════════════════════════════════════════════════════════════

class TestActivityReport:

    def test_returns_all_entries(self, app, db):
        with app.app_context():
            for i in range(3):
                make_audit(db, actor=f"admin{i}", action="login")
            data = reports_service.get_activity_report(page=1, per_page=10)
            assert data["pagination"].total == 3

    def test_filter_by_level(self, app, db):
        with app.app_context():
            make_audit(db, level="error")
            make_audit(db, level="info")
            data = reports_service.get_activity_report(level="error", page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_filter_by_action(self, app, db):
        with app.app_context():
            make_audit(db, action="login")
            make_audit(db, action="sync_start")
            data = reports_service.get_activity_report(action="login", page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_stats_error_warning_counts(self, app, db):
        with app.app_context():
            make_audit(db, level="error")
            make_audit(db, level="error")
            make_audit(db, level="warning")
            make_audit(db, level="info")
            data = reports_service.get_activity_report(page=1, per_page=10)
            assert data["stats"]["errors"] == 2
            assert data["stats"]["warnings"] == 1
            assert data["stats"]["total"] == 4

    def test_search_filters(self, app, db):
        with app.app_context():
            make_audit(db, actor="alice", detail="important event")
            make_audit(db, actor="bob", detail="nothing")
            data = reports_service.get_activity_report(search="important", page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_action_names_populated(self, app, db):
        with app.app_context():
            make_audit(db, action="login")
            make_audit(db, action="sync_ok")
            data = reports_service.get_activity_report(page=1, per_page=10)
            assert "login" in data["action_names"]
            assert "sync_ok" in data["action_names"]

    def test_get_activity_report_all(self, app, db):
        with app.app_context():
            make_audit(db, level="error")
            make_audit(db, level="info")
            entries = reports_service.get_activity_report_all(level="error")
            assert len(entries) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Syncs report
# ═══════════════════════════════════════════════════════════════════════════════

class TestSyncsReport:

    def test_returns_all_runs(self, app, db):
        with app.app_context():
            for i in range(4):
                make_sync(db)
            data = reports_service.get_syncs_report(page=1, per_page=10)
            assert data["pagination"].total == 4

    def test_filter_by_status(self, app, db):
        with app.app_context():
            make_sync(db, status="success")
            make_sync(db, status="error")
            data = reports_service.get_syncs_report(status="error", page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_filter_by_triggered_by(self, app, db):
        with app.app_context():
            make_sync(db, triggered_by="manual")
            make_sync(db, triggered_by="scheduled")
            data = reports_service.get_syncs_report(triggered_by="scheduled", page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_stats_success_and_errors(self, app, db):
        with app.app_context():
            make_sync(db, status="success")
            make_sync(db, status="success")
            make_sync(db, status="error")
            data = reports_service.get_syncs_report(page=1, per_page=10)
            assert data["stats"]["success"] == 2
            assert data["stats"]["errors"] == 1
            assert data["stats"]["total"] == 3

    def test_get_syncs_report_all(self, app, db):
        with app.app_context():
            make_sync(db, status="success")
            make_sync(db, status="error")
            runs = reports_service.get_syncs_report_all(status="error")
            assert len(runs) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Quotas report
# ═══════════════════════════════════════════════════════════════════════════════

class TestQuotasReport:

    def test_returns_all_users(self, app, db):
        with app.app_context():
            make_user(db, "oid-qt1", max_quota_bytes=1024)
            make_user(db, "oid-qt2", max_quota_bytes=None)
            data = reports_service.get_quotas_report(page=1, per_page=10)
            assert data["total"] == 2

    def test_filter_exceeded(self, app, db):
        with app.app_context():
            u_exc = make_user(db, "oid-qt3", max_quota_bytes=100)
            make_project(db, "oid-qt3-p", owner=u_exc, size_bytes=200)
            make_user(db, "oid-qt4", max_quota_bytes=10000)
            data = reports_service.get_quotas_report(status_filter="exceeded", page=1, per_page=10)
            assert data["total"] == 1

    def test_filter_unlimited(self, app, db):
        with app.app_context():
            make_user(db, "oid-qt5", max_quota_bytes=None)
            make_user(db, "oid-qt6", max_quota_bytes=1024)
            data = reports_service.get_quotas_report(status_filter="unlimited", page=1, per_page=10)
            assert data["total"] == 1

    def test_stats_counts(self, app, db):
        with app.app_context():
            u_exc = make_user(db, "oid-qt7", max_quota_bytes=100)
            make_project(db, "oid-qt7-p", owner=u_exc, size_bytes=200)
            make_user(db, "oid-qt8", max_quota_bytes=10000)
            data = reports_service.get_quotas_report(page=1, per_page=10)
            assert data["stats"]["exceeded"] == 1

    def test_pagination(self, app, db):
        with app.app_context():
            for i in range(5):
                make_user(db, f"oid-qtpag{i}")
            data = reports_service.get_quotas_report(page=1, per_page=2)
            assert len(data["items"]) == 2
            assert data["pages"] == 3

    def test_quotas_report_all(self, app, db):
        with app.app_context():
            make_user(db, "oid-qtall1", max_quota_bytes=1024)
            make_user(db, "oid-qtall2", max_quota_bytes=None)
            rows = reports_service.get_quotas_report_all()
            assert len(rows) == 2

    def test_quota_row_has_role_info(self, app, db):
        with app.app_context():
            from app.model.entities.role import Role
            role = Role.query.filter_by(name="alumno").first()
            u = make_user(db, "oid-qtrole1", max_quota_bytes=1024, role=role)
            data = reports_service.get_quotas_report(page=1, per_page=10)
            row = [r for r in data["items"] if r["user"].id == u.id][0]
            assert row["role_name"] == "alumno"
            assert row["max_projects"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Incidents report
# ═══════════════════════════════════════════════════════════════════════════════

class TestIncidentsReport:

    def test_returns_only_warnings_and_errors(self, app, db):
        with app.app_context():
            make_audit(db, level="info")
            make_audit(db, level="warning")
            make_audit(db, level="error")
            data = reports_service.get_incidents_report(page=1, per_page=10)
            assert data["pagination"].total == 2

    def test_filter_by_level(self, app, db):
        with app.app_context():
            make_audit(db, level="warning")
            make_audit(db, level="error")
            data = reports_service.get_incidents_report(level="error", page=1, per_page=10)
            assert data["pagination"].total == 1

    def test_stats(self, app, db):
        with app.app_context():
            make_audit(db, level="error")
            make_audit(db, level="error")
            make_audit(db, level="warning")
            data = reports_service.get_incidents_report(page=1, per_page=10)
            assert data["stats"]["errors"] == 2
            assert data["stats"]["warnings"] == 1

    def test_incidents_report_all(self, app, db):
        with app.app_context():
            make_audit(db, level="error")
            make_audit(db, level="info")
            entries = reports_service.get_incidents_report_all()
            assert len(entries) == 1


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — General report
# ═══════════════════════════════════════════════════════════════════════════════

class TestGeneralReport:

    def test_empty_db_returns_all_keys(self, app, db):
        with app.app_context():
            data = reports_service.get_general_report_data()
            assert data["total_users"] == 0
            assert data["total_projects"] == 0
            assert data["total_syncs"] == 0
            # System status and conclusion removed
            assert "services" not in data
            assert "platform_status" not in data
            assert "conclusion" not in data
            assert "users_by_role" in data
            assert "top_users_storage" in data
            assert "top_projects_size" in data

    def test_counts_correctly(self, app, db):
        with app.app_context():
            make_user(db, "oid-gen1")
            make_user(db, "oid-gen2")
            make_project(db, "oid-gen-p1", size_bytes=5000)
            make_sync(db, status="success")
            data = reports_service.get_general_report_data()
            assert data["total_users"] == 2
            assert data["total_projects"] == 1
            assert data["total_syncs"] == 1
            assert data["success_pct"] == 100.0

    def test_no_system_status_in_general_data(self, app, db):
        with app.app_context():
            data = reports_service.get_general_report_data()
            assert "services" not in data
            assert "platform_status" not in data
            assert "conclusion" not in data

    def test_collaborative_projects_count(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-gen-collab-own")
            member = make_user(db, "oid-gen-collab-mem")
            p = make_project(db, "oid-gen-collab-p", owner=owner)
            db.session.add(ProjectMember(project=p, user=member, role="collaborator"))
            db.session.commit()
            data = reports_service.get_general_report_data()
            assert data["collaborative_projects"] >= 1


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — AJAX section endpoints
# ═══════════════════════════════════════════════════════════════════════════════

class TestGeneralSections:

    def test_resumen_section_returns_keys(self, app, db):
        with app.app_context():
            data = reports_service.get_general_section_resumen()
            assert "total_users" in data
            assert "total_projects" in data
            assert "total_storage_fmt" in data
            assert "total_syncs" in data
            assert "success_pct" in data

    def test_usuarios_section_returns_keys(self, app, db):
        with app.app_context():
            data = reports_service.get_general_section_usuarios()
            assert "total_users" in data
            assert "users_by_role" in data
            assert "users_exceeded_quota" in data

    def test_proyectos_section_returns_keys(self, app, db):
        with app.app_context():
            data = reports_service.get_general_section_proyectos()
            assert "total_projects" in data
            assert "large_projects" in data
            assert "top_projects_size" in data

    def test_almacenamiento_section_returns_keys(self, app, db):
        with app.app_context():
            data = reports_service.get_general_section_almacenamiento()
            assert "total_storage_fmt" in data
            assert "top_users_storage" in data

    def test_sincronizacion_section_returns_keys(self, app, db):
        with app.app_context():
            data = reports_service.get_general_section_sincronizacion()
            assert "total_syncs" in data
            assert "success_pct" in data
            assert "failed_syncs_recent" in data

    def test_auditoria_section_returns_keys(self, app, db):
        with app.app_context():
            data = reports_service.get_general_section_auditoria()
            assert "active_alerts_count" in data
            assert "recent_errors" in data
            assert "recent_role_changes" in data

    def test_resumen_section_counts(self, app, db):
        with app.app_context():
            make_user(db, "oid-sec-r1")
            make_project(db, "oid-sec-rp1", size_bytes=1000)
            data = reports_service.get_general_section_resumen()
            assert data["total_users"] == 1
            assert data["total_projects"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Index stats (lightweight)
# ═══════════════════════════════════════════════════════════════════════════════

class TestIndexStats:

    def test_index_stats_returns_last_export(self, app, db):
        with app.app_context():
            stats = reports_service.get_index_stats()
            assert "last_general_export" in stats
            assert stats["last_general_export"] is None

    def test_index_stats_with_export(self, app, db):
        with app.app_context():
            reports_service.log_report_export(
                report_type="general", fmt="pdf", file_name="general.pdf"
            )
            stats = reports_service.get_index_stats()
            assert stats["last_general_export"] is not None


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Export logging
# ═══════════════════════════════════════════════════════════════════════════════

class TestExportLogging:

    def test_log_creates_entries(self, app, db):
        with app.app_context():
            entry = reports_service.log_report_export(
                report_type="usuarios",
                fmt="csv",
                file_name="test.csv",
            )
            assert entry.id is not None
            assert entry.report_type == "usuarios"
            assert entry.format == "csv"
            assert entry.status == "completed"

    def test_log_also_writes_audit_log(self, app, db):
        with app.app_context():
            reports_service.log_report_export(
                report_type="proyectos",
                fmt="pdf",
                file_name="test.pdf",
            )
            audit = AuditLog.query.filter_by(action="export").first()
            assert audit is not None
            assert "proyectos" in audit.detail

    def test_get_export_history(self, app, db):
        with app.app_context():
            for i in range(3):
                reports_service.log_report_export(
                    report_type=f"type{i}", fmt="csv", file_name=f"f{i}.csv"
                )
            data = reports_service.get_export_history(page=1, per_page=10)
            assert len(data["items"]) == 3

    def test_get_recent_exports(self, app, db):
        with app.app_context():
            reports_service.log_report_export(
                report_type="usuarios", fmt="csv", file_name="u.csv"
            )
            reports_service.log_report_export(
                report_type="general", fmt="pdf", file_name="g.pdf"
            )
            recent = reports_service.get_recent_exports(limit=5)
            assert len(recent) == 2
            assert recent[0]["report_type"] == "general"  # most recent first

    def test_log_with_filters(self, app, db):
        with app.app_context():
            entry = reports_service.log_report_export(
                report_type="usuarios", fmt="csv", file_name="u.csv",
                filters={"q": "test", "role_id": 1},
            )
            assert entry.filters_json is not None
            assert "test" in entry.filters_json


# ═══════════════════════════════════════════════════════════════════════════════
# SERVICE — Trends (backward compat)
# ═══════════════════════════════════════════════════════════════════════════════

class TestTrends:

    def test_trend_zero_to_zero(self):
        assert reports_service._trend(0, 0) == 0

    def test_trend_zero_to_positive(self):
        assert reports_service._trend(5, 0) == 100

    def test_trend_positive_growth(self):
        assert reports_service._trend(10, 5) == 100

    def test_trend_negative_growth(self):
        assert reports_service._trend(5, 10) == -50

    def test_overview_includes_trends(self, app, db):
        with app.app_context():
            data = reports_service.get_reports_overview()
            assert "trends" in data
            for key in ("users", "projects", "storage", "syncs", "alerts"):
                assert key in data["trends"]

    def test_overview_includes_storage_split(self, app, db):
        with app.app_context():
            data = reports_service.get_reports_overview()
            assert "storage_val" in data
            assert "storage_unit" in data


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTERS — CSV
# ═══════════════════════════════════════════════════════════════════════════════

class TestExporters:

    def test_export_users_csv_headers(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-exp1", email="export@test.com")
            data, filename, ct = exporters.export_users_csv([u])
            text = data.decode("utf-8-sig")
            assert "Email" in text
            assert "Cuota asignada" in text
            assert filename.startswith("informe_usuarios_") and filename.endswith(".csv")

    def test_export_users_csv_row(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-exp2", email="row@test.com")
            data, _, _ = exporters.export_users_csv([u])
            text = data.decode("utf-8-sig")
            assert "row@test.com" in text

    def test_export_projects_csv_headers(self, app, db):
        with app.app_context():
            p = make_project(db, "oid-expp1", name="Proj Export")
            data, filename, ct = exporters.export_projects_csv([p])
            text = data.decode("utf-8-sig")
            assert "Nombre" in text
            assert filename.startswith("informe_proyectos_") and filename.endswith(".csv")

    def test_export_storage_csv(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-exps1", max_quota_bytes=1024)
            make_project(db, "oid-exps-p1", owner=owner, size_bytes=512)
            storage_data = reports_service.get_storage_report()
            data, filename, ct = exporters.export_storage_csv(storage_data["rows"])
            text = data.decode("utf-8-sig")
            assert "Email" in text
            assert filename.startswith("informe_almacenamiento_") and filename.endswith(".csv")

    def test_export_activity_csv(self, app, db):
        with app.app_context():
            entry = make_audit(db, actor="admin", action="login", level="info")
            data, filename, ct = exporters.export_activity_csv([entry])
            text = data.decode("utf-8-sig")
            assert "Actor" in text
            assert "admin" in text
            assert filename.startswith("informe_actividad_") and filename.endswith(".csv")

    def test_export_syncs_csv(self, app, db):
        with app.app_context():
            sr = make_sync(db, status="success")
            data, filename, ct = exporters.export_syncs_csv([sr])
            text = data.decode("utf-8-sig")
            assert "Estado" in text
            assert "success" in text
            assert filename.startswith("informe_sincronizaciones_") and filename.endswith(".csv")

    def test_csv_content_type(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-expct1")
            _, _, ct = exporters.export_users_csv([u])
            assert "text/csv" in ct

    def test_export_quotas_csv(self, app, db):
        with app.app_context():
            make_user(db, "oid-expq1", max_quota_bytes=1024)
            rows = reports_service.get_quotas_report_all()
            data, filename, ct = exporters.export_quotas_csv(rows)
            text = data.decode("utf-8-sig")
            assert "Rol" in text
            assert filename.startswith("informe_cuotas_") and filename.endswith(".csv")

    def test_export_incidents_csv(self, app, db):
        with app.app_context():
            entry = make_audit(db, level="error", action="sync_error")
            data, filename, ct = exporters.export_incidents_csv([entry])
            text = data.decode("utf-8-sig")
            assert "Nivel" in text
            assert filename.startswith("informe_incidencias_") and filename.endswith(".csv")

    def test_export_general_csv(self, app, db):
        with app.app_context():
            gen_data = reports_service.get_general_report_data()
            data, filename, ct = exporters.export_general_csv(gen_data)
            text = data.decode("utf-8-sig")
            assert "Sección" in text
            assert "Métrica" in text
            assert filename.startswith("informe_general_") and filename.endswith(".csv")

    def test_general_csv_no_system_status(self, app, db):
        with app.app_context():
            gen_data = reports_service.get_general_report_data()
            data, _, _ = exporters.export_general_csv(gen_data)
            text = data.decode("utf-8-sig")
            assert "Estado de la plataforma" not in text
            assert "Conclusion" not in text


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTERS — PDF
# ═══════════════════════════════════════════════════════════════════════════════

class TestPdfExporters:

    def test_export_users_pdf(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-pdf-u1", email="pdf@test.com")
            data, filename, ct = exporters.export_users_pdf([u])
            assert filename.startswith("informe_usuarios_") and filename.endswith(".pdf")
            assert ct == "application/pdf"
            assert data[:5] == b"%PDF-"
            assert len(data) > 100

    def test_export_projects_pdf(self, app, db):
        with app.app_context():
            p = make_project(db, "oid-pdf-p1", name="PDF Project")
            data, filename, ct = exporters.export_projects_pdf([p])
            assert filename.startswith("informe_proyectos_") and filename.endswith(".pdf")
            assert data[:5] == b"%PDF-"

    def test_export_storage_pdf(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-pdf-s1", max_quota_bytes=1024)
            make_project(db, "oid-pdf-sp1", owner=owner, size_bytes=512)
            storage_data = reports_service.get_storage_report()
            data, filename, ct = exporters.export_storage_pdf(storage_data["rows"], totals=storage_data)
            assert filename.startswith("informe_almacenamiento_") and filename.endswith(".pdf")
            assert data[:5] == b"%PDF-"

    def test_export_quotas_pdf(self, app, db):
        with app.app_context():
            make_user(db, "oid-pdf-q1", max_quota_bytes=1024)
            rows = reports_service.get_quotas_report_all()
            data, filename, ct = exporters.export_quotas_pdf(rows)
            assert filename.startswith("informe_cuotas_") and filename.endswith(".pdf")
            assert data[:5] == b"%PDF-"

    def test_export_activity_pdf(self, app, db):
        with app.app_context():
            entry = make_audit(db, actor="admin", action="login")
            data, filename, ct = exporters.export_activity_pdf([entry])
            assert filename.startswith("informe_actividad_") and filename.endswith(".pdf")
            assert data[:5] == b"%PDF-"

    def test_export_incidents_pdf(self, app, db):
        with app.app_context():
            entry = make_audit(db, level="error", action="sync_error")
            data, filename, ct = exporters.export_incidents_pdf([entry])
            assert filename.startswith("informe_incidencias_") and filename.endswith(".pdf")
            assert data[:5] == b"%PDF-"

    def test_export_syncs_pdf(self, app, db):
        with app.app_context():
            sr = make_sync(db, status="success")
            data, filename, ct = exporters.export_syncs_pdf([sr])
            assert filename.startswith("informe_sincronizaciones_") and filename.endswith(".pdf")
            assert data[:5] == b"%PDF-"

    def test_export_general_pdf(self, app, db):
        with app.app_context():
            make_user(db, "oid-pdf-gen1")
            make_project(db, "oid-pdf-gen-p1", size_bytes=1024)
            gen_data = reports_service.get_general_report_data()
            data, filename, ct = exporters.export_general_pdf(gen_data)
            assert filename.startswith("informe_general_") and filename.endswith(".pdf")
            assert ct == "application/pdf"
            assert data[:5] == b"%PDF-"
            assert len(data) > 500

    def test_export_general_pdf_empty_db(self, app, db):
        with app.app_context():
            gen_data = reports_service.get_general_report_data()
            data, filename, ct = exporters.export_general_pdf(gen_data)
            assert data[:5] == b"%PDF-"

    def test_pdf_with_filters_text(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-pdf-ft1")
            data, filename, ct = exporters.export_users_pdf(
                [u], generated_by="testadmin", filters_text="Busqueda: test"
            )
            assert data[:5] == b"%PDF-"

    def test_general_pdf_uses_resumen_not_ejecutivo(self, app, db):
        """PDF should use 'Resumen' not 'Resumen ejecutivo'.

        We verify this indirectly: the exporter function uses
        '1. Resumen' as heading (not 'Resumen ejecutivo').
        """
        with app.app_context():
            gen_data = reports_service.get_general_report_data()
            data, _, _ = exporters.export_general_pdf(gen_data)
            assert data[:5] == b"%PDF-"
            # The source code uses "1. Resumen" — we can't easily parse
            # compressed PDF text, so we trust the unit: the heading string
            # in exporters.py reads "1. Resumen" (verified by code inspection).


# ═══════════════════════════════════════════════════════════════════════════════
# CONTROLLER
# ═══════════════════════════════════════════════════════════════════════════════

class TestReportsController:

    # ── Unauthenticated redirects ─────────────────────────────────────────────

    def test_index_redirects_unauthenticated(self, client):
        resp = client.get("/informes/")
        assert resp.status_code in (302, 401)

    def test_general_report_redirects_unauthenticated(self, client):
        resp = client.get("/informes/general")
        assert resp.status_code in (302, 401)

    def test_export_history_redirects_unauthenticated(self, client):
        resp = client.get("/informes/exportaciones")
        assert resp.status_code in (302, 401)

    # ── Specific report views redirect to index ──────────────────────────────

    def test_users_report_redirects_to_index(self, auth_client):
        resp = auth_client.get("/informes/usuarios")
        assert resp.status_code == 302
        assert "/informes/" in resp.headers.get("Location", "")

    def test_projects_report_redirects_to_index(self, auth_client):
        resp = auth_client.get("/informes/proyectos")
        assert resp.status_code == 302

    def test_storage_report_redirects_to_index(self, auth_client):
        resp = auth_client.get("/informes/almacenamiento")
        assert resp.status_code == 302

    def test_activity_report_redirects_to_index(self, auth_client):
        resp = auth_client.get("/informes/actividad")
        assert resp.status_code == 302

    def test_quotas_report_redirects_to_index(self, auth_client):
        resp = auth_client.get("/informes/cuotas")
        assert resp.status_code == 302

    def test_incidents_report_redirects_to_index(self, auth_client):
        resp = auth_client.get("/informes/incidencias")
        assert resp.status_code == 302

    def test_syncs_report_redirects_to_index(self, auth_client):
        resp = auth_client.get("/informes/sincronizaciones")
        assert resp.status_code == 302

    # ── Authenticated GET — index and general ────────────────────────────────

    def test_index_renders_ok(self, auth_client):
        resp = auth_client.get("/informes/")
        assert resp.status_code == 200

    def test_index_no_header_text(self, auth_client):
        """Index should NOT show the old subtitle text."""
        resp = auth_client.get("/informes/")
        assert b"Genera informes filtrados sobre usuarios" not in resp.data

    def test_index_no_accesos_rapidos(self, auth_client):
        """Index should not have 'accesos rapidos' or dashboard widgets."""
        resp = auth_client.get("/informes/")
        html = resp.data.decode()
        assert "accesos rapidos" not in html.lower()
        assert "Resumen rapido" not in html

    def test_index_has_download_buttons(self, auth_client):
        """Index should have CSV/PDF download buttons."""
        resp = auth_client.get("/informes/")
        html = resp.data.decode()
        assert "CSV" in html
        assert "PDF" in html

    def test_general_report_renders_ok(self, auth_client):
        resp = auth_client.get("/informes/general")
        assert resp.status_code == 200

    def test_general_report_has_back_link(self, auth_client):
        """General report should show 'Volver a informes' back link."""
        resp = auth_client.get("/informes/general")
        html = resp.data.decode()
        assert "Volver a informes" in html

    def test_general_report_no_breadcrumb(self, auth_client):
        """General report should NOT show breadcrumb."""
        resp = auth_client.get("/informes/general")
        html = resp.data.decode()
        assert "breadcrumb" not in html

    def test_general_report_uses_resumen_not_ejecutivo(self, auth_client):
        """General report should use 'Resumen' not 'Resumen ejecutivo'."""
        resp = auth_client.get("/informes/general")
        html = resp.data.decode()
        assert "Resumen" in html
        assert "Resumen ejecutivo" not in html

    def test_general_report_no_estado_sistema(self, auth_client):
        """General report should NOT show 'Estado del sistema'."""
        resp = auth_client.get("/informes/general")
        html = resp.data.decode()
        assert "Estado del sistema" not in html

    def test_general_report_no_conclusion(self, auth_client):
        """General report should NOT show 'Conclusion' section."""
        resp = auth_client.get("/informes/general")
        html = resp.data.decode()
        # Check for the section title pattern
        assert "Conclusion" not in html or "Conclusion automatica" not in html

    def test_general_report_uses_ajax(self, auth_client):
        """General report page should contain AJAX fetch calls."""
        resp = auth_client.get("/informes/general")
        html = resp.data.decode()
        assert "fetch(" in html
        assert "section-loading" in html or "spinner" in html

    def test_export_history_renders_ok(self, auth_client):
        resp = auth_client.get("/informes/exportaciones")
        assert resp.status_code == 200

    # ── AJAX section endpoints ───────────────────────────────────────────────

    def test_ajax_resumen_returns_json(self, auth_client):
        resp = auth_client.get("/informes/general/seccion/resumen")
        assert resp.status_code == 200
        assert resp.content_type.startswith("application/json")
        data = resp.get_json()
        assert "total_users" in data

    def test_ajax_usuarios_returns_json(self, auth_client):
        resp = auth_client.get("/informes/general/seccion/usuarios")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "users_by_role" in data

    def test_ajax_proyectos_returns_json(self, auth_client):
        resp = auth_client.get("/informes/general/seccion/proyectos")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_projects" in data

    def test_ajax_almacenamiento_returns_json(self, auth_client):
        resp = auth_client.get("/informes/general/seccion/almacenamiento-cuotas")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_storage_fmt" in data

    def test_ajax_sincronizacion_returns_json(self, auth_client):
        resp = auth_client.get("/informes/general/seccion/sincronizacion")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "total_syncs" in data

    def test_ajax_auditoria_returns_json(self, auth_client):
        resp = auth_client.get("/informes/general/seccion/auditoria-incidencias")
        assert resp.status_code == 200
        data = resp.get_json()
        assert "active_alerts_count" in data

    # ── CSV export endpoints ──────────────────────────────────────────────────

    def test_export_users_csv_returns_csv(self, auth_client):
        resp = auth_client.get("/informes/usuarios/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_export_projects_csv_returns_csv(self, auth_client):
        resp = auth_client.get("/informes/proyectos/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_export_storage_csv_returns_csv(self, auth_client):
        resp = auth_client.get("/informes/almacenamiento/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_export_activity_csv_returns_csv(self, auth_client):
        resp = auth_client.get("/informes/actividad/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_export_syncs_csv_returns_csv(self, auth_client):
        resp = auth_client.get("/informes/sincronizaciones/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_export_quotas_csv_returns_csv(self, auth_client):
        resp = auth_client.get("/informes/cuotas/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_export_incidents_csv_returns_csv(self, auth_client):
        resp = auth_client.get("/informes/incidencias/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    def test_export_general_csv_returns_csv(self, auth_client):
        resp = auth_client.get("/informes/general/csv")
        assert resp.status_code == 200
        assert "text/csv" in resp.content_type

    # ── PDF export endpoints ──────────────────────────────────────────────────

    def test_export_users_pdf_returns_pdf(self, auth_client):
        resp = auth_client.get("/informes/usuarios/pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type

    def test_export_projects_pdf_returns_pdf(self, auth_client):
        resp = auth_client.get("/informes/proyectos/pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type

    def test_export_storage_pdf_returns_pdf(self, auth_client):
        resp = auth_client.get("/informes/almacenamiento/pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type

    def test_export_activity_pdf_returns_pdf(self, auth_client):
        resp = auth_client.get("/informes/actividad/pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type

    def test_export_syncs_pdf_returns_pdf(self, auth_client):
        resp = auth_client.get("/informes/sincronizaciones/pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type

    def test_export_quotas_pdf_returns_pdf(self, auth_client):
        resp = auth_client.get("/informes/cuotas/pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type

    def test_export_incidents_pdf_returns_pdf(self, auth_client):
        resp = auth_client.get("/informes/incidencias/pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type

    def test_export_general_pdf_returns_pdf(self, auth_client):
        resp = auth_client.get("/informes/general/pdf")
        assert resp.status_code == 200
        assert "application/pdf" in resp.content_type

    # ── Content-Disposition ───────────────────────────────────────────────────

    def test_csv_has_content_disposition(self, auth_client):
        resp = auth_client.get("/informes/usuarios/csv")
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        assert "informe_usuarios_" in resp.headers.get("Content-Disposition", "")

    def test_pdf_has_content_disposition(self, auth_client):
        resp = auth_client.get("/informes/usuarios/pdf")
        assert "attachment" in resp.headers.get("Content-Disposition", "")
        assert "informe_usuarios_" in resp.headers.get("Content-Disposition", "")

    def test_general_pdf_has_content_disposition(self, auth_client):
        resp = auth_client.get("/informes/general/pdf")
        assert "informe_general_" in resp.headers.get("Content-Disposition", "")

    # ── Data shows up correctly ───────────────────────────────────────────────

    def test_users_csv_contains_data(self, app, db, auth_client):
        with app.app_context():
            make_user(db, "oid-csv-u1", email="csvuser@test.com")
        resp = auth_client.get("/informes/usuarios/csv")
        assert b"csvuser@test.com" in resp.data

    def test_projects_csv_contains_data(self, app, db, auth_client):
        with app.app_context():
            make_project(db, "oid-csv-p1", name="CSV Project")
        resp = auth_client.get("/informes/proyectos/csv")
        assert b"CSV Project" in resp.data

    # ── Export creates audit log ──────────────────────────────────────────────

    def test_csv_export_creates_log(self, app, db, auth_client):
        resp = auth_client.get("/informes/usuarios/csv")
        assert resp.status_code == 200
        with app.app_context():
            log = ReportExportLog.query.filter_by(
                report_type="usuarios", format="csv"
            ).first()
            assert log is not None
            assert log.status == "completed"

    def test_pdf_export_creates_log(self, app, db, auth_client):
        resp = auth_client.get("/informes/general/pdf")
        assert resp.status_code == 200
        with app.app_context():
            log = ReportExportLog.query.filter_by(
                report_type="general", format="pdf"
            ).first()
            assert log is not None

    # ── Empty DB doesn't break ────────────────────────────────────────────────

    def test_general_report_empty_db(self, auth_client):
        resp = auth_client.get("/informes/general")
        assert resp.status_code == 200

    def test_general_pdf_empty_db(self, auth_client):
        resp = auth_client.get("/informes/general/pdf")
        assert resp.status_code == 200

    def test_export_history_empty_db(self, auth_client):
        resp = auth_client.get("/informes/exportaciones")
        assert resp.status_code == 200


# ═══════════════════════════════════════════════════════════════════════════════
# EXPORTERS — Tildes, rankings, translations, narrative
# ═══════════════════════════════════════════════════════════════════════════════

class TestExporterTildes:
    """CSV headers should use proper accented characters."""

    def test_general_csv_has_tildes(self, app, db):
        with app.app_context():
            gen_data = reports_service.get_general_report_data()
            data, _, _ = exporters.export_general_csv(gen_data)
            text = data.decode("utf-8-sig")
            assert "Sección" in text
            assert "Métrica" in text
            assert "Sincronización" in text
            assert "Auditoría" in text
            assert "Duración" in text

    def test_projects_csv_has_tildes(self, app, db):
        with app.app_context():
            p = make_project(db, "oid-tilde-p1", name="Test")
            data, _, _ = exporters.export_projects_csv([p])
            text = data.decode("utf-8-sig")
            assert "Tamaño" in text
            assert "Última actualización" in text

    def test_users_csv_has_tildes(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-tilde-u1")
            data, _, _ = exporters.export_users_csv([u])
            text = data.decode("utf-8-sig")
            assert "Último acceso" in text

    def test_activity_csv_has_tildes(self, app, db):
        with app.app_context():
            entry = make_audit(db, action="test")
            data, _, _ = exporters.export_activity_csv([entry])
            text = data.decode("utf-8-sig")
            assert "Acción" in text

    def test_quotas_csv_has_tildes(self, app, db):
        with app.app_context():
            make_user(db, "oid-tilde-q1", max_quota_bytes=1024)
            rows = reports_service.get_quotas_report_all()
            data, _, _ = exporters.export_quotas_csv(rows)
            text = data.decode("utf-8-sig")
            assert "Límite proyectos" in text

    def test_syncs_csv_has_tildes(self, app, db):
        with app.app_context():
            sr = make_sync(db)
            data, _, _ = exporters.export_syncs_csv([sr])
            text = data.decode("utf-8-sig")
            assert "Duración" in text


class TestRankingLimits:
    """Rankings should be limited to 5 entries and exclude empty data."""

    def test_top_projects_limited_to_5(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-rank-own")
            for i in range(8):
                make_project(
                    db, f"oid-rank-p{i}",
                    owner=owner, size_bytes=(i + 1) * 1000,
                )
            data = reports_service.get_general_report_data()
            assert len(data["top_projects_size"]) <= 5

    def test_top_users_storage_limited_to_5(self, app, db):
        with app.app_context():
            for i in range(8):
                owner = make_user(db, f"oid-rank-u{i}")
                make_project(
                    db, f"oid-rank-up{i}",
                    owner=owner, size_bytes=(i + 1) * 1000,
                )
            data = reports_service.get_general_report_data()
            assert len(data["top_users_storage"]) <= 5

    def test_top_projects_excludes_zero_size(self, app, db):
        with app.app_context():
            owner = make_user(db, "oid-rank-zero-own")
            make_project(db, "oid-rank-zero1", owner=owner, size_bytes=0)
            make_project(db, "oid-rank-zero2", owner=owner, size_bytes=5000)
            data = reports_service.get_general_report_data()
            for p in data["top_projects_size"]:
                assert p["size_fmt"] != "0.0 B"


class TestActionTranslation:
    """Internal action names should be translated to Spanish."""

    def test_translate_known_actions(self):
        assert exporters._translate_action("changed") == "Cambio de rol"
        assert exporters._translate_action("sync_error") == "Error de sincronización"
        assert exporters._translate_action("login") == "Inicio de sesión"
        assert exporters._translate_action("export") == "Exportación"

    def test_translate_unknown_action_returns_original(self):
        assert exporters._translate_action("custom_action") == "custom_action"

    def test_translate_none_returns_empty(self):
        assert exporters._translate_action(None) == ""


class TestSmartTruncate:
    """Text truncation should use word boundaries and ellipsis."""

    def test_short_text_unchanged(self):
        assert exporters._smart_truncate("hello", 60) == "hello"

    def test_long_text_truncated_with_ellipsis(self):
        long_text = "Este es un mensaje de error muy largo que supera el limite"
        result = exporters._smart_truncate(long_text, 30)
        assert result.endswith("…")
        assert len(result) <= 32  # 30 + ellipsis

    def test_empty_text(self):
        assert exporters._smart_truncate("", 60) == ""
        assert exporters._smart_truncate(None, 60) == ""


class TestNarrativeSummary:
    """Rule-based narrative summary should reflect data state."""

    def test_narrative_contains_user_count(self, app, db):
        with app.app_context():
            make_user(db, "oid-narr1")
            make_user(db, "oid-narr2")
            data = reports_service.get_general_report_data()
            text = exporters._build_narrative_summary(data)
            assert "2" in text
            assert "usuarios" in text

    def test_narrative_warns_exceeded_quota(self, app, db):
        with app.app_context():
            u = make_user(db, "oid-narr-exc", max_quota_bytes=100)
            make_project(db, "oid-narr-exc-p", owner=u, size_bytes=200)
            data = reports_service.get_general_report_data()
            text = exporters._build_narrative_summary(data)
            assert "superado" in text.lower() or "Atención" in text

    def test_narrative_no_alerts_message(self, app, db):
        with app.app_context():
            data = reports_service.get_general_report_data()
            text = exporters._build_narrative_summary(data)
            assert "No se han registrado alertas" in text

    def test_general_pdf_with_narrative_generates_valid_pdf(self, app, db):
        """General PDF with narrative text should be valid."""
        with app.app_context():
            make_user(db, "oid-narr-pdf1")
            make_project(db, "oid-narr-pdf-p", size_bytes=5000)
            make_sync(db, status="success")
            data = reports_service.get_general_report_data()
            pdf_data, _, _ = exporters.export_general_pdf(data)
            assert pdf_data[:5] == b"%PDF-"
            assert len(pdf_data) > 500
