"""
seed_overleaf_mongo_large.py
============================
Heavy seeder for Overleaf CE MongoDB: ~50 users, ~120 projects, lots of
collaboration links and realistic storage sizes.

Design choices
--------------
- **Idempotent**: skips users by email and projects by name on re-runs.
- **Auto-initiates the replica set**: if Mongo answers "not in primary",
  runs ``rs.initiate()`` once. This is what makes data appear lost across
  ``bin/down``/``bin/up`` cycles — the volume IS persisted, but a fresh
  container has no replica-set primary until initiated.
- **Realistic storage**: ``size_bytes`` per project ranges from a few KB
  (notes) to ~50 MB (heavy projects with figures / data files), so dashboard
  metrics (top storage, quota percentage) show meaningful variety.
- **Role mix**: 1 admin user, ~10 "profesor" candidates, the rest "alumno"
  (the admin app assigns roles via the default role + manual changes; this
  script only sets ``isAdmin`` in Overleaf itself).
- **Collaboration patterns**: solo projects, 2–5 collaborator projects,
  read-only viewers, and shared TFG/TFM-style projects across multiple users.

Usage
-----
  venv\\Scripts\\python.exe scripts/seed_overleaf_mongo_large.py

  Optional flags:
    --reset       Drop existing seeded users/projects first.
    --users N     Override target user count (default 50).
    --projects N  Override target project count (default 120).
"""
import argparse
import hashlib
import random
import sys
from datetime import datetime, timedelta, timezone

from bson import ObjectId

try:
    from pymongo import MongoClient
    from pymongo.errors import OperationFailure
except ImportError:
    print("ERROR: pymongo no instalado. pip install pymongo")
    sys.exit(1)

try:
    import bcrypt
except ImportError:
    print("ERROR: bcrypt no instalado. pip install bcrypt")
    sys.exit(1)


MONGO_URI = "mongodb://localhost:27017/sharelatex?directConnection=true"
DB_NAME = "sharelatex"
DEFAULT_PASSWORD = "Test1234!"

# Mongo container hostname inside docker network (for rs.initiate)
MONGO_RS_HOST = "mongo:27017"
MONGO_RS_NAME = "overleaf"

# Deterministic seed → same data every run, easier to compare dashboards.
random.seed(20260514)


# ── Mongo helpers ────────────────────────────────────────────────────────────

def now_utc():
    return datetime.now(timezone.utc)


def days_ago(n):
    return now_utc() - timedelta(days=n)


def ensure_replica_set(client):
    """Initiate the replica set if needed. Safe to call repeatedly."""
    try:
        client.admin.command("ping")
        return
    except OperationFailure as exc:
        msg = str(exc).lower()
        if "not in primary" not in msg and "no primary" not in msg:
            raise
    print("[INFO] Replica set sin primary — ejecutando rs.initiate()…")
    try:
        client.admin.command(
            "replSetInitiate",
            {"_id": MONGO_RS_NAME, "members": [{"_id": 0, "host": MONGO_RS_HOST}]},
        )
    except OperationFailure as exc:
        if "already initialized" in str(exc).lower():
            print("[INFO] Replica set ya inicializado, esperando primary…")
        else:
            raise
    # Esperar a que el primary esté listo
    import time
    for _ in range(20):
        try:
            client.admin.command("ping")
            print("[INFO] Primary disponible.")
            return
        except OperationFailure:
            time.sleep(1)
    print("[WARN] Primary no respondió en 20s. Continuo de todos modos.")


def hash_password(plain):
    return bcrypt.hashpw(plain.encode("utf-8"), bcrypt.gensalt(rounds=10)).decode("utf-8")


def make_oid():
    return ObjectId()


def random_token(length=12):
    return hashlib.md5(str(make_oid()).encode()).hexdigest()[:length]


def make_project_tokens():
    return {
        "readOnly": random_token(12),
        "readAndWrite": random_token(12),
        "readAndWritePrefix": random_token(6),
    }


def default_features():
    return {
        "collaborators": -1,
        "versioning": True,
        "dropbox": False,
        "github": False,
        "gitBridge": False,
        "symbolPalette": False,
        "compileGroup": "standard",
        "compileTimeout": 60,
    }


