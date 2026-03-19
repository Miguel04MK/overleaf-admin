"""
scripts/sync_manual.py
----------------------
Runs a manual ETL synchronization from Overleaf CE MongoDB → PostgreSQL.
Execute this from the command line when you want to sync outside the web UI.

Usage:
    python scripts/sync_manual.py

Prerequisites:
    - PostgreSQL running and migrated (flask db upgrade)
    - .env configured with DATABASE_URL and MONGO_URI
    - Overleaf CE running in WSL with MongoDB accessible
"""
import sys
import os

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

from app import create_app
from app.sync.runner import run_sync


def main():
    print("=" * 60)
    print("  Overleaf Admin — Sincronización manual")
    print("=" * 60)

    app = create_app()

    print(f"[INFO] MongoDB URI:    {app.config['MONGO_URI']}")
    print(f"[INFO] PostgreSQL URL: {app.config['SQLALCHEMY_DATABASE_URI']}")
    print()

    sync_run = run_sync(app, triggered_by="manual")

    print()
    print(f"[RESULTADO] Estado:    {sync_run.status}")
    print(f"[RESULTADO] Usuarios:  {sync_run.users_synced}/{sync_run.users_found}")
    print(f"[RESULTADO] Proyectos: {sync_run.projects_synced}/{sync_run.projects_found}")
    if sync_run.duration_seconds is not None:
        print(f"[RESULTADO] Duración:  {sync_run.duration_seconds:.2f}s")
    if sync_run.message:
        print(f"[RESULTADO] Mensaje:   {sync_run.message}")
    print()

    if sync_run.status == "error":
        print("[ERROR] La sincronización falló. Revisa los logs y ejecuta:")
        print("        python scripts/diagnose_overleaf.py")
        sys.exit(1)
    else:
        print("[OK] Sincronización completada.")


if __name__ == "__main__":
    main()
