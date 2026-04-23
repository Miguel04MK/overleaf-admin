"""
seed_overleaf_mongo.py
======================
Inserts realistic test data directly into Overleaf CE's MongoDB (sharelatex db).

What it creates
---------------
  - 8 test users  (different roles, names, signup dates)
  - 15 projects   (various owners, some shared, different sizes)
  - Collaboration links between users and projects

Usage
-----
  cd overleaf-admin
  venv\\Scripts\\python.exe scripts/seed_overleaf_mongo.py

Requirements
------------
  - Overleaf CE must be running (MongoDB accessible on localhost:27017)
  - pymongo and bcrypt must be installed in the venv
      pip install pymongo bcrypt

IMPORTANT
---------
  This script inserts into Overleaf's own MongoDB.  It will NOT break
  existing users/projects — it only inserts new documents.  Existing
  data is left untouched.  Re-running the script is idempotent: it
  skips documents whose email/name already exists.

Overleaf CE version notes
--------------------------
  Tested against Overleaf CE / sharelatex image 4.x / 5.x.
  Field names used: email, first_name, last_name, isAdmin, hashedPassword,
  signUpDate, lastLoggedIn, loginCount, holdingAccount, features,
  collaberator_refs, readOnly_refs, owner_ref, rootFolder, created,
  lastUpdated, lastUpdatedBy, name, publicAccesLevel, active.
  If your version uses different field names, adjust the dicts below.
"""

import sys
import random
import hashlib
from datetime import datetime, timedelta, timezone
from bson import ObjectId

try:
    from pymongo import MongoClient
except ImportError:
    print("ERROR: pymongo not installed. Run: pip install pymongo")
    sys.exit(1)

try:
    import bcrypt
except ImportError:
    print("ERROR: bcrypt not installed. Run: pip install bcrypt")
    sys.exit(1)

# ---------------------------------------------------------------------------
# Config
# ---------------------------------------------------------------------------
MONGO_URI  = "mongodb://localhost:27017/sharelatex?directConnection=true"
DB_NAME    = "sharelatex"
# Default password for all seeded users — change if you want
DEFAULT_PASSWORD = "Test1234!"

# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def now_utc():
    return datetime.now(timezone.utc)

def days_ago(n):
    return now_utc() - timedelta(days=n)

def hash_password(plain: str) -> str:
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")

def make_oid():
    return ObjectId()

def random_tex_size():
    """Simulate a binary attachment size (0-5 MB in bytes)."""
    return random.randint(0, 5 * 1024 * 1024)

def make_root_folder(n_files=1):
    """Build a minimal rootFolder structure Overleaf expects."""
    docs = [{"_id": make_oid(), "name": "main.tex", "rev": 1}]
    file_refs = []
    # Add some binary file refs to simulate size
    for i in range(n_files):
        file_refs.append({
            "_id": make_oid(),
            "name": f"figure_{i+1}.pdf",
            "size": random.randint(50_000, 2_000_000),
            "created": days_ago(random.randint(1, 60)),
        })
    return [{
        "_id": make_oid(),
        "name": "rootFolder",
        "docs": docs,
        "fileRefs": file_refs,
        "folders": [],
    }]

def random_token(length=12):
    return hashlib.md5(str(make_oid()).encode()).hexdigest()[:length]

def make_project_tokens():
    return {
        "readOnly":          random_token(12),
        "readAndWrite":      random_token(12),
        "readAndWritePrefix": random_token(6),
    }

def default_features():
    return {
        "collaborators":   -1,
        "versioning":      True,
        "dropbox":         False,
        "github":          False,
        "gitBridge":       False,
        "symbolPalette":   False,
        "compileGroup":    "standard",
        "compileTimeout":  60,
    }

# ---------------------------------------------------------------------------
# Data definitions
# ---------------------------------------------------------------------------

USERS_DATA = [
    {
        "email": "ana.garcia@universidad.es",
        "first_name": "Ana",
        "last_name": "Garcia",
        "isAdmin": False,
        "signup_offset_days": 400,
        "last_login_offset_days": 2,
    },
    {
        "email": "carlos.ruiz@universidad.es",
        "first_name": "Carlos",
        "last_name": "Ruiz",
        "isAdmin": False,
        "signup_offset_days": 380,
        "last_login_offset_days": 5,
    },
    {
        "email": "maria.lopez@universidad.es",
        "first_name": "Maria",
        "last_name": "Lopez",
        "isAdmin": False,
        "signup_offset_days": 300,
        "last_login_offset_days": 1,
    },
    {
        "email": "jorge.martinez@universidad.es",
        "first_name": "Jorge",
        "last_name": "Martinez",
        "isAdmin": False,
        "signup_offset_days": 250,
        "last_login_offset_days": 10,
    },
    {
        "email": "lucia.fernandez@universidad.es",
        "first_name": "Lucia",
        "last_name": "Fernandez",
        "isAdmin": False,
        "signup_offset_days": 180,
        "last_login_offset_days": 3,
    },
    {
        "email": "david.sanchez@universidad.es",
        "first_name": "David",
        "last_name": "Sanchez",
        "isAdmin": False,
        "signup_offset_days": 90,
        "last_login_offset_days": 0,
    },
    {
        "email": "elena.torres@universidad.es",
        "first_name": "Elena",
        "last_name": "Torres",
        "isAdmin": False,
        "signup_offset_days": 60,
        "last_login_offset_days": 7,
    },
    {
        "email": "admin.test@universidad.es",
        "first_name": "Admin",
        "last_name": "Pruebas",
        "isAdmin": True,
        "signup_offset_days": 500,
        "last_login_offset_days": 0,
    },
]