def make_root_folder(target_bytes):
    """Build a rootFolder with file refs whose sizes sum approximately to
    ``target_bytes``. Overleaf computes project size from file refs."""
    docs = [{"_id": make_oid(), "name": "main.tex", "rev": 1}]
    file_refs = []
    remaining = target_bytes
    idx = 1
    while remaining > 0:
        # Random chunks between 50 KB and 8 MB
        chunk = min(remaining, random.randint(50_000, 8_000_000))
        file_refs.append({
            "_id": make_oid(),
            "name": f"asset_{idx}.{random.choice(['pdf','png','jpg','dat','bib'])}",
            "size": chunk,
            "created": days_ago(random.randint(1, 120)),
        })
        remaining -= chunk
        idx += 1
        if idx > 30:  # safety cap
            break
    return [{
        "_id": make_oid(),
        "name": "rootFolder",
        "docs": docs,
        "fileRefs": file_refs,
        "folders": [],
    }]


# ── Data generation ──────────────────────────────────────────────────────────

FIRST_NAMES = [
    "Ana", "Carlos", "Maria", "Jorge", "Lucia", "David", "Elena", "Pablo",
    "Sara", "Javier", "Laura", "Miguel", "Carmen", "Antonio", "Isabel",
    "Francisco", "Patricia", "Manuel", "Cristina", "Alejandro", "Marta",
    "Rafael", "Beatriz", "Sergio", "Andrea", "Daniel", "Paula", "Adrian",
    "Natalia", "Ruben", "Silvia", "Hugo", "Irene", "Diego", "Nuria",
    "Gonzalo", "Raquel", "Alvaro", "Eva", "Ignacio", "Sofia", "Victor",
    "Clara", "Tomas", "Julia", "Pedro", "Rocio", "Oscar", "Alicia",
    "Fernando",
]
LAST_NAMES = [
    "Garcia", "Lopez", "Martinez", "Sanchez", "Rodriguez", "Fernandez",
    "Perez", "Gomez", "Jimenez", "Ruiz", "Hernandez", "Diaz", "Moreno",
    "Alvarez", "Romero", "Navarro", "Torres", "Dominguez", "Vazquez",
    "Ramos", "Gil", "Serrano", "Blanco", "Suarez", "Castro", "Ortega",
    "Rubio", "Marin", "Sanz", "Iglesias",
]

PROJECT_TEMPLATES = [
    "TFG - {topic}",
    "TFM - {topic}",
    "Tesis Doctoral - {topic}",
    "Articulo - {topic}",
    "Practicas de {topic}",
    "Apuntes de {topic}",
    "Memoria - {topic}",
    "Informe - {topic}",
    "Presentacion {topic}",
    "Notas de clase - {topic}",
    "Proyecto - {topic}",
    "Seminario - {topic}",
    "Manual - {topic}",
    "Trabajo de {topic}",
]
TOPICS = [
    "Redes Neuronales", "Sistemas Distribuidos", "Algoritmos Geneticos",
    "Procesamiento de Lenguaje", "Vision por Computador", "Bases de Datos",
    "Calculo Vectorial", "Algebra Lineal", "Estadistica Bayesiana",
    "Mecanica Cuantica", "Termodinamica", "Electromagnetismo",
    "Biologia Molecular", "Quimica Organica", "Historia Contemporanea",
    "Filosofia de la Ciencia", "Ingenieria de Software", "Compiladores",
    "Robotica Autonoma", "Aprendizaje por Refuerzo", "Criptografia",
    "Redes de Computadores", "Computacion Paralela", "Teoria de la Informacion",
    "Optimizacion Convexa", "Analisis Numerico", "Geometria Diferencial",
    "Topologia Algebraica", "Teoria de Grupos", "Logica Computacional",
    "Sistemas Embebidos", "IoT y Smart Cities", "Ciberseguridad",
    "Realidad Virtual", "Blockchain", "Cloud Computing",
]


