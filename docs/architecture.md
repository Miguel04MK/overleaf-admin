# Arquitectura del sistema

## Visión general

```
┌─────────────────────────────────────────────────────────────┐
│                    Overleaf CE (WSL)                        │
│  ┌──────────────┐    ┌───────────────────────────────────┐  │
│  │   Overleaf   │    │       MongoDB (sharelatex)         │  │
│  │   Web App    │───▶│  users / projects / docs / ...     │  │
│  └──────────────┘    └───────────────┬───────────────────┘  │
└─────────────────────────────────────┼─────────────────────┘
                                       │ pymongo (TCP 27017)
┌─────────────────────────────────────▼─────────────────────┐
│                Overleaf Admin Platform                      │
│                                                             │
│  ┌─────────────────────────────────────────────────────┐   │
│  │                   ETL / Sync                         │   │
│  │  adapter.py → extractor.py → transformer → loader    │   │
│  └──────────────────────────┬──────────────────────────┘   │
│                              │ SQLAlchemy                   │
│  ┌───────────────────────────▼──────────────────────────┐  │
│  │              PostgreSQL (overleaf_admin)               │  │
│  │  admin_users / overleaf_users / overleaf_projects     │  │
│  │  project_members / sync_runs / audit_logs             │  │
│  └───────────────────────────┬──────────────────────────┘  │
│                              │                              │
│  ┌───────────────────────────▼──────────────────────────┐  │
│  │            Flask + Jinja2 + Bootstrap                  │  │
│  │  auth / dashboard / users / projects / audit / sync   │  │
│  └──────────────────────────────────────────────────────┘  │
└────────────────────────────────────────────────────────────┘
         ▲
         │ HTTP (navegador)
         └── Admin local
```

## Capas

| Capa | Módulo | Responsabilidad |
|------|--------|-----------------|
| Adaptador | `app/sync/adapter.py` | Conexión y ping a MongoDB |
| Extractor | `app/sync/extractor.py` | Leer y normalizar docs de Mongo |
| Transformer | `app/sync/transformer.py` | Convertir a objetos ORM |
| Loader | `app/sync/loader.py` | Upsert idempotente en PostgreSQL |
| Runner | `app/sync/runner.py` | Orquestador del pipeline ETL |
| Servicios | `app/services/` | Lógica de negocio (sin acceso directo a BD) |
| Repositorios | `app/repositories/` | Consultas SQL reutilizables |
| Blueprints | `app/auth/`, `app/dashboard/`, ... | Rutas HTTP y renderizado |
| Modelos | `app/models/` | Esquema PostgreSQL vía SQLAlchemy |

## Modelo de datos PostgreSQL

```
admin_users
  id, username, email, password_hash, is_active, created_at, last_login_at

overleaf_users
  id, overleaf_id (unique), email, first_name, last_name,
  is_admin, signup_date, last_login_at, synced_at

overleaf_projects
  id, overleaf_id (unique), name, owner_id (FK→overleaf_users),
  owner_overleaf_id, created_at, last_updated_at, synced_at

project_members
  id, project_id (FK), user_id (FK), role, synced_at
  UNIQUE(project_id, user_id)

sync_runs
  id, started_at, finished_at, status, users_found, users_synced,
  projects_found, projects_synced, triggered_by, message

audit_logs
  id, actor, action, detail, level, ip_address, created_at
```

## Decisiones de diseño

- **PostgreSQL en lugar de MongoDB**: modelo relacional claro, mejores joins
  para métricas, desacoplamiento de la estructura interna de Overleaf.
- **Sync idempotente**: upsert por `overleaf_id`; se puede re-ejecutar sin
  duplicar datos.
- **Adaptador aislado**: si Overleaf cambia el nombre de colecciones o campos,
  solo se toca `adapter.py` y `extractor.py`.
- **Fallback de estado de servicios**: Docker → TCP → mock. El dashboard
  siempre renderiza aunque no haya información real.
