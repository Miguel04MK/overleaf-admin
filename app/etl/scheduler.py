"""
SyncScheduler — integración con APScheduler para ejecutar SyncSchedule.

Arquitectura:
  - Un único BackgroundScheduler arrancado al crear la app.
  - Un job de "tick" que se ejecuta cada 60 segundos:
      1. Consulta SyncSchedule.query.filter(enabled=True, next_run_at<=now).
      2. Para cada schedule vencida, lanza run_sync(sync_type=..., triggered_by="scheduled")
         desde un hilo de fondo (el propio ejecutor de APScheduler).
      3. Marca last_run_at = now y next_run_at = now + interval_minutes.

Garantías:
  - El _SYNC_LOCK del runner evita que se solapen syncs aunque haya múltiples
    schedules vencidas a la vez.
  - is_sync_running() (consulta a DB) descarta lanzar mientras ya hay una
    `status='running'` activa — no se crean SyncRun erróneos en cadena.
  - Idempotente al reinicio: la próxima vez que el tick corre, recoge lo que
    quedó pendiente. No hay estado en memoria que se pierda.

Gating:
  - Sólo arranca si app.config['SCHEDULER_ENABLED'] es True (default True).
  - En modo debug, evita arrancar en el proceso "watcher" del autoreloader
    de Werkzeug (sólo en el "main" se inicia el scheduler).
"""
from __future__ import annotations

import atexit
import logging
import os
import threading
from datetime import datetime, timezone, timedelta

logger = logging.getLogger(__name__)

# Singletons (una sola instancia por proceso, incluso si init_scheduler se
# llama varias veces — útil para tests y para el autoreload de Flask).
_scheduler = None
_init_lock = threading.Lock()

# Cadencia del tick (segundos). Como el intervalo mínimo configurable en
# SyncSchedule es 1 minuto, 60s es suficientemente fino.
TICK_SECONDS = 60


def init_scheduler(app):
    """Arranca el BackgroundScheduler con el job de tick. Idempotente.

    Llamarlo desde el app factory. Si el flag SCHEDULER_ENABLED es False
    o estamos en el proceso watcher del autoreloader, no hace nada.
    """
    global _scheduler

    if not app.config.get("SCHEDULER_ENABLED", True):
        logger.info("Scheduler deshabilitado por configuración.")
        return None

    # Werkzeug autoreloader arranca 2 procesos: el watcher y el main.
    # WERKZEUG_RUN_MAIN sólo está a "true" en el main. En producción la
    # variable no existe, así que la condición es laxa.
    if app.debug and os.environ.get("WERKZEUG_RUN_MAIN") != "true":
        logger.info("Scheduler omitido en el proceso watcher de Werkzeug.")
        return None

    with _init_lock:
        if _scheduler is not None and _scheduler.running:
            return _scheduler

        # Importación perezosa: si APScheduler no está instalado, lo dejamos
        # claro pero no rompemos la app.
        try:
            from apscheduler.schedulers.background import BackgroundScheduler
            from apscheduler.triggers.interval import IntervalTrigger
        except ImportError as exc:
            logger.error("APScheduler no instalado (%s) — scheduler deshabilitado.", exc)
            return None

        sch = BackgroundScheduler(
            timezone="UTC",
            job_defaults={
                "coalesce":      True,   # Combina ejecuciones perdidas en una
                "max_instances": 1,      # No solapar el mismo tick
                "misfire_grace_time": 60,
            },
        )
        sch.add_job(
            func=lambda: _tick(app),
            trigger=IntervalTrigger(seconds=TICK_SECONDS),
            id="sync_scheduler_tick",
            replace_existing=True,
            name="SyncScheduler tick",
            next_run_time=datetime.now(timezone.utc) + timedelta(seconds=10),
        )
        sch.start()
        _scheduler = sch

        atexit.register(_shutdown)
        logger.info("SyncScheduler arrancado — tick cada %ds.", TICK_SECONDS)
        return sch


def _shutdown():
    global _scheduler
    if _scheduler is not None and _scheduler.running:
        try:
            _scheduler.shutdown(wait=False)
            logger.info("SyncScheduler detenido.")
        except Exception as exc:
            logger.warning("Error al detener el scheduler: %s", exc)
    _scheduler = None


