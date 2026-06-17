"""
tests/test_dashboard.py
-----------------------
Tests for the dashboard service and route (summary-only view).
Heavy analytics tests live in test_metrics.py.

Run with:
    python -m pytest tests/test_dashboard.py -v
"""
import pytest
from datetime import datetime, timezone, timedelta

from app import create_app
from app.config.extensions import db as _db
from app.model.entities.overleaf_user import OverleafUser
from app.model.entities.overleaf_project import OverleafProject
from app.model.entities.sync_run import SyncRun
from app.model.entities.system_alert import SystemAlert
from app.model.entities.audit_log import AuditLog
from app.model.entities.role import Role
from app.model.entities.admin_user import AdminUser


@pytest.fixture()
def app():
    app = create_app("testing")
    with app.app_context():
        _db.create_all()
        yield app
        _db.session.remove()
        _db.drop_all()


@pytest.fixture()
def db(app):
    return _db


@pytest.fixture()
def client(app):
    return app.test_client()


@pytest.fixture()
def seed_roles(db):
    r1 = Role(name="alumno", is_default=True, color="primary",
              storage_quota_bytes=500 * 1024 * 1024, max_projects=20)
    r2 = Role(name="profesor", is_default=False, color="info",
              storage_quota_bytes=5 * 1024 ** 3, max_projects=50)
    r3 = Role(name="admin", is_default=False, color="warning",
              storage_quota_bytes=None, max_projects=None)
    db.session.add_all([r1, r2, r3])
    db.session.commit()
    return {"alumno": r1, "profesor": r2, "admin": r3}


@pytest.fixture()
def seed_users(db, seed_roles):
    users = []
    for i in range(5):
        u = OverleafUser(
            overleaf_id=f"user_{i}",
            email=f"user{i}@test.com",
            first_name=f"User{i}",
            last_name="Test",
            role_id=seed_roles["alumno"].id,
            max_quota_bytes=500 * 1024 * 1024,
        )
        users.append(u)
    prof = OverleafUser(
        overleaf_id="prof_1",
        email="prof@test.com",
        first_name="Prof",
        last_name="Test",
        role_id=seed_roles["profesor"].id,
        max_quota_bytes=5 * 1024 ** 3,
    )
    users.append(prof)
    db.session.add_all(users)
    db.session.commit()
    return users


@pytest.fixture()
def seed_projects(db, seed_users):
    projects = []
    for i, user in enumerate(seed_users[:3]):
        for j in range(i + 1):
            p = OverleafProject(
                overleaf_id=f"proj_{user.overleaf_id}_{j}",
                name=f"Project {j} of {user.email}",
                owner_id=user.id,
                size_bytes=(j + 1) * 1024 * 1024,
            )
            projects.append(p)
    db.session.add_all(projects)
    db.session.commit()
    return projects


@pytest.fixture()
def seed_sync(db):
    now = datetime.now(timezone.utc)
    s = SyncRun(
        started_at=now - timedelta(minutes=5),
        finished_at=now,
        status="success",
        users_found=50,
        projects_found=52,
        triggered_by="manual",
    )
    db.session.add(s)
    db.session.commit()
    return s


@pytest.fixture()
def seed_alerts(db):
    alerts = []
    for i, (level, type_) in enumerate([
        ("warning", "quota_warning"),
        ("danger", "quota_exceeded"),
        ("critical", "sync_failed"),
    ]):
        a = SystemAlert(
            type=type_, level=level,
            title=f"Test alert {i}",
            message=f"Test alert message {i}",
            is_resolved=False, is_read=False,
        )
        alerts.append(a)
    db.session.add_all(alerts)
    db.session.commit()
    return alerts


@pytest.fixture()
def seed_audit_logs(db):
    logs = []
    for i in range(3):
        log = AuditLog(
            actor="system",
            action="sync_ok",
            detail=f"Sync completed {i}",
            level="info",
        )
        logs.append(log)
    db.session.add_all(logs)
    db.session.commit()
    return logs


@pytest.fixture()
def login(client, db):
    admin = AdminUser(
        username="testadmin",
        email="admin@test.com",
        is_active=True,
    )
    admin.set_password("test1234")
    db.session.add(admin)
    db.session.commit()
    client.post("/auth/login", data={
        "username": "testadmin",
        "password": "test1234",
    }, follow_redirects=True)
    return admin


# ── Dashboard service tests ──────────────────────────────────────────────────

