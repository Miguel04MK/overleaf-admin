"""
scripts/seed_overleaf.py
------------------------
Populates Overleaf CE with sample users and projects for testing.

STRATEGY (honest documentation):
─────────────────────────────────
Overleaf CE does NOT have a stable public CLI for creating users/projects.
The toolkit provides limited admin commands that vary by version.

This script uses TWO approaches in order of preference:

  A) Overleaf toolkit admin script (real, recommended):
     ~/overleaf/toolkit/bin/run-script-runner create-user
     This is the officially supported method in some CE versions.
     If it fails or is not available, falls back to B.

  B) Direct MongoDB insertion (fallback):
     Inserts user documents directly into the 'users' collection.
     WARNING: passwords inserted this way use bcrypt hashing.
     Projects created this way are minimal metadata stubs.
     This works for populating the sync data but users WON'T be
     able to log into Overleaf with these accounts unless
     the password hash is correct for the installed version.

LIMITATION:
  Creating full functional Overleaf projects via direct MongoDB
  insert is complex and version-dependent. This script creates
  metadata-only records sufficient for testing the sync pipeline.
  For real LaTeX project files, use the Overleaf web UI.

Usage:
    python scripts/seed_overleaf.py

  From WSL (recommended for approach A):
    cd ~/overleaf/toolkit
    python /path/to/scripts/seed_overleaf.py
"""
import sys
import os
import subprocess
import hashlib
from datetime import datetime, timezone, timedelta
from bson import ObjectId

sys.path.insert(0, os.path.join(os.path.dirname(__file__), ".."))
from dotenv import load_dotenv
load_dotenv()

MONGO_URI = os.getenv("MONGO_URI", "mongodb://localhost:27017/sharelatex")
MONGO_DB  = os.getenv("MONGO_DB", "sharelatex")

# Sample data
SAMPLE_USERS = [
    {"email": "alice@example.com",  "first_name": "Alice",  "last_name": "García",   "is_admin": False},
    {"email": "bob@example.com",    "first_name": "Bob",    "last_name": "Martínez", "is_admin": False},
    {"email": "carol@example.com",  "first_name": "Carol",  "last_name": "López",    "is_admin": True},
    {"email": "david@example.com",  "first_name": "David",  "last_name": "Sánchez",  "is_admin": False},
    {"email": "eva@example.com",    "first_name": "Eva",    "last_name": "Fernández","is_admin": False},
]

SAMPLE_PROJECTS = [
    {"name": "TFG — Ingeniería Informática"},
    {"name": "Apuntes de Cálculo I"},
    {"name": "Artículo IEEE — Redes Neuronales"},
    {"name": "Memoria de Prácticas"},
    {"name": "Presentación Defensa TFG"},
    {"name": "Plantilla CV LaTeX"},
]


def _make_bcrypt_hash(password: str) -> str:
    """
    Generate a bcrypt hash for the given password.
    Requires the 'bcrypt' package.
    """
    try:
        import bcrypt
        return bcrypt.hashpw(password.encode(), bcrypt.gensalt()).decode()
    except ImportError:
        # Fallback: sha256 hex — users CANNOT log in with this,
        # but it satisfies the field requirement for sync testing.
        print("  [!] bcrypt no disponible. Los usuarios no podrán hacer login en Overleaf.")
        return "INVALID_HASH_" + hashlib.sha256(password.encode()).hexdigest()[:16]


