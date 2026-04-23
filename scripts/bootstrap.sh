#!/usr/bin/env bash
# =============================================================
# bootstrap.sh
# Prepara el entorno para overleaf-admin de forma idempotente:
#   1. Levanta PostgreSQL (docker-compose de este proyecto) si no esta.
#   2. Levanta Overleaf CE (toolkit) si no esta.
#   3. Inicializa el replica set de MongoDB si no lo esta.
#   4. Inserta el seed de usuarios/proyectos si la DB esta vacia.
#
# Uso:
#   bash scripts/bootstrap.sh
# =============================================================
set -e

PROJECT_DIR="$(cd "$(dirname "$0")/.." && pwd)"
TOOLKIT_DIR="${OVERLEAF_TOOLKIT_DIR:-/home/migue/overleaf-toolkit}"
SEED_FILE="$PROJECT_DIR/scripts/seed_overleaf.js"

echo "[1/4] PostgreSQL (overleaf-admin)..."
(cd "$PROJECT_DIR" && docker compose up -d db >/dev/null 2>&1) || true

echo "[2/4] Overleaf CE toolkit..."
if [ -d "$TOOLKIT_DIR" ]; then
  (cd "$TOOLKIT_DIR" && bin/up -d >/dev/null 2>&1) || true
else
  echo "  (skip: toolkit dir not found at $TOOLKIT_DIR)"
fi

echo "[3/4] MongoDB replica set..."
# Esperar a que mongo este arriba
for i in {1..30}; do
  if docker exec mongo mongosh --quiet --eval 'db.runCommand({ping:1}).ok' >/dev/null 2>&1; then
    break
  fi
  sleep 1
done

RS_OK=$(docker exec mongo mongosh --quiet --eval 'try { rs.status().ok } catch(e) { print("0") }' 2>/dev/null | tr -d '[:space:]')
if [ "$RS_OK" != "1" ]; then
  echo "  Inicializando replica set..."
  docker exec mongo mongosh --quiet --eval 'rs.initiate({ _id: "overleaf", members: [{ _id: 0, host: "mongo:27017" }] })' >/dev/null
  # Esperar a que sea PRIMARY
  for i in {1..30}; do
    STATE=$(docker exec mongo mongosh --quiet --eval 'try { rs.status().members[0].stateStr } catch(e) { "X" }' 2>/dev/null | tr -d '[:space:]')
    [ "$STATE" = "PRIMARY" ] && break
    sleep 1
  done
else
  echo "  Replica set ya inicializado."
fi

echo "[4/4] Seed MongoDB..."
USER_COUNT=$(docker exec mongo mongosh sharelatex --quiet --eval 'db.users.countDocuments({})' 2>/dev/null | tr -d '[:space:]')
if [ "${USER_COUNT:-0}" -lt 10 ]; then
  echo "  Insertando seed (usuarios y proyectos)..."
  docker cp "$SEED_FILE" mongo:/tmp/seed.js
  docker exec mongo mongosh --quiet /tmp/seed.js
else
  echo "  Ya hay $USER_COUNT usuarios. Seed omitido."
fi

echo ""
echo "[OK] Entorno listo."
echo "     - Panel:    python run.py  ->  http://localhost:5000"
echo "     - Overleaf: http://localhost/"