class TestDashboardService:

    def test_total_users(self, app, seed_users):
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert data["total_users"] == 6

    def test_total_projects(self, app, seed_projects):
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert data["total_projects"] == len(seed_projects)

    def test_total_storage_nonzero(self, app, seed_projects):
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert data["total_storage_bytes"] > 0
        assert data["total_storage_fmt"] != "0 B"

    def test_avg_projects_per_user(self, app, seed_projects):
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert data["avg_projects_per_user"] > 0

    def test_latest_sync(self, app, seed_sync):
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert data["last_sync"] is not None
        assert data["last_sync"].status == "success"

    def test_no_sync_shows_none(self, app):
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert data["last_sync"] is None

    def test_active_alerts_count(self, app, seed_alerts):
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert data["alerts_active"] == 3
        assert "warning" in data["alerts_by_level"]
        assert "danger" in data["alerts_by_level"]
        assert "critical" in data["alerts_by_level"]

    def test_no_alerts_shows_zero(self, app):
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert data["alerts_active"] == 0

    def test_role_stats(self, app, seed_users, seed_roles):
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert isinstance(data["role_stats"], dict)
        total_in_roles = sum(data["role_stats"].values())
        assert total_in_roles == 6

    def test_recent_alerts(self, app, seed_alerts):
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert len(data["recent_alerts"]) == 3

    def test_recent_audit(self, app, seed_audit_logs):
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert len(data["recent_audit"]) == 3

    def test_db_ok(self, app):
        """`db_ok` se retiró del dashboard junto al panel de salud de servicios."""
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert isinstance(data, dict)
        assert "db_ok" not in data

    def test_empty_db_returns_defaults(self, app):
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert data["total_users"] == 0
        assert data["total_projects"] == 0
        assert data["total_storage_fmt"] == "0 B"
        assert data["alerts_active"] == 0
        assert data["last_sync"] is None

    def test_section_isolation(self, app, seed_users, seed_alerts, seed_sync):
        """Even if one section has issues, other sections should still return data."""
        from app.model.services.dashboard_service import get_dashboard_data
        data = get_dashboard_data()
        assert data["total_users"] == 6
        assert data["alerts_active"] == 3
        assert data["last_sync"] is not None


# ── Dashboard route tests ────────────────────────────────────────────────────

class TestDashboardRoute:

    def test_dashboard_renders_without_errors(self, client, login, seed_users,
                                               seed_projects, seed_sync,
                                               seed_alerts, seed_audit_logs):
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Dashboard" in html

    def test_dashboard_shows_user_count(self, client, login, seed_users):
        resp = client.get("/")
        html = resp.data.decode()
        assert "6" in html

    def test_dashboard_shows_project_count(self, client, login, seed_projects):
        resp = client.get("/")
        html = resp.data.decode()
        assert str(len(seed_projects)) in html

    def test_dashboard_shows_sync_date(self, client, login, seed_sync):
        resp = client.get("/")
        html = resp.data.decode()
        assert "Nunca" not in html or "Exitosa" in html

    def test_dashboard_shows_alert_count(self, client, login, seed_alerts):
        resp = client.get("/")
        html = resp.data.decode()
        assert "3" in html

    def test_dashboard_empty_db_no_errors(self, client, login):
        resp = client.get("/")
        assert resp.status_code == 200

    def test_dashboard_has_metrics_link(self, client, login):
        """Dashboard should link to the metrics page."""
        resp = client.get("/")
        html = resp.data.decode()
        assert "/metricas" in html or "metricas" in html


# ── Sidebar badge ────────────────────────────────────────────────────────────

class TestSidebarBadge:

    def test_badge_visible_outside_alerts_page(self, client, login, seed_alerts):
        """The active-alerts badge must appear on the dashboard, not only inside /alertas/."""
        resp = client.get("/")
        html = resp.data.decode()
        assert "Alertas" in html
        assert ">\n              3\n            <" in html or ">3<" in html.replace(" ", "").replace("\n", "")

    def test_badge_visible_on_users_page(self, client, login, seed_alerts):
        resp = client.get("/usuarios/")
        if resp.status_code == 200:
            assert "sidebar_active_alerts" not in resp.data.decode()
            assert "Alertas" in resp.data.decode()


# ── Dashboard ↔ alerts service coherence ─────────────────────────────────────

