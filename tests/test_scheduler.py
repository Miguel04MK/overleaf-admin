"""
tests/test_scheduler.py
-----------------------
Tests para la lógica del tick de APScheduler en app/etl/scheduler.py.

No arrancamos APScheduler real: testeamos `_process_due_schedules` directamente
con un `run_sync` mockeado. Esto verifica que:
  - Sólo se procesan schedules activas con next_run_at <= now.
  - El campo next_run_at se reprograma correctamente tras la ejecución.
  - No se solapan: si is_sync_running() es True, no se lanza nada.
  - Sólo se lanza UNA schedule por tick (la más antigua) aunque haya varias
    vencidas — la siguiente se ejecutará en el próximo tick.
"""
from datetime import datetime, timezone, timedelta
from unittest.mock import patch

import pytest

from app.config.extensions import db as _db
from app.etl import scheduler
from app.model.entities.sync_schedule import SyncSchedule
from app.model.services import sync_service


def _make_sch(db, *, name="test", sync_type="full", interval_minutes=60,
              enabled=True, next_run_at=None):
    s = SyncSchedule(
        name=name,
        sync_type=sync_type,
        interval_minutes=interval_minutes,
        enabled=enabled,
        next_run_at=next_run_at,
    )
    db.session.add(s)
    db.session.commit()
    return s


# ── Lógica del tick ──────────────────────────────────────────────────────────

class TestProcessDueSchedules:

    def test_no_schedules_does_nothing(self, app, db):
        """Sin schedules → tick no hace nada y no falla."""
        with patch("app.etl.runners.runner.run_sync") as m:
            scheduler._process_due_schedules(app)
        m.assert_not_called()  # asegura que ni siquiera intentó

    def test_skips_disabled_schedules(self, app, db):
        with app.app_context():
            past = datetime.now(timezone.utc) - timedelta(minutes=5)
            _make_sch(db, name="paused", enabled=False, next_run_at=past)
        with patch("app.etl.runners.runner.run_sync") as m, app.app_context():
            scheduler._process_due_schedules(app)
        m.assert_not_called()

    def test_skips_future_schedules(self, app, db):
        with app.app_context():
            future = datetime.now(timezone.utc) + timedelta(hours=1)
            _make_sch(db, name="future", next_run_at=future)
        with patch("app.etl.runners.runner.run_sync") as m, app.app_context():
            scheduler._process_due_schedules(app)
        m.assert_not_called()

    def test_runs_due_schedule(self, app, db):
        with app.app_context():
            past = datetime.now(timezone.utc) - timedelta(minutes=2)
            sch  = _make_sch(db, name="due", sync_type="users",
                             interval_minutes=60, next_run_at=past)
            sid  = sch.id
        with patch("app.etl.runners.runner.run_sync") as m, app.app_context():
            scheduler._process_due_schedules(app)
        assert m.called
        # Verifica que se llamó con el sync_type correcto
        kwargs = m.call_args.kwargs
        assert kwargs.get("sync_type") == "users"
        assert kwargs.get("triggered_by") == "scheduled"

    def test_reschedules_next_run(self, app, db):
        """Tras ejecutar, next_run_at se mueve al futuro (+interval_minutes)."""
        with app.app_context():
            past = datetime.now(timezone.utc) - timedelta(minutes=5)
            sch  = _make_sch(db, name="reschedule_me",
                             interval_minutes=60, next_run_at=past)
            sid  = sch.id
        with patch("app.etl.runners.runner.run_sync"), app.app_context():
            scheduler._process_due_schedules(app)
        with app.app_context():
            refreshed = _db.session.get(SyncSchedule, sid)
            now = datetime.now(timezone.utc)
            assert refreshed.next_run_at is not None
            # SQLite devuelve datetimes naive; normalizamos a UTC para comparar
            nra = refreshed.next_run_at
            if nra.tzinfo is None:
                nra = nra.replace(tzinfo=timezone.utc)
            delta = nra - now
            assert timedelta(minutes=55) < delta < timedelta(minutes=65)
            assert refreshed.last_run_at is not None

    def test_does_not_run_when_sync_in_progress(self, app, db):
        """Si is_sync_running() devuelve True, el tick no lanza nada."""
        with app.app_context():
            past = datetime.now(timezone.utc) - timedelta(minutes=1)
            _make_sch(db, name="hold", next_run_at=past)
        with patch("app.etl.runners.runner.run_sync") as m_run, \
             patch.object(sync_service, "is_sync_running", return_value=True), \
             app.app_context():
            scheduler._process_due_schedules(app)
        m_run.assert_not_called()

    def test_only_one_schedule_per_tick(self, app, db):
        """Aunque haya varias vencidas, sólo se lanza una por tick."""
        with app.app_context():
            past = datetime.now(timezone.utc) - timedelta(minutes=10)
            _make_sch(db, name="due1", next_run_at=past, sync_type="users")
            _make_sch(db, name="due2", next_run_at=past, sync_type="projects")
        with patch("app.etl.runners.runner.run_sync") as m, app.app_context():
            scheduler._process_due_schedules(app)
        assert m.call_count == 1

    def test_oldest_schedule_runs_first(self, app, db):
        with app.app_context():
            old   = datetime.now(timezone.utc) - timedelta(minutes=20)
            newer = datetime.now(timezone.utc) - timedelta(minutes=5)
            _make_sch(db, name="newer", next_run_at=newer, sync_type="users")
            _make_sch(db, name="older", next_run_at=old,   sync_type="projects")
        with patch("app.etl.runners.runner.run_sync") as m, app.app_context():
            scheduler._process_due_schedules(app)
        assert m.call_args.kwargs.get("sync_type") == "projects"


# ── Gating de init_scheduler ─────────────────────────────────────────────────

class TestSchedulerGating:

    def test_disabled_config_does_not_start(self, app):
        """Si SCHEDULER_ENABLED=False (como en TestingConfig) no se arranca."""
        # En testing, SCHEDULER_ENABLED=False por defecto, así que init no debe
        # arrancar nada — y la suite tampoco lo activa.
        assert app.config.get("SCHEDULER_ENABLED") is False
        result = scheduler.init_scheduler(app)
        assert result is None
        assert scheduler.is_running() is False