def build_users(n_users):
    """Generate user dicts. Indices 0..n-1 are deterministic."""
    users = []
    seen_emails = set()

    # Always include 1 platform admin
    users.append({
        "email": "admin.platform@universidad.es",
        "first_name": "Admin",
        "last_name": "Plataforma",
        "isAdmin": True,
        "signup_offset_days": 730,
        "last_login_offset_days": 0,
    })

    # 10 "profesores": much older signup, larger projects, frequent login
    teacher_count = 10
    for i in range(teacher_count):
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        email = f"prof.{first.lower()}.{last.lower()}@universidad.es"
        if email in seen_emails:
            email = f"prof.{first.lower()}.{last.lower()}{i}@universidad.es"
        seen_emails.add(email)
        users.append({
            "email": email,
            "first_name": first,
            "last_name": last,
            "isAdmin": False,
            "signup_offset_days": random.randint(500, 900),
            "last_login_offset_days": random.randint(0, 14),
        })

    # Rest are "alumnos"
    while len(users) < n_users:
        first = random.choice(FIRST_NAMES)
        last = random.choice(LAST_NAMES)
        # Add a stable disambiguator using current index so emails are unique
        suffix = ""
        base = f"{first.lower()}.{last.lower()}"
        candidate = f"{base}@universidad.es"
        n = 1
        while candidate in seen_emails:
            n += 1
            candidate = f"{base}{n}@universidad.es"
        seen_emails.add(candidate)

        # Some alumnos are "inactivos" (no login > 200 days) — useful for
        # dashboard inactivity rotation card.
        if random.random() < 0.15:
            last_login = random.randint(220, 600)
        else:
            last_login = random.randint(0, 60)

        users.append({
            "email": candidate,
            "first_name": first,
            "last_name": last,
            "isAdmin": False,
            "signup_offset_days": random.randint(60, 500),
            "last_login_offset_days": last_login,
        })
    return users


def build_projects(n_projects, n_users):
    """Generate project tuples (owner_idx, name, collab_idxs, readonly_idxs,
    size_bytes_target, created_offset)."""
    projects = []
    used_names = set()

    # First teacher index range: 1..10 (index 0 is admin)
    teacher_idxs = list(range(1, 11))
    alumno_idxs = list(range(11, n_users))

    for _ in range(n_projects):
        # 70% owned by alumno, 30% by teacher (teachers own bigger / shared)
        if random.random() < 0.3 and teacher_idxs:
            owner = random.choice(teacher_idxs)
            is_teacher = True
        else:
            owner = random.choice(alumno_idxs) if alumno_idxs else random.choice(teacher_idxs)
            is_teacher = False

        # Project name
        for _try in range(20):
            tmpl = random.choice(PROJECT_TEMPLATES)
            name = tmpl.format(topic=random.choice(TOPICS))
            if name not in used_names:
                used_names.add(name)
                break

        # Collaboration: 35% solo, 50% 1-3 collabs, 15% group projects (4-6 collabs)
        r = random.random()
        if r < 0.35:
            n_collabs = 0
        elif r < 0.85:
            n_collabs = random.randint(1, 3)
        else:
            n_collabs = random.randint(4, 6)

        # Read-only viewers (typically 0-2)
        n_readonly = random.choices([0, 1, 2, 3], weights=[55, 25, 15, 5])[0]

        all_pool = [i for i in range(n_users) if i != owner]
        random.shuffle(all_pool)
        collab_idxs = all_pool[:n_collabs]
        readonly_idxs = all_pool[n_collabs:n_collabs + n_readonly]

        # Size: small (notes), medium (papers), large (theses)
        size_class = random.choices(
            ["tiny", "small", "medium", "large", "huge"],
            weights=[20, 30, 25, 18, 7],
        )[0]
        size_bytes = {
            "tiny":   random.randint(20_000, 200_000),
            "small":  random.randint(300_000, 2_500_000),
            "medium": random.randint(3_000_000, 15_000_000),
            "large":  random.randint(20_000_000, 50_000_000),
            "huge":   random.randint(60_000_000, 120_000_000),
        }[size_class]
        # Teachers' projects skew larger
        if is_teacher:
            size_bytes = int(size_bytes * random.uniform(1.2, 2.0))

        created_offset = random.randint(7, 800)
        projects.append((owner, name, collab_idxs, readonly_idxs, size_bytes, created_offset))

    return projects