# Projects defined by (owner_index, name, collab_indices, readonly_indices, n_files, created_offset)
PROJECTS_DATA = [
    # Ana's projects
    (0, "TFG - Analisis de Redes Neuronales",          [1, 2],    [],  3, 200),
    (0, "Practicas de Laboratorio Q1",                 [2],       [],  1,  90),
    (0, "Articulo - Aprendizaje Automatico",           [1],       [4], 2, 150),

    # Carlos's projects
    (1, "TFM - Sistemas Distribuidos",                 [0, 3],    [],  4, 180),
    (1, "Notas de clase - Algoritmos",                 [],        [],  0,  30),

    # Maria's projects
    (2, "Tesis Doctoral - Capitulo 1",                 [0],       [],  5, 350),
    (2, "Presentacion Congreso Madrid 2025",           [0, 1],    [],  2,  45),
    (2, "Apuntes Calculo Vectorial",                   [],        [3], 0,  10),

    # Jorge's projects
    (3, "Proyecto Final - Robotica",                   [4, 5],    [],  3, 120),
    (3, "Seminario de Investigacion",                  [2],       [],  1,  60),

    # Lucia's projects
    (4, "TFG - Procesamiento de Lenguaje Natural",     [5, 6],    [0], 2,  70),
    (4, "Manual de Laboratorio",                       [],        [],  0,  20),

    # David's projects
    (5, "Practica de Redes - Informe Final",           [6],       [],  1,  15),

    # Elena's projects
    (6, "Memoria de Practicas en Empresa",             [4],       [],  2,  30),
    (6, "Trabajo de Clase - Historia de la Ciencia",   [],        [],  0,   5),
]

# ---------------------------------------------------------------------------
# Main seed function
# ---------------------------------------------------------------------------

def seed(client):
    db = client[DB_NAME]
    users_col    = db["users"]
    projects_col = db["projects"]

    hashed_pw = hash_password(DEFAULT_PASSWORD)
    print(f"Contrasena por defecto para todos: {DEFAULT_PASSWORD}")
    print()

    # ── Insert users ──────────────────────────────────────────────────────
    print("=== Creando usuarios ===")
    inserted_users = []   # list of inserted user docs (with _id)

    for ud in USERS_DATA:
        existing = users_col.find_one({"email": ud["email"]})
        if existing:
            print(f"  [SKIP] {ud['email']} — ya existe (id: {existing['_id']})")
            inserted_users.append(existing)
            continue

        doc = {
            "_id":           make_oid(),
            "email":         ud["email"],
            "first_name":    ud["first_name"],
            "last_name":     ud["last_name"],
            "isAdmin":       ud["isAdmin"],
            "hashedPassword": hashed_pw,
            "signUpDate":    days_ago(ud["signup_offset_days"]),
            "lastLoggedIn":  days_ago(ud["last_login_offset_days"]),
            "loginCount":    random.randint(1, 200),
            "holdingAccount": False,
            "ace": {},
            "features": default_features(),
        }
        users_col.insert_one(doc)
        inserted_users.append(doc)
        role = "ADMIN" if ud["isAdmin"] else "user"
        print(f"  [OK]   {ud['email']} ({role})")

    print()

    # ── Insert projects ───────────────────────────────────────────────────
    print("=== Creando proyectos ===")

    for (owner_idx, name, collab_idxs, readonly_idxs, n_files, created_offset) in PROJECTS_DATA:
        existing = projects_col.find_one({"name": name})
        if existing:
            print(f"  [SKIP] '{name}' — ya existe")
            continue

        owner   = inserted_users[owner_idx]
        collabs = [inserted_users[i]["_id"] for i in collab_idxs]
        reads   = [inserted_users[i]["_id"] for i in readonly_idxs]

        created_dt     = days_ago(created_offset)
        last_updated   = created_dt + timedelta(days=random.randint(1, min(created_offset, 30)))

        doc = {
            "_id":                make_oid(),
            "name":               name,
            "owner_ref":          owner["_id"],
            "collaberator_refs":  collabs,
            "readOnly_refs":      reads,
            "rootFolder":         make_root_folder(n_files),
            "publicAccesLevel":   "private",
            "spellCheckLanguage": "es",
            "tokens":             make_project_tokens(),
            "created":            created_dt,
            "lastUpdated":        last_updated,
            "lastUpdatedBy":      owner["_id"],
            "active":             True,
            "__v":                0,
        }
        projects_col.insert_one(doc)

        collab_emails = [inserted_users[i]["email"].split("@")[0] for i in collab_idxs]
        ro_emails     = [inserted_users[i]["email"].split("@")[0] for i in readonly_idxs]
        info = ""
        if collab_emails:
            info += f" | colaboradores: {', '.join(collab_emails)}"
        if ro_emails:
            info += f" | solo-lectura: {', '.join(ro_emails)}"
        print(f"  [OK]   '{name}' (propietario: {owner['email'].split('@')[0]}{info})")

    print()

    # ── Summary ───────────────────────────────────────────────────────────
    print("=== Resumen final ===")
    print(f"  Usuarios en DB : {users_col.count_documents({})}")
    print(f"  Proyectos en DB: {projects_col.count_documents({})}")
    print()
    print("Sincroniza ahora desde la plataforma admin para ver los datos.")


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    print("Conectando a MongoDB...")
    try:
        client = MongoClient(
            MONGO_URI,
            serverSelectionTimeoutMS=5000,
            connectTimeoutMS=5000,
            directConnection=True,
        )
        client.admin.command("ping")
        print("Conexion OK\n")
    except Exception as e:
        print(f"ERROR: no se puede conectar a MongoDB: {e}")
        print()
        print("Asegurate de que Overleaf CE esta corriendo:")
        print("  wsl -> cd ~/overleaf/toolkit -> bin/up")
        sys.exit(1)

    seed(client)
    client.close()