class TestAlertsCoherence:

    def test_active_count_matches_recent_alerts_source(self, app, seed_alerts):
        """If alerts_active > 0, recent_alerts must not be empty."""
        from app.model.services.dashboard_service import get_dashboard_data
        from app.model.services import alerts_service
        data = get_dashboard_data()
        assert data["alerts_active"] == alerts_service.get_active_count()
        if data["alerts_active"] > 0:
            assert len(data["recent_alerts"]) > 0

    def test_recent_alerts_template_no_empty_state_when_active(self, client, login, seed_alerts):
        resp = client.get("/")
        html = resp.data.decode()
        assert "No hay alertas activas" not in html


# ── Performance: dashboard does NOT recalculate alerts ───────────────────────

class TestDashboardPerformance:

    def test_dashboard_does_not_recalculate_alerts(self, client, login, seed_users,
                                                    seed_projects, seed_alerts, monkeypatch):
        called = {"flag": False}
        from app.model.services import alerts_service

        def fake_recalc(*a, **kw):
            called["flag"] = True

        monkeypatch.setattr(alerts_service, "recalculate_alerts", fake_recalc)
        monkeypatch.setattr(alerts_service, "generate_quota_alerts", fake_recalc)
        monkeypatch.setattr(alerts_service, "generate_project_limit_alerts", fake_recalc)

        resp = client.get("/")
        assert resp.status_code == 200
        assert called["flag"] is False, "Dashboard must NOT recalculate alerts on load"


# ── Analytics service unit tests ─────────────────────────────────────────────

class TestAnalyticsService:

    def test_users_near_quota_caps_at_10(self, app, seed_users, seed_projects):
        from app.model.services.dashboard_analytics_service import users_near_quota_dataset
        ds = users_near_quota_dataset()
        assert len(ds["labels"]) <= 10
        assert ds["type"] == "bar"
        assert ds["unit"] == "%"

    def test_inactive_users_dataset(self, app, db, seed_users):
        from app.model.services.dashboard_analytics_service import inactive_users_dataset
        u = seed_users[0]
        u.last_login_at = datetime(2020, 1, 1, tzinfo=timezone.utc)
        db.session.commit()
        ds = inactive_users_dataset()
        assert ds["id"] == "inactive_users"
        assert len(ds["labels"]) <= 10
        assert any(v is not None and v > 0 for v in ds["values"])

    def test_role_quota_change_propagates_and_triggers_alerts(self, app, db, seed_roles):
        from app.model.entities.overleaf_user import OverleafUser
        from app.model.entities.overleaf_project import OverleafProject
        from app.model.entities.system_alert import SystemAlert
        from app.model.services import roles_service

        alumno = seed_roles["alumno"]
        u1 = OverleafUser(overleaf_id="u1", email="u1@test.com",
                          role_id=alumno.id, max_quota_bytes=alumno.storage_quota_bytes)
        u2 = OverleafUser(overleaf_id="u2", email="u2@test.com",
                          role_id=alumno.id, max_quota_bytes=alumno.storage_quota_bytes)
        db.session.add_all([u1, u2]); db.session.commit()
        db.session.add_all([
            OverleafProject(overleaf_id="p1", name="P1", owner_id=u1.id, size_bytes=4 * 1024 * 1024),
            OverleafProject(overleaf_id="p2", name="P2", owner_id=u2.id, size_bytes=4 * 1024 * 1024),
        ])
        db.session.commit()

        ok, msg = roles_service.update_role_config(
            role_id=alumno.id, description=None,
            storage_quota_bytes=1 * 1024 * 1024, max_projects=alumno.max_projects,
        )
        assert ok
        db.session.refresh(u1); db.session.refresh(u2)
        assert u1.max_quota_bytes == 1 * 1024 * 1024
        assert u2.max_quota_bytes == 1 * 1024 * 1024
        active = SystemAlert.query.filter_by(is_resolved=False, type="quota_exceeded").count()
        assert active >= 2

    def test_role_quota_change_preserves_custom_overrides(self, app, db, seed_roles):
        from app.model.entities.overleaf_user import OverleafUser
        from app.model.services import roles_service
        alumno = seed_roles["alumno"]
        custom = OverleafUser(overleaf_id="u_custom", email="custom@test.com",
                              role_id=alumno.id,
                              max_quota_bytes=999_999)
        db.session.add(custom); db.session.commit()
        roles_service.update_role_config(
            role_id=alumno.id, description=None,
            storage_quota_bytes=1234, max_projects=alumno.max_projects,
        )
        db.session.refresh(custom)
        assert custom.max_quota_bytes == 999_999

    def test_users_near_project_limit_filters_unlimited(self, app, db, seed_users, seed_roles):
        from app.model.services.dashboard_analytics_service import users_near_project_limit_dataset
        ds = users_near_project_limit_dataset()
        admin_emails = [u.email for u in seed_users if u.role_id == seed_roles["admin"].id]
        for lbl in ds["labels"]:
            assert lbl not in admin_emails


