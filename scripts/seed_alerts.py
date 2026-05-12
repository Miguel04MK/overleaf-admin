"""
scripts/seed_alerts.py
----------------------
Inserts 10 realistic SystemAlert records for UI testing.

Usage:
    python scripts/seed_alerts.py

Adds variety: critical / danger / warning / info levels,
active / resolved states, read / unread, and several
entity types (user, service, sync_run, project).
"""
import sys
import os
import json
from datetime import datetime, timezone, timedelta

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.config.extensions import db
from app.model.entities.system_alert import SystemAlert


def _dt(days_ago: int, hours: int = 0) -> datetime:
    return datetime.now(timezone.utc) - timedelta(days=days_ago, hours=hours)


ALERTS = [
    # 1 — Critical: MongoDB service unreachable
    dict(
        type="service_down",
        level="critical",
        title="Servicio MongoDB caído",
        message=(
            "No se puede establecer conexión con el servidor MongoDB en "
            "mongodb://localhost:27017. Todos los accesos a datos están bloqueados."
        ),
        entity_type="service",
        entity_id="mongodb",
        is_read=False,
        is_resolved=False,
        created_by_system=True,
        source="health_checker",
        created_at=_dt(0, 2),
        extra_data_json=json.dumps({"host": "localhost", "port": 27017, "retries": 5}),
    ),
    # 2 — Danger: user quota exceeded
    dict(
        type="quota_exceeded",
        level="danger",
        title="Cuota de almacenamiento superada — usuario #42",
        message=(
            "El usuario con id 42 (ana.gomez@universidad.es) ha superado su cuota "
            "de almacenamiento asignada (5 GB). Uso actual: 5.8 GB."
        ),
        entity_type="user",
        entity_id="42",
        is_read=False,
        is_resolved=False,
        created_by_system=True,
        source="quota_checker",
        created_at=_dt(0, 5),
        extra_data_json=json.dumps({"quota_gb": 5, "used_gb": 5.8}),
    ),
    # 3 — Danger: last sync failed
    dict(
        type="sync_failed",
        level="danger",
        title="Sincronización con Overleaf fallida",
        message=(
            "La última ejecución del ETL terminó con errores. "
            "Se procesaron 120 usuarios pero 8 fallaron al importarse. "
            "Revisa los logs del runner para más detalles."
        ),
        entity_type="sync_run",
        entity_id="last",
        is_read=True,
        is_resolved=False,
        created_by_system=True,
        source="sync_checker",
        created_at=_dt(1),
        extra_data_json=json.dumps({"total": 120, "failed": 8, "run_id": "sync-20260510"}),
    ),
    # 4 — Warning: quota near limit
    dict(
        type="quota_warning",
        level="warning",
        title="Cuota al 85 % — usuario #17",
        message=(
            "El usuario con id 17 (carlos.ruiz@universidad.es) ha alcanzado el 85 % "
            "de su cuota de almacenamiento (4.25 GB de 5 GB)."
        ),
        entity_type="user",
        entity_id="17",
        is_read=False,
        is_resolved=False,
        created_by_system=True,
        source="quota_checker",
        created_at=_dt(1, 3),
        extra_data_json=json.dumps({"quota_gb": 5, "used_gb": 4.25, "pct": 85}),
    ),
    # 5 — Warning: project collaborator limit
    dict(
        type="project_limit_warning",
        level="warning",
        title="Número de proyectos cercano al límite — usuario #8",
        message=(
            "El usuario con id 8 (laura.martin@universidad.es) tiene 8 proyectos "
            "activos sobre un límite de 10 (80 %)."
        ),
        entity_type="user",
        entity_id="8",
        is_read=True,
        is_resolved=False,
        created_by_system=True,
        source="project_limit_checker",
        created_at=_dt(2),
        extra_data_json=json.dumps({"project_count": 8, "limit": 10, "pct": 80}),
    ),
    # 6 — Warning: repeated errors on a service
    dict(
        type="repeated_errors",
        level="warning",
        title="Errores repetidos en el servicio de compilación LaTeX",
        message=(
            "Se han registrado 12 errores de compilación LaTeX en las últimas 2 horas. "
            "Posible problema con la instalación de TeX Live o permisos de directorio."
        ),
        entity_type="service",
        entity_id="latex_compiler",
        is_read=False,
        is_resolved=False,
        created_by_system=True,
        source="error_monitor",
        created_at=_dt(2, 6),
        extra_data_json=json.dumps({"error_count": 12, "window_hours": 2}),
    ),
    # 7 — Info (resolved): service back online
    dict(
        type="service_down",
        level="info",
        title="Servicio Redis recuperado",
        message=(
            "El servicio Redis dejó de responder a las 03:15 y fue restaurado "
            "automáticamente a las 03:28 tras reinicio del contenedor."
        ),
        entity_type="service",
        entity_id="redis",
        is_read=True,
        is_resolved=True,
        resolved_by="system",
        resolved_at=_dt(3, 0),
        resolution_comment="Contenedor reiniciado automáticamente por el health-check de Docker.",
        created_by_system=True,
        source="health_checker",
        created_at=_dt(3, 1),
        extra_data_json=json.dumps({"downtime_minutes": 13}),
    ),
    # 8 — Warning (resolved): PDF report generation failed
    dict(
        type="administrative_warning",
        level="warning",
        title="Error al generar informe PDF mensual",
        message=(
            "La generación del informe de actividad mensual (abril 2026) falló "
            "debido a un timeout al consultar la base de datos. "
            "El informe fue regenerado manualmente el día siguiente."
        ),
        entity_type=None,
        entity_id=None,
        is_read=True,
        is_resolved=True,
        resolved_by="admin",
        resolved_at=_dt(10),
        resolution_comment="Informe generado manualmente. Se amplió el timeout de consulta a 60 s.",
        created_by_system=True,
        source="report_scheduler",
        created_at=_dt(11),
        extra_data_json=json.dumps({"report": "monthly_april_2026", "timeout_s": 30}),
    ),
    # 9 — Danger: project limit exceeded
    dict(
        type="project_limit_exceeded",
        level="danger",
        title="Límite de proyectos superado — usuario #55",
        message=(
            "El usuario con id 55 (pedro.sanchez@universidad.es) tiene 11 proyectos "
            "activos, superando el límite máximo permitido de 10."
        ),
        entity_type="user",
        entity_id="55",
        is_read=False,
        is_resolved=False,
        created_by_system=True,
        source="project_limit_checker",
        created_at=_dt(4),
        extra_data_json=json.dumps({"project_count": 11, "limit": 10}),
    ),
    # 10 — Info (resolved): sync with minor warnings
    dict(
        type="sync_failed",
        level="info",
        title="Sincronización completada con avisos menores",
        message=(
            "La sincronización del 08/05/2026 finalizó correctamente para 118 usuarios. "
            "2 usuarios fueron ignorados por tener datos incompletos en Overleaf."
        ),
        entity_type="sync_run",
        entity_id="last",
        is_read=True,
        is_resolved=True,
        resolved_by="system",
        resolved_at=_dt(5),
        resolution_comment="Sincronización completada. Usuarios omitidos notificados al administrador.",
        created_by_system=True,
        source="sync_checker",
        created_at=_dt(5, 1),
        extra_data_json=json.dumps({"total": 120, "ok": 118, "skipped": 2}),
    ),
]


def seed():
    app = create_app()
    with app.app_context():
        existing = db.session.query(SystemAlert).count()
        if existing > 0:
            print(f"[INFO] Ya existen {existing} alertas. Añadiendo las nuevas de todas formas.")

        for data in ALERTS:
            alert = SystemAlert(**data)
            db.session.add(alert)

        db.session.commit()
        total = db.session.query(SystemAlert).count()
        print(f"[OK] Insertadas {len(ALERTS)} alertas de prueba. Total en BD: {total}.")


if __name__ == "__main__":
    seed()
