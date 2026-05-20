"""
service/system_checks.py
-------------------------
Lightweight connectivity checks for PostgreSQL, MongoDB, and Docker.
"""
from __future__ import annotations

from flask import current_app
from sqlalchemy import text

from app.config.extensions import db


def _check_postgresql() -> dict[str, str]:
    try:
        db.session.execute(text("SELECT 1"))
        return {"name": "PostgreSQL", "status": "ok", "detail": "Conexion correcta"}
    except Exception as exc:
        return {"name": "PostgreSQL", "status": "error", "detail": str(exc)[:120]}


def _check_mongodb() -> dict[str, str]:
    try:
        uri = current_app.config.get("MONGO_URI", "")
        if not uri:
            return {"name": "MongoDB / Overleaf", "status": "warn",
                    "detail": "MONGO_URI no configurada"}
        from pymongo import MongoClient
        client = MongoClient(uri, serverSelectionTimeoutMS=3000)
        client.admin.command("ping")
        client.close()
        return {"name": "MongoDB / Overleaf", "status": "ok", "detail": "Conexion correcta"}
    except Exception as exc:
        return {"name": "MongoDB / Overleaf", "status": "warn", "detail": str(exc)[:120]}


def _check_docker() -> dict[str, str]:
    try:
        import docker
        client = docker.from_env()
        client.ping()
        client.close()
        return {"name": "Docker", "status": "ok", "detail": "Daemon accesible"}
    except ImportError:
        return {"name": "Docker", "status": "warn", "detail": "SDK no disponible"}
    except Exception as exc:
        return {"name": "Docker", "status": "warn", "detail": str(exc)[:120]}


def check_system_status() -> list[dict[str, str]]:
    """Run all service checks."""
    return [_check_postgresql(), _check_mongodb(), _check_docker()]
