"""
scripts/diagnose_overleaf.py
-----------------------------
Diagnoses connectivity and data availability for Overleaf CE.

Checks:
  1. MongoDB reachability (TCP + ping)
  2. Database and collection existence
  3. Document counts in users and projects collections
  4. Sample field names (to detect version differences)
  5. PostgreSQL connectivity

Usage:
    python scripts/diagnose_overleaf.py
"""
import sys
import os
import socket

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))

from dotenv import load_dotenv
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/sharelatex")
MONGO_DB  = os.getenv("MONGO_DB", "sharelatex")
DB_URL    = os.getenv("DATABASE_URL", "")


def section(title: str) -> None:
    print(f"\n{'─' * 60}")
    print(f"  {title}")
    print('─' * 60)


def check(label: str, ok: bool, detail: str = "") -> None:
    icon = "✓" if ok else "✗"
    status = "OK" if ok else "FALLO"
    line = f"  [{icon}] {label:40s} {status}"
    if detail:
        line += f"  ({detail})"
    print(line)


def main():
    print("=" * 60)
    print("  Overleaf Admin — Diagnóstico de conexión")
    print("=" * 60)

    # ── 1. MongoDB TCP ──────────────────────────────────────────
    section("1. MongoDB — conexión TCP")

    from urllib.parse import urlparse
    parsed = urlparse(MONGO_URI)
    host = parsed.hostname or "localhost"
    port = parsed.port or 27017
    print(f"  URI: {MONGO_URI}")
    print(f"  Host: {host}  Puerto: {port}")

    tcp_ok = False
    try:
        with socket.create_connection((host, port), timeout=3):
            tcp_ok = True
    except OSError as e:
        print(f"  [!] TCP error: {e}")
    check("TCP al puerto MongoDB", tcp_ok,
          "Si falla, Overleaf puede no estar corriendo en WSL")

    # ── 2. MongoDB ping ─────────────────────────────────────────
    section("2. MongoDB — ping y colecciones")

    mongo_ok = False
    users_count = 0
    projects_count = 0
    user_sample_fields = []
    project_sample_fields = []

    try:
        from pymongo import MongoClient
        from pymongo.errors import ServerSelectionTimeoutError

        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=4000)
        client.admin.command("ping")
        mongo_ok = True
        check("MongoDB ping", True)

        db = client[MONGO_DB]
        collections = db.list_collection_names()
        check(f"Base de datos '{MONGO_DB}' accesible", True,
              f"colecciones: {', '.join(collections[:8])}")

        # Users
        users_count = db["users"].count_documents({})
        check("Colección 'users' existe", "users" in collections,
              f"{users_count} documentos")

        if users_count > 0:
            sample = db["users"].find_one({})
            user_sample_fields = [k for k in sample.keys() if k != "_id"]
            print(f"  [i] Campos en users (muestra): {user_sample_fields}")

            # Check expected fields
            for field in ["email", "isAdmin", "signUpDate", "first_name"]:
                present = field in sample
                print(f"      {'✓' if present else '?'} {field}: {'presente' if present else 'AUSENTE (puede ser normal según versión)'}")

        # Projects
        projects_count = db["projects"].count_documents({})
        check("Colección 'projects' existe", "projects" in collections,
              f"{projects_count} documentos")

        if projects_count > 0:
            sample = db["projects"].find_one({})
            project_sample_fields = [k for k in sample.keys() if k != "_id"]
            print(f"  [i] Campos en projects (muestra): {project_sample_fields}")

            for field in ["name", "owner_ref", "created", "lastUpdated"]:
                present = field in sample
                print(f"      {'✓' if present else '?'} {field}: {'presente' if present else 'AUSENTE (puede ser normal según versión)'}")

        client.close()

    except Exception as e:
        check("MongoDB ping", False, str(e))
        print(f"\n  [!] No se pudo conectar a MongoDB.")
        print(f"      Asegúrate de que Overleaf CE esté corriendo en WSL:")
        print(f"      $ cd ~/overleaf/toolkit && ./bin/up")
        print(f"      Y que MongoDB esté expuesto en el puerto {port}.")
        print(f"\n      Si usas Docker en WSL, puede que necesites:")
        print(f"      $ docker ps  (busca el contenedor sharelatex o mongo)")
        print(f"      $ docker inspect <container> | grep IPAddress")

    # ── 3. PostgreSQL ───────────────────────────────────────────
    section("3. PostgreSQL — conexión")
    print(f"  URL: {DB_URL[:60]}{'...' if len(DB_URL) > 60 else ''}")

    pg_ok = False
    try:
        import psycopg2
        conn = psycopg2.connect(DB_URL, connect_timeout=3)
        conn.close()
        pg_ok = True
    except Exception as e:
        print(f"  [!] Error PostgreSQL: {e}")
    check("PostgreSQL accesible", pg_ok,
          "Si falla: docker compose up -d db")

    # ── 4. Resumen ──────────────────────────────────────────────
    section("4. Resumen")
    if mongo_ok and pg_ok:
        print(f"  [✓] Todo listo para sincronizar.")
        print(f"      Usuarios en Overleaf:  {users_count}")
        print(f"      Proyectos en Overleaf: {projects_count}")
        print(f"\n  Ejecuta la sincronización con:")
        print(f"      python scripts/sync_manual.py")
    elif pg_ok and not mongo_ok:
        print(f"  [!] PostgreSQL OK, pero MongoDB no accesible.")
        print(f"      La plataforma puede abrirse, pero la sincronización fallará.")
        print(f"      Verifica que Overleaf CE esté levantado en WSL.")
    elif mongo_ok and not pg_ok:
        print(f"  [!] MongoDB OK, pero PostgreSQL no accesible.")
        print(f"      Levanta PostgreSQL: docker compose up -d db")
    else:
        print(f"  [✗] Ninguna base de datos está accesible.")
        print(f"      Revisa la configuración en .env y los servicios Docker.")

    print()


if __name__ == "__main__":
    main()
