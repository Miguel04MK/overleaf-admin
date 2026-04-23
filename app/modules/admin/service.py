"""
AdminService — combines audit logging and service status checking.

Merges audit_service.py and status_service.py functionality.
"""
import logging
import socket
from dataclasses import dataclass, field
from urllib.parse import urlparse

from flask import current_app

from app.extensions import db
from app.models.audit_log import AuditLog

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Audit log functions (from audit_service.py)
# ---------------------------------------------------------------------------

def log_action(
    action: str,
    actor: str = "system",
    detail: str | None = None,
    level: str = "info",
    ip_address: str | None = None,
) -> None:
    """Write a single audit log entry. Silently swallows errors to avoid
    cascading failures when the audit log itself has a problem."""
    try:
        entry = AuditLog(
            actor=actor,
            action=action,
            detail=detail,
            level=level,
            ip_address=ip_address,
        )
        db.session.add(entry)
        db.session.commit()
    except Exception as exc:
        logger.error("Failed to write audit log: %s", exc)
        db.session.rollback()


def get_recent_logs(limit: int = 200):
    """Return the most recent audit log entries."""
    return (
        AuditLog.query.order_by(AuditLog.created_at.desc()).limit(limit).all()
    )


def get_paginated_logs(page: int = 1, per_page: int = 30):
    """Return paginated audit log entries."""
    return AuditLog.query.order_by(AuditLog.created_at.desc()).paginate(
        page=page, per_page=per_page, error_out=False
    )


# ---------------------------------------------------------------------------
# Service status functions (from status_service.py)
# ---------------------------------------------------------------------------

@dataclass
class ServiceStatus:
    name: str
    status: str          # "online" | "offline" | "unknown"
    detail: str = ""
    source: str = "mock" # "docker" | "tcp" | "mock"


def _check_tcp(host: str, port: int, timeout: float = 2.0) -> bool:
    """Return True if a TCP connection to host:port succeeds."""
    try:
        with socket.create_connection((host, port), timeout=timeout):
            return True
    except OSError:
        return False


def _docker_statuses(project_name: str) -> list[ServiceStatus]:
    """Try to list Docker containers for the Overleaf compose project."""
    try:
        import docker  # type: ignore
        client = docker.from_env()
        containers = client.containers.list(all=True)
        results = []
        for c in containers:
            labels = c.labels or {}
            compose_project = labels.get("com.docker.compose.project", "")
            if project_name.lower() in compose_project.lower() or project_name.lower() in c.name.lower():
                results.append(
                    ServiceStatus(
                        name=c.name,
                        status="online" if c.status == "running" else "offline",
                        detail=f"Estado Docker: {c.status}",
                        source="docker",
                    )
                )
        return results
    except Exception as exc:
        logger.debug("Docker status check failed (expected if Docker not available): %s", exc)
        return []


def _tcp_statuses(mongo_uri: str) -> list[ServiceStatus]:
    """Fall back to simple TCP port checks."""
    statuses = []

    # MongoDB
    try:
        parsed = urlparse(mongo_uri)
        host = parsed.hostname or "localhost"
        port = parsed.port or 27017
        ok = _check_tcp(host, port)
        statuses.append(ServiceStatus(
            name="MongoDB (Overleaf)",
            status="online" if ok else "offline",
            detail=f"{host}:{port}",
            source="tcp",
        ))
    except Exception as exc:
        logger.debug("MongoDB TCP check error: %s", exc)

    # Overleaf web (common ports)
    for port in (80, 443, 8080):
        ok = _check_tcp("localhost", port, timeout=1.0)
        if ok:
            statuses.append(ServiceStatus(
                name=f"Overleaf Web (:{port})",
                status="online",
                detail=f"Puerto {port} responde",
                source="tcp",
            ))
            break
    else:
        statuses.append(ServiceStatus(
            name="Overleaf Web",
            status="offline",
            detail="No se detectó Overleaf en puertos 80/443/8080",
            source="tcp",
        ))

    return statuses


def _mock_statuses() -> list[ServiceStatus]:
    """Last-resort fallback: return unknown statuses so UI still renders."""
    return [
        ServiceStatus(
            name="MongoDB (Overleaf)",
            status="unknown",
            detail="No se pudo verificar (Docker ni TCP disponibles)",
            source="mock",
        ),
        ServiceStatus(
            name="Overleaf Web",
            status="unknown",
            detail="No se pudo verificar",
            source="mock",
        ),
    ]


def get_service_statuses() -> list[ServiceStatus]:
    """
    Return list of ServiceStatus objects.
    Tries: Docker → TCP → mock (in that order).
    Never raises — always returns something renderable.
    """
    project = current_app.config.get("OVERLEAF_COMPOSE_PROJECT", "sharelatex")
    mongo_uri = current_app.config.get("MONGO_URI", "mongodb://localhost:27017/sharelatex")

    # 1. Try Docker
    docker_results = _docker_statuses(project)
    if docker_results:
        return docker_results

    # 2. Try TCP
    tcp_results = _tcp_statuses(mongo_uri)
    if tcp_results:
        return tcp_results

    # 3. Mock fallback
    return _mock_statuses()