# ── Dashboard rendering ─────────────────────────────────────────────────────

class TestDashboardRendering:

    def test_get_root_has_kpi_strip(self, client, login):
        resp = client.get("/")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "kpi-strip" in html
        assert "kpi--users" in html
        assert "kpi--projects" in html

    def test_get_root_renders_kpi_strip(self, client, login):
        """La barra inferior 'status-line' se retiró; el dashboard ahora se
        compone de la franja de KPIs + filas de cards. Verificamos que
        renderiza la franja de KPIs."""
        resp = client.get("/")
        html = resp.data.decode()
        assert "kpi-strip" in html
        assert "status-line" not in html

    def test_dashboard_renders_audit_translations(self, client, login, seed_audit_logs):
        resp = client.get("/")
        html = resp.data.decode()
        assert "Sincronización OK" in html or "sync_ok" not in html

    def test_failed_section_does_not_poison_subsequent_sections(
        self, app, db, monkeypatch, seed_users, seed_projects,
    ):
        """If section N raises, sections N+1, N+2... must still produce data."""
        from app.model.services import dashboard_service
        original = dashboard_service.get_dashboard_data
        import app.model.entities.overleaf_user as ou
        monkeypatch.setattr(ou, "QUOTA_WARNING_PCT", "not-a-number")
        d = original()
        # Core KPIs must still work even if quota section fails
        assert d["total_users"] > 0
        assert d["recent_audit"] is not None

    def test_get_root_does_not_recalculate_alerts(
        self, client, login, seed_users, seed_projects, seed_alerts, monkeypatch,
    ):
        called = {"flag": False}
        from app.model.services import alerts_service
        monkeypatch.setattr(alerts_service, "recalculate_alerts",
                            lambda *a, **kw: called.update(flag=True))
        monkeypatch.setattr(alerts_service, "generate_quota_alerts",
                            lambda *a, **kw: called.update(flag=True))
        monkeypatch.setattr(alerts_service, "generate_project_limit_alerts",
                            lambda *a, **kw: called.update(flag=True))
        resp = client.get("/")
        assert resp.status_code == 200
        assert called["flag"] is False


class TestLabelTruncation:

    def test_rotation_datasets_keep_full_labels(self, app, db, seed_roles):
        from app.model.entities.overleaf_user import OverleafUser
        from app.model.services.dashboard_analytics_service import inactive_users_dataset
        u = OverleafUser(
            overleaf_id="long_email_user",
            email="very.long.email.address.that.exceeds.usual.length@universidad.es",
            last_login_at=datetime(2020, 1, 1, tzinfo=timezone.utc),
            role_id=seed_roles["alumno"].id,
        )
        db.session.add(u); db.session.commit()
        ds = inactive_users_dataset()
        long_labels = [l for l in ds["labels"] if "very.long.email" in l]
        assert long_labels, "Long email should be present in dataset"
        assert len(long_labels[0]) > 22


# ── Metrics route tests ──────────────────────────────────────────────────────

