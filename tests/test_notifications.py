"""
tests/test_notifications.py
---------------------------
Tests del envío automático de correos de alerta (sección 12 de docs):

  - send_immediate_notifications(): correo «NUEVAS ALERTAS» agrupado, marca
    email_notified_at, respeta preferencias y admins sin email.
  - _digest_due() / send_periodic_digests(): resumen periódico según
    frequency / hour / last_digest_sent_at.

En TestingConfig el SMTP está forzado a mock, así que `_smtp_send` no envía
nada real y devuelve (True, ...).

Run: python -m pytest tests/test_notifications.py -v
"""
from datetime import datetime, timezone, timedelta

from app.model.entities.admin_user import AdminUser
from app.model.entities.admin_notification_pref import AdminNotificationPref
from app.model.entities.system_alert import SystemAlert
from app.model.services import notification_service


# ── Helpers ───────────────────────────────────────────────────────────────────

def _make_admin(db, username, email="a@test.com", active=True):
    a = AdminUser(username=username, email=email, is_active=active)
    a.set_password("x")
    db.session.add(a)
    db.session.commit()
    return a


def _make_pref(db, admin, **fields):
    p = AdminNotificationPref(admin_id=admin.id)
    # Por defecto, todo apagado para controlar el test explícitamente.
    for k in AdminNotificationPref.NOTIFY_KEYS:
        setattr(p, k, False)
        setattr(p, k + "_digest_only", False)
    for k, v in fields.items():
        setattr(p, k, v)
    db.session.add(p)
    db.session.commit()
    return p


def _make_alert(db, type="quota_warning", level="warning", resolved=False, notified=False):
    a = SystemAlert(
        type=type, level=level, title="T", message="M",
        is_resolved=resolved,
        email_notified_at=datetime.now(timezone.utc) if notified else None,
    )
    db.session.add(a)
    db.session.commit()
    return a


# ═══════════════════════════════════════════════════════════════════════════════
# INMEDIATO
# ═══════════════════════════════════════════════════════════════════════════════

class TestImmediateNotifications:

    def test_no_pending_returns_zero(self, app, db):
        with app.app_context():
            _make_admin(db, "a1")
            res = notification_service.send_immediate_notifications()
            assert res["sent"] == 0
            assert res["alerts_notified"] == 0

    def test_matching_alert_is_sent_and_marked(self, app, db):
        with app.app_context():
            admin = _make_admin(db, "a1", email="a1@test.com")
            _make_pref(db, admin, notify_quota_warning=True)
            alert = _make_alert(db, type="quota_warning", level="warning")

            res = notification_service.send_immediate_notifications()
            assert res["sent"] == 1
            assert res["alerts_notified"] == 1
            # La alerta queda marcada para no reenviarla
            refreshed = db.session.get(SystemAlert, alert.id)
            assert refreshed.email_notified_at is not None

    def test_non_matching_alert_not_sent(self, app, db):
        with app.app_context():
            admin = _make_admin(db, "a1", email="a1@test.com")
            # Pref con TODO apagado → no quiere ninguna inmediata
            _make_pref(db, admin)
            alert = _make_alert(db, type="quota_warning", level="warning")

            res = notification_service.send_immediate_notifications()
            assert res["sent"] == 0
            refreshed = db.session.get(SystemAlert, alert.id)
            assert refreshed.email_notified_at is None

    def test_already_notified_alert_excluded(self, app, db):
        with app.app_context():
            admin = _make_admin(db, "a1", email="a1@test.com")
            _make_pref(db, admin, notify_quota_warning=True)
            _make_alert(db, type="quota_warning", notified=True)

            res = notification_service.send_immediate_notifications()
            assert res["sent"] == 0  # ya tenía email_notified_at

    def test_admin_without_email_skipped(self, app, db):
        with app.app_context():
            admin = _make_admin(db, "a1", email="")
            _make_pref(db, admin, notify_quota_warning=True)
            alert = _make_alert(db, type="quota_warning")

            res = notification_service.send_immediate_notifications()
            assert res["sent"] == 0
            refreshed = db.session.get(SystemAlert, alert.id)
            assert refreshed.email_notified_at is None

    def test_multiple_alerts_grouped_in_one_email(self, app, db):
        with app.app_context():
            admin = _make_admin(db, "a1", email="a1@test.com")
            _make_pref(db, admin, notify_quota_warning=True, notify_danger=True)
            _make_alert(db, type="quota_warning", level="warning")
            _make_alert(db, type="quota_exceeded", level="danger")
            _make_alert(db, type="sync_failed",    level="danger")

            res = notification_service.send_immediate_notifications()
            # Un único correo (sent=1) pero 3 alertas notificadas
            assert res["sent"] == 1
            assert res["alerts_notified"] == 3

    def test_defaults_when_no_pref(self, app, db):
        """Sin fila de preferencias, los defaults conservadores aplican:
        critical/danger + sync_failed/quota_exceeded/repeated_errors."""
        with app.app_context():
            _make_admin(db, "a1", email="a1@test.com")  # sin pref
            _make_alert(db, type="quota_exceeded", level="danger")

            res = notification_service.send_immediate_notifications()
            assert res["sent"] == 1