def is_running() -> bool:
    """True si el scheduler está arrancado (útil para tests y diagnóstico)."""
    return _scheduler is not None and _scheduler.running


def _tick(app):
    """Lógica de un tick: procesa schedules vencidas y envía notificaciones.

    Se importa en runtime (no top-level) para evitar acoplamientos circulares
    con la app factory.
    """
    try:
        with app.app_context():
            _process_due_schedules(app)
    except Exception as exc:
        logger.error("Excepción en tick (schedules): %s", exc, exc_info=True)

    # El envío de emails es independiente del estado de la sync: aunque haya
    # una sync corriendo, las alertas pendientes deben notificarse.
    try:
        with app.app_context():
            _process_email_notifications()
    except Exception as exc:
        logger.error("Excepción en tick (emails): %s", exc, exc_info=True)


def _process_email_notifications():
    """Dispara las notificaciones por email pendientes en cada tick:

      1. Inmediatas: un correo «NUEVAS ALERTAS» por admin con las alertas
         recién generadas que coincidan con su pestaña Inmediato.
      2. Periódicas: el resumen (digest) para los admins cuyo intervalo
         haya vencido.

    Silencioso si no hay nada que enviar.
    """
    from app.model.services import notification_service

    imm = notification_service.send_immediate_notifications(actor="scheduler")
    if imm.get("sent"):
        logger.info("Tick: %d correo(s) inmediato(s) enviados (%d alertas).",
                    imm["sent"], imm.get("alerts_notified", 0))

    dig = notification_service.send_periodic_digests(actor="scheduler")
    if dig.get("sent"):
        logger.info("Tick: %d resumen(es) periódico(s) enviados.", dig["sent"])


def _process_due_schedules(app):
    """Despacha las schedules que vencieron.

    Si ya hay una sync corriendo, no lanza más — el siguiente tick lo
    reintentará. Esto evita encolar errores cuando una sync larga se solapa
    con su propia siguiente ejecución.
    """
    from app.model.entities.sync_schedule import SyncSchedule
    from app.model.services.sync_service import is_sync_running
    from app.config.extensions import db

    if is_sync_running():
        logger.debug("Tick: hay sync corriendo, se difiere.")
        return

    now = datetime.now(timezone.utc)
    due = (
        SyncSchedule.query
        .filter(SyncSchedule.enabled.is_(True))
        .filter(SyncSchedule.next_run_at.isnot(None))
        .filter(SyncSchedule.next_run_at <= now)
        .order_by(SyncSchedule.next_run_at.asc())
        .all()
    )

    if not due:
        return

    # Si hay varias vencidas, ejecutamos UNA por tick (la más antigua). Las
    # demás se atenderán en el siguiente tick — así no encadenamos varias
    # sincronizaciones al mismo tiempo aunque coincida la activación.
    sch = due[0]
    logger.info(
        "Tick: lanzando schedule #%d «%s» (%s)",
        sch.id, sch.name, sch.sync_type,
    )

    # Reservamos la próxima ejecución ANTES de lanzar, así otros ticks no
    # vuelven a recogerla. Si la sync falla, la próxima ya estará programada
    # respetando el intervalo (no se ataca en bucle).
    sch.last_run_at = now
    sch.next_run_at = now + timedelta(minutes=sch.interval_minutes)
    db.session.commit()
    schedule_name = sch.name
    schedule_type = sch.sync_type

    try:
        from app.etl.runners.runner import run_sync
        run_sync(
            app,
            sync_type=schedule_type,
            triggered_by="scheduled",
            triggered_by_user=None,
        )
        # AuditLog específico de ejecución programada
        try:
            from app.model.services.admin import admin_service as audit_service
            audit_service.log_action(
                action="sync_scheduled_run",
                actor="scheduler",
                detail=f"Programación «{schedule_name}» ejecutada ({schedule_type}).",
                level="info",
            )
        except Exception as exc:
            logger.warning("AuditLog sync_scheduled_run falló: %s", exc)
    except Exception as exc:
        logger.error("Error al ejecutar schedule #%d: %s", sch.id, exc, exc_info=True)