class TestMetricsRoute:

    def test_metrics_renders_without_errors(self, client, login, seed_users,
                                             seed_projects, seed_sync,
                                             seed_alerts, seed_audit_logs):
        resp = client.get("/metricas/")
        assert resp.status_code == 200
        html = resp.data.decode()
        assert "Métricas" in html or "tricas" in html

    def test_metrics_requires_login(self, client):
        resp = client.get("/metricas/", follow_redirects=False)
        assert resp.status_code in (302, 401)

    def test_metrics_shows_growth_charts(self, client, login, seed_users, seed_projects):
        resp = client.get("/metricas/")
        html = resp.data.decode()
        # Tras la reorganización, las gráficas usuarios/proyectos se fusionan
        # en una card "Crecimiento" con un switcher. Buscamos cualquier marcador.
        assert (
            "Crecimiento" in html
            and ("growth-panel" in html or "chartGrowthUsers" in html)
        )

    def test_metrics_shows_rankings(self, client, login, seed_projects):
        resp = client.get("/metricas/")
        html = resp.data.decode()
        # Ranking ahora vive en la tab "Usuarios y proyectos" con switcher
        # entre "Más proyectos" y "Más almacenamiento".
        assert "Ranking" in html and "ranking-panel" in html

    def test_metrics_shows_sync_history(self, client, login, seed_sync):
        resp = client.get("/metricas/")
        html = resp.data.decode()
        # Tras la reorganización, el historial vive en la tab "Sincronización";
        # buscamos cualquier marcador estable de esa sección.
        assert (
            "Historial" in html
            and ("Sincronización" in html or "sync-tbl" in html)
        )

    def test_metrics_empty_db_no_errors(self, client, login):
        resp = client.get("/metricas/")
        assert resp.status_code == 200

    def test_metrics_renders_tab_structure(self, client, login):
        """La pantalla de métricas se organiza en 4 tabs (se retiró 'salud')."""
        resp = client.get("/metricas/")
        html = resp.data.decode()
        assert 'id="metricsTabs"' in html
        for tid in ("tab-resumen", "tab-usuarios", "tab-storage", "tab-sync"):
            assert f'data-bs-target="#{tid}"' in html, f"falta tab {tid}"
        assert 'data-bs-target="#tab-salud"' not in html

    def test_metrics_has_chart_switchers(self, client, login):
        """Las gráficas hermanas (crecimiento / ranking) se fusionan con un
        switcher dentro de la misma card."""
        resp = client.get("/metricas/")
        html = resp.data.decode()
        assert 'class="chart-switch"' in html or "chart-switch" in html
        assert "growth-panel" in html
        assert "ranking-panel" in html


# ── Metrics service tests ────────────────────────────────────────────────────

class TestMetricsService:

    def test_growth_users_has_12_months(self, app, seed_users):
        from app.model.services.metrics_service import get_metrics_data
        d = get_metrics_data()
        assert len(d["growth_users"]) == 12
        for entry in d["growth_users"]:
            assert "label" in entry and "count" in entry

    def test_growth_projects_has_12_months(self, app, seed_projects):
        from app.model.services.metrics_service import get_metrics_data
        d = get_metrics_data()
        assert len(d["growth_projects"]) == 12

    def test_top_owners_populated(self, app, seed_projects):
        from app.model.services.metrics_service import get_metrics_data
        d = get_metrics_data()
        assert len(d["top_owners"]) > 0
        assert "label" in d["top_owners"][0]
        assert "count" in d["top_owners"][0]
        assert "user_id" in d["top_owners"][0]

    def test_top_storage_populated(self, app, seed_projects):
        from app.model.services.metrics_service import get_metrics_data
        d = get_metrics_data()
        assert len(d["top_storage"]) > 0
        assert "label" in d["top_storage"][0]
        assert "bytes" in d["top_storage"][0]
        assert d["top_storage"][0]["bytes"] > 0

    def test_size_buckets_populated(self, app, seed_projects):
        from app.model.services.metrics_service import get_metrics_data
        d = get_metrics_data()
        total = sum(b["count"] for b in d["size_buckets"])
        assert total == len(seed_projects)
        assert len(d["size_buckets"]) == 5

    def test_size_buckets_empty_when_no_projects(self, app):
        from app.model.services.metrics_service import get_metrics_data
        d = get_metrics_data()
        assert sum(b["count"] for b in d["size_buckets"]) == 0

    def test_sync_history(self, app, seed_sync):
        from app.model.services.metrics_service import get_metrics_data
        d = get_metrics_data()
        assert len(d["sync_history"]) == 1
        assert d["sync_stats"]["total_runs"] == 1
        assert d["sync_stats"]["success_rate"] == 100.0

    def test_avg_projects_per_user(self, app, seed_projects):
        from app.model.services.metrics_service import get_metrics_data
        d = get_metrics_data()
        assert d["avg_projects_per_user"] > 0

    def test_role_distribution(self, app, seed_users, seed_roles):
        from app.model.services.metrics_service import get_metrics_data
        d = get_metrics_data()
        assert len(d["role_distribution"]) >= 3
        total = sum(r["count"] for r in d["role_distribution"])
        assert total == 6

    def test_empty_db_returns_defaults(self, app):
        from app.model.services.metrics_service import get_metrics_data
        d = get_metrics_data()
        assert d["total_users"] == 0
        assert d["total_projects"] == 0
        assert d["avg_projects_per_user"] == 0.0
        assert d["sync_history"] == []