# ═══════════════════════════════════════════════════════════════════════════════
# DIGEST — _digest_due
# ═══════════════════════════════════════════════════════════════════════════════

class TestDigestDue:

    def _pref(self, freq="daily", hour=None, last=None):
        p = AdminNotificationPref(admin_id=1)
        p.digest_frequency = freq
        p.digest_hour = hour
        p.last_digest_sent_at = last
        return p

    def test_none_pref_never_due(self):
        now = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)
        assert notification_service._digest_due(None, now) is False

    def test_disabled_never_due(self):
        now = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)
        assert notification_service._digest_due(self._pref(freq="disabled"), now) is False

    def test_first_send_no_hour_is_due(self):
        now = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)
        assert notification_service._digest_due(self._pref(freq="daily", hour=None), now) is True

    def test_first_send_with_hour_only_at_that_hour(self):
        pref = self._pref(freq="daily", hour=8)
        at_8  = datetime(2026, 6, 16, 8, 30, tzinfo=timezone.utc)
        at_10 = datetime(2026, 6, 16, 10, 0, tzinfo=timezone.utc)
        assert notification_service._digest_due(pref, at_8) is True
        assert notification_service._digest_due(pref, at_10) is False

    def test_not_due_before_interval(self):
        last = datetime(2026, 6, 16, 8, 0, tzinfo=timezone.utc)
        now  = datetime(2026, 6, 16, 12, 0, tzinfo=timezone.utc)  # 4h < daily
        assert notification_service._digest_due(self._pref(freq="daily", last=last), now) is False

    def test_due_after_interval(self):
        last = datetime(2026, 6, 15, 8, 0, tzinfo=timezone.utc)
        now  = datetime(2026, 6, 16, 9, 0, tzinfo=timezone.utc)  # 25h >= daily
        assert notification_service._digest_due(self._pref(freq="daily", last=last), now) is True


# ═══════════════════════════════════════════════════════════════════════════════
# DIGEST — send_periodic_digests
# ═══════════════════════════════════════════════════════════════════════════════

class TestPeriodicDigests:

    def test_disabled_admin_not_sent(self, app, db):
        with app.app_context():
            admin = _make_admin(db, "a1", email="a1@test.com")
            _make_pref(db, admin, notify_warning_digest_only=True)  # freq disabled por defecto
            _make_alert(db, type="quota_warning", level="warning")

            res = notification_service.send_periodic_digests()
            assert res["sent"] == 0

    def test_due_admin_with_matching_active_alert(self, app, db):
        with app.app_context():
            admin = _make_admin(db, "a1", email="a1@test.com")
            pref = _make_pref(db, admin, notify_warning_digest_only=True)
            pref.digest_frequency = "daily"
            pref.digest_hour = None
            pref.last_digest_sent_at = None  # primer envío → due
            db.session.commit()
            _make_alert(db, type="quota_warning", level="warning", resolved=False)

            res = notification_service.send_periodic_digests()
            assert res["sent"] == 1
            # last_digest_sent_at se actualiza
            refreshed = db.session.get(AdminNotificationPref, pref.id)
            assert refreshed.last_digest_sent_at is not None

    def test_resolved_alerts_excluded_from_digest(self, app, db):
        with app.app_context():
            admin = _make_admin(db, "a1", email="a1@test.com")
            pref = _make_pref(db, admin, notify_warning_digest_only=True)
            pref.digest_frequency = "daily"
            db.session.commit()
            _make_alert(db, type="quota_warning", level="warning", resolved=True)

            res = notification_service.send_periodic_digests()
            # No hay alertas activas que incluir → no se envía correo,
            # pero el digest se marca como procesado (no acumula intentos).
            assert res["sent"] == 0


# ═══════════════════════════════════════════════════════════════════════════════
# ProxyFix
# ═══════════════════════════════════════════════════════════════════════════════

class TestProxyFix:

    def test_proxyfix_disabled_by_default(self, app):
        # La app de tests se crea sin BEHIND_PROXY → wsgi_app no es ProxyFix
        assert type(app.wsgi_app).__name__ != "ProxyFix"

    def test_proxyfix_enabled_with_flag(self, monkeypatch):
        # BEHIND_PROXY se resuelve al importar config (os.getenv), así que
        # parcheamos el atributo de la clase de config en lugar del entorno.
        from app.config.config import TestingConfig
        monkeypatch.setattr(TestingConfig, "BEHIND_PROXY", True)
        from app import create_app
        a = create_app("testing")
        assert type(a.wsgi_app).__name__ == "ProxyFix"
