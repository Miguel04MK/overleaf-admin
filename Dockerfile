# syntax=docker/dockerfile:1
# ──────────────────────────────────────────────────────────────────────────────
# Overleaf Admin Platform — imagen de producción
#
# Diseño:
#   - Python 3.12-slim como base (compatible con SQLAlchemy 2.0 y SQLite 3 nuevo).
#   - Stage único: la app no requiere compilar nada nativo.
#   - Usuario no-root (`app`) para reducir superficie de ataque.
#   - Gunicorn como WSGI server (1 worker, ver punto crítico en docs).
# ──────────────────────────────────────────────────────────────────────────────
FROM python:3.12-slim

# Variables de entorno por defecto
ENV PYTHONDONTWRITEBYTECODE=1 \
    PYTHONUNBUFFERED=1 \
    PIP_NO_CACHE_DIR=1 \
    PIP_DISABLE_PIP_VERSION_CHECK=1 \
    FLASK_APP=run.py

# Dependencias del sistema mínimas: cliente Postgres para healthcheck y curl para debug.
RUN apt-get update \
    && apt-get install -y --no-install-recommends \
        postgresql-client \
        curl \
    && rm -rf /var/lib/apt/lists/*

WORKDIR /app

# Instalación de dependencias primero (capa cacheable)
COPY requirements.txt .
RUN pip install --upgrade pip \
    && pip install -r requirements.txt

# Código de la aplicación
COPY . .

# Permisos del entrypoint
RUN chmod +x /app/docker-entrypoint.sh

# Usuario no-root
RUN useradd --create-home --shell /bin/bash app \
    && chown -R app:app /app
USER app

EXPOSE 8000

ENTRYPOINT ["/app/docker-entrypoint.sh"]
CMD ["gunicorn", "-w", "1", "-b", "0.0.0.0:8000", "--access-logfile", "-", "--error-logfile", "-", "run:app"]