# ── Insertion ────────────────────────────────────────────────────────────────

def seed(client, n_users, n_projects, reset):
    db = client[DB_NAME]
    users_col = db["users"]
    projects_col = db["projects"]

    if reset:
        print("[RESET] Borrando usuarios y proyectos del seed previo…")
        users_col.delete_many({"email": {"$regex": "@universidad.es$"}})
        projects_col.delete_many({})

    pw = hash_password(DEFAULT_PASSWORD)
    print(f"Contraseña para todos los usuarios sembrados: {DEFAULT_PASSWORD}\n")

    USERS_DATA = build_users(n_users)
    PROJECTS_DATA = build_projects(n_projects, len(USERS_DATA))

    print(f"=== Insertando {len(USERS_DATA)} usuarios ===")
    inserted = []
    for ud in USERS_DATA:
        existing = users_col.find_one({"email": ud["email"]})
        if existing:
            inserted.append(existing)
            continue
        doc = {
            "_id":            make_oid(),
            "email":          ud["email"],
            "first_name":     ud["first_name"],
            "last_name":      ud["last_name"],
            "isAdmin":        ud["isAdmin"],
            "hashedPassword": pw,
            "signUpDate":     days_ago(ud["signup_offset_days"]),
            "lastLoggedIn":   days_ago(ud["last_login_offset_days"]),
            "loginCount":     random.randint(1, 300),
            "holdingAccount": False,
            "ace":            {},
            "features":       default_features(),
        }
        users_col.insert_one(doc)
        inserted.append(doc)
    n_new_users = sum(1 for u in inserted if users_col.count_documents({"_id": u["_id"]}) == 1)
    print(f"  {n_new_users} usuarios insertados/existentes")

    print(f"\n=== Insertando {len(PROJECTS_DATA)} proyectos ===")
    n_new_projects = 0
    n_skipped = 0
    total_bytes = 0
    for (owner_idx, name, collab_idxs, readonly_idxs, size_bytes, created_offset) in PROJECTS_DATA:
        if projects_col.find_one({"name": name}):
            n_skipped += 1
            continue
        owner = inserted[owner_idx]
        created_dt = days_ago(created_offset)
        last_updated = created_dt + timedelta(days=random.randint(1, max(1, min(created_offset, 90))))

        doc = {
            "_id":                make_oid(),
            "name":               name,
            "owner_ref":          owner["_id"],
            "collaberator_refs":  [inserted[i]["_id"] for i in collab_idxs],
            "readOnly_refs":      [inserted[i]["_id"] for i in readonly_idxs],
            "rootFolder":         make_root_folder(size_bytes),
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
        n_new_projects += 1
        total_bytes += size_bytes

    print(f"  {n_new_projects} proyectos insertados, {n_skipped} omitidos (ya existían)")
    if n_new_projects:
        avg_mb = total_bytes / n_new_projects / (1024 * 1024)
        total_mb = total_bytes / (1024 * 1024)
        print(f"  Almacenamiento simulado: {total_mb:.1f} MB total, ~{avg_mb:.1f} MB/proyecto")

    print(f"\n=== Resumen final ===")
    print(f"  Usuarios en Mongo : {users_col.count_documents({})}")
    print(f"  Proyectos en Mongo: {projects_col.count_documents({})}")
    print()
    print("Ejecuta ahora: venv\\Scripts\\python.exe scripts\\sync_manual.py")


# ── Entry point ──────────────────────────────────────────────────────────────

def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--reset", action="store_true",
                    help="Borra usuarios @universidad.es y todos los proyectos antes de sembrar.")
    ap.add_argument("--users", type=int, default=50)
    ap.add_argument("--projects", type=int, default=120)
    args = ap.parse_args()

    print("Conectando a MongoDB…")
    client = MongoClient(
        MONGO_URI,
        serverSelectionTimeoutMS=5000,
        connectTimeoutMS=5000,
        directConnection=True,
    )
    ensure_replica_set(client)
    print("Conexion OK\n")

    seed(client, args.users, args.projects, args.reset)
    client.close()


if __name__ == "__main__":
    main()