def seed_via_mongo():
    """Fallback: insert documents directly into MongoDB."""
    print("\n[APPROACH B] Inserción directa en MongoDB...")
    try:
        from pymongo import MongoClient
        client = MongoClient(MONGO_URI, serverSelectionTimeoutMS=5000)
        client.admin.command("ping")
        db = client[MONGO_DB]

        now = datetime.now(timezone.utc)
        created_user_ids = {}

        print("\n  Insertando usuarios...")
        for i, u in enumerate(SAMPLE_USERS):
            existing = db["users"].find_one({"email": u["email"]})
            if existing:
                print(f"    [SKIP] {u['email']} ya existe.")
                created_user_ids[u["email"]] = existing["_id"]
                continue

            doc = {
                "_id": ObjectId(),
                "email": u["email"],
                "first_name": u["first_name"],
                "last_name": u["last_name"],
                "isAdmin": u["is_admin"],
                "hashedPassword": _make_bcrypt_hash("Test1234!"),
                "signUpDate": now - timedelta(days=30 - i * 5),
                "lastLoggedIn": now - timedelta(days=i),
                "loginCount": i * 3,
                "features": {},
                "ace": {},
            }
            db["users"].insert_one(doc)
            created_user_ids[u["email"]] = doc["_id"]
            print(f"    [OK] {u['email']}")

        print("\n  Insertando proyectos...")
        user_emails = list(created_user_ids.keys())

        for i, p in enumerate(SAMPLE_PROJECTS):
            existing = db["projects"].find_one({"name": p["name"]})
            if existing:
                print(f"    [SKIP] Proyecto '{p['name']}' ya existe.")
                continue

            owner_email = user_emails[i % len(user_emails)]
            owner_id = created_user_ids[owner_email]

            doc = {
                "_id": ObjectId(),
                "name": p["name"],
                "owner_ref": owner_id,
                "collaberator_refs": [],
                "readOnly_refs": [],
                "created": now - timedelta(days=20 - i * 3),
                "lastUpdated": now - timedelta(days=i),
                "active": True,
                "publicAccesLevel": "private",
                "tokens": {},
                "version": 1,
                "rootDoc_id": ObjectId(),
                "rootFolder": [],
            }
            db["projects"].insert_one(doc)
            print(f"    [OK] '{p['name']}' (propietario: {owner_email})")

        client.close()
        print("\n[OK] Datos de prueba insertados en MongoDB.")
        print("     Ejecuta la sincronización para cargarlos en PostgreSQL:")
        print("     python scripts/sync_manual.py")

    except Exception as e:
        print(f"\n[ERROR] No se pudo insertar datos en MongoDB: {e}")
        print("        Verifica que Overleaf CE esté corriendo y MONGO_URI sea correcto.")
        sys.exit(1)


def try_toolkit_approach() -> bool:
    """
    Approach A: use Overleaf toolkit's create-user script.
    Returns True if successful, False if not available.
    """
    toolkit_path = os.path.expanduser("~/overleaf/toolkit")
    script = os.path.join(toolkit_path, "bin", "run-script-runner")

    if not os.path.exists(script):
        print(f"  [!] Script de toolkit no encontrado en: {script}")
        print(f"      (Esto es normal si ejecutas desde Windows/Docker)")
        return False

    print(f"\n[APPROACH A] Usando Overleaf toolkit: {script}")
    print("  Nota: este método es interactivo. Puede requerir confirmar opciones.")

    for u in SAMPLE_USERS:
        cmd = [script, "create-user", "--email", u["email"]]
        try:
            result = subprocess.run(cmd, capture_output=True, text=True, timeout=30)
            if result.returncode == 0:
                print(f"  [OK] {u['email']}")
            else:
                print(f"  [!] {u['email']}: {result.stderr.strip()[:100]}")
        except Exception as e:
            print(f"  [!] Error ejecutando toolkit: {e}")
            return False

    return True


def main():
    print("=" * 60)
    print("  Overleaf Admin — Seed de datos de prueba")
    print("=" * 60)
    print(f"  MongoDB: {MONGO_URI}")
    print()
    print("IMPORTANTE: Este script inserta datos de prueba en Overleaf CE.")
    print("Los usuarios tendrán contraseña: Test1234!")
    print("(Solo válida para login en Overleaf si se usa la approach A)")
    print()

    resp = input("¿Continuar? [s/N] ").strip().lower()
    if resp not in ("s", "si", "sí", "y", "yes"):
        print("Cancelado.")
        sys.exit(0)

    # Try toolkit first (only works from WSL with toolkit installed)
    toolkit_ok = try_toolkit_approach()

    if not toolkit_ok:
        print("\n  → Usando inserción directa en MongoDB (approach B)...")
        seed_via_mongo()


if __name__ == "__main__":
    main()
