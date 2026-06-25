#!/bin/bash
# ──────────────────────────────────────────────────────────────────────────────
# Overleaf Admin Platform — entrypoint del contenedor
#
# Espera a que Postgres esté listo, aplica migraciones Alembic y lanza el CMD
# pasado por Docker (por defecto: gunicorn con 1 worker).
# ──────────────────────────────────────────────────────────────────────────────
set -e

PG_HOST="${POSTGRES_HOST:-db}"
PG_PORT="${POSTGRES_PORT:-5432}"
PG_USER="${POSTGRES_USER:-overleaf_admin}"
PG_DB="${POSTGRES_DB:-overleaf_admin}"

# ── 1. Esperar a Postgres ────────────────────────────────────────────────────
echo "[entrypoint] Esperando a PostgreSQL en ${PG_HOST}:${PG_PORT}..."
RETRIES=30
until pg_isready -h "$PG_HOST" -p "$PG_PORT" -U "$PG_USER" -d "$PG_DB" -q; do
    RETRIES=$((RETRIES - 1))
    if [ $RETRIES -le 0 ]; then
        echo "[entrypoint] ERROR: PostgreSQL no respondio tras 30 intentos." >&2
        exit 1
    fi
    sleep 1
done
echo "[entrypoint] PostgreSQL OK."

# ── 2. Aplicar migraciones Alembic ───────────────────────────────────────────
echo "[entrypoint] Aplicando migraciones (flask db upgrade)..."
flask db upgrade

# ── 3. Lanzar el CMD (gunicorn por defecto) ──────────────────────────────────
echo "[entrypoint] Arrancando: $*"
exec "$@"
