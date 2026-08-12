# Overleaf Admin Platform

Plataforma web de administración y gestión complementaria para **Overleaf Community Edition**.
Desarrollada como Trabajo de Fin de Grado (TFG).

> **Importante:** Esta plataforma NO sustituye a Overleaf.
> Se conecta externamente a Overleaf CE para extraer metadatos y ofrecerlos
> en un panel de administración propio, con PostgreSQL como base de datos.

---

## Stack tecnológico

| Componente | Tecnología |
|---|---|
| Backend | Python 3.12 + Flask 3 |
| Templates | Jinja2 + Bootstrap 5 |
| Base de datos propia | PostgreSQL 16 |
| ORM | SQLAlchemy + Flask-Migrate |
| Conexión a Overleaf | pymongo → MongoDB de Overleaf CE |
| Contenedores | Docker Compose (solo PostgreSQL) |
| Auth | Flask-Login (sesión simple) |

---

## Requisitos previos

- Python 3.11+ instalado en Windows o WSL
- Docker Desktop (para levantar PostgreSQL)
- Overleaf Community Edition instalado en WSL (`~/overleaf/toolkit`)
- Git (opcional)

---

## Instalación paso a paso

### 1. Clonar o descomprimir el proyecto

```bash
cd ~/ruta/al/proyecto
# o simplemente navega a la carpeta overleaf-admin
```

### 2. Crear y activar el entorno virtual

```bash
python -m venv venv

# Windows (PowerShell):
.\venv\Scripts\Activate.ps1

# Windows (CMD):
venv\Scripts\activate.bat

# WSL / Linux:
source venv/bin/activate
```

### 3. Instalar dependencias

```bash
pip install -r requirements.txt
```

### 4. Configurar variables de entorno

```bash
cp .env.example .env
```

Edita `.env` y ajusta al menos:

```dotenv
SECRET_KEY=una-clave-secreta-larga-y-aleatoria
DATABASE_URL=postgresql://overleaf_admin:overleaf_admin_pass@localhost:5432/overleaf_admin
MONGO_URI=mongodb://localhost:27017/sharelatex
```

---

## Levantar PostgreSQL con Docker

```bash
docker compose up -d db
```

Verifica que está corriendo:

```bash
docker compose ps
```

Para usar pgAdmin (interfaz gráfica de PostgreSQL):

```bash
docker compose --profile tools up -d pgadmin
# Abre: http://localhost:5050
# Email: admin@localhost  Contraseña: admin
```

---

## Migraciones de base de datos

### Primera vez (crear tablas):

```bash
flask db init       # Solo la primera vez — crea la carpeta migrations/
flask db migrate -m "Initial schema"
flask db upgrade
```

### Veces posteriores (tras cambios en modelos):

```bash
flask db migrate -m "Descripción del cambio"
flask db upgrade
```

> `FLASK_APP` se detecta automáticamente desde `run.py`.
> Si no, exporta: `export FLASK_APP=run.py`

---

## Crear el usuario administrador por defecto

```bash
python scripts/create_admin.py
```

Credenciales por defecto: **admin / admin**

Para personalizar:

```bash
ADMIN_USERNAME=miadmin ADMIN_PASSWORD=MiContraseña123 python scripts/create_admin.py
```

---

## Arrancar la aplicación

```bash
python run.py
```

Abre el navegador en: **http://127.0.0.1:5000**

---

## Conectar con Overleaf CE en WSL

### ¿Cómo funciona?

Overleaf CE corre en WSL usando Docker Compose (toolkit).
Su MongoDB está expuesto en el puerto `27017` del contenedor Docker.

### Paso 1 — Levantar Overleaf CE en WSL

```bash
# En WSL:
cd ~/overleaf/toolkit
./bin/up
```

### Paso 2 — Verificar que MongoDB es accesible

```bash
# En WSL:
docker ps | grep mongo
# Debe aparecer un contenedor de mongo corriendo

# Opcional — conectar con mongo shell:
docker exec -it sharelatex_mongo_1 mongosh sharelatex
```

### Paso 3 — Configurar MONGO_URI en .env

**Desde Windows (app corriendo en Windows):**

```dotenv
# MongoDB está en WSL, accesible via localhost si hay port-forward,
# o via la IP de WSL (127.0.0.1 suele funcionar con Docker Desktop):
MONGO_URI=mongodb://localhost:27017/sharelatex
```

Si `localhost` no funciona, obtén la IP de WSL:

```powershell
# En PowerShell:
wsl hostname -I
```

Y usa esa IP en `MONGO_URI`.

**Desde WSL (app corriendo en WSL):**

```dotenv
MONGO_URI=mongodb://localhost:27017/sharelatex
```

### Paso 4 — Diagnosticar la conexión

```bash
python scripts/diagnose_overleaf.py
```

Este script comprueba:
- Conectividad TCP al puerto de MongoDB
- Ping a MongoDB
- Existencia de las colecciones `users` y `projects`
- Campos disponibles (detecta diferencias de versión)
- Conectividad a PostgreSQL

---

## Ejecutar la sincronización

### Desde la interfaz web:

1. Abre la sección **Sincronización** en el menú lateral
2. Haz clic en **"Sincronizar ahora"**
3. El proceso corre en segundo plano; refresca la página para ver el resultado

### Desde la línea de comandos:

```bash
python scripts/sync_manual.py
```

### ¿Qué sincroniza?

- Todos los usuarios de la colección `users` de MongoDB
- Todos los proyectos activos de la colección `projects`
- Las relaciones propietario/colaborador entre usuarios y proyectos
- Fechas de creación, última actualización y último acceso (si están disponibles)

Las sincronizaciones son **idempotentes**: se pueden ejecutar repetidamente sin duplicar datos.

---

## Poblar Overleaf con datos de prueba

```bash
python scripts/seed_overleaf.py
```

Este script intenta:
1. Usar el script de toolkit de Overleaf `bin/run-script-runner create-user` (si está en WSL)
2. Si no está disponible, inserta documentos directamente en MongoDB

> Ver `scripts/seed_overleaf.py` para documentación detallada de limitaciones.

---

## Ejecutar los tests

```bash
pip install pytest
python -m pytest tests/ -v
```

Los tests de `tests/test_sync.py` validan la capa ETL usando mocks;
**no requieren** conexión real a MongoDB ni PostgreSQL.

---

## Estructura del proyecto

```
overleaf-admin/
├── app/
│   ├── __init__.py          # App factory
│   ├── config.py            # Configuración por entorno
│   ├── extensions.py        # db, migrate, login_manager
│   ├── models/              # SQLAlchemy models (PostgreSQL)
│   │   ├── admin_user.py
│   │   ├── overleaf_user.py
│   │   ├── overleaf_project.py
│   │   ├── project_member.py
│   │   ├── sync_run.py
│   │   └── audit_log.py
│   ├── services/            # Lógica de negocio
│   ├── repositories/        # Consultas SQL reutilizables
│   ├── sync/                # Pipeline ETL Overleaf → PostgreSQL
│   │   ├── adapter.py       # Conexión MongoDB
│   │   ├── extractor.py     # Extracción de datos (versión-aware)
│   │   ├── transformer.py   # Conversión a modelos ORM
│   │   ├── loader.py        # Upsert en PostgreSQL
│   │   └── runner.py        # Orquestador
│   ├── auth/                # Blueprint: login/logout
│   ├── dashboard/           # Blueprint: dashboard principal
│   ├── users/               # Blueprint: listado usuarios
│   ├── projects/            # Blueprint: listado proyectos
│   ├── audit/               # Blueprint: registro de auditoría
│   ├── sync_bp/             # Blueprint: interfaz sincronización
│   ├── templates/           # Jinja2 templates
│   └── static/              # CSS y JS
├── scripts/
│   ├── create_admin.py      # Crear usuario admin
│   ├── sync_manual.py       # Sincronización manual por CLI
│   ├── diagnose_overleaf.py # Diagnóstico de conexión
│   └── seed_overleaf.py     # Datos de prueba para Overleaf
├── migrations/              # Generado por Flask-Migrate
├── tests/
│   └── test_sync.py         # Tests de la capa ETL
├── docs/
│   └── architecture.md      # Diagrama de arquitectura
├── docker/
│   └── Dockerfile
├── docker-compose.yml
├── requirements.txt
├── .env.example
└── run.py
```

---

## Limitaciones conocidas y fallbacks aplicados

### Extracción desde Overleaf CE

| Limitación | Fallback aplicado |
|---|---|
| Los nombres de campos en MongoDB pueden variar entre versiones de Overleaf CE | Toda la lógica de campo está encapsulada en `app/sync/extractor.py`. Se manejan alias (`first_name` / `firstName`, `created` / `date`). Si tu versión usa campos distintos, solo hay que editar ese archivo. |
| Overleaf CE no tiene API REST pública estable para metadatos | Se accede directamente a MongoDB vía pymongo. |
| MongoDB de Overleaf puede no tener autenticación (CE por defecto) | Si la tiene, configura usuario/contraseña en `MONGO_URI`. |
| Crear usuarios en Overleaf por CLI depende de la versión del toolkit | `seed_overleaf.py` usa el toolkit si existe; si no, inserta en MongoDB directamente. Los usuarios insertados directamente no pueden hacer login en Overleaf a menos que el hash de contraseña sea correcto. |
| El socket Docker puede no ser accesible desde Windows | El estado de servicios cae a verificación TCP y luego a mock. El dashboard sigue funcionando. |
| `lastLoggedIn` puede estar ausente si el usuario nunca ha hecho login | Se almacena como `NULL` en PostgreSQL. |

### Campos dependientes de versión de Overleaf CE

Los siguientes campos están documentados en `app/sync/extractor.py`:
- `signUpDate` vs `date` (fecha de registro de usuario)
- `first_name` vs `firstName` (nombre de usuario)
- `created` vs `date` (fecha de creación de proyecto)

---

## Variables de entorno

| Variable | Por defecto | Descripción |
|---|---|---|
| `SECRET_KEY` | dev-secret-key... | Clave para firmar sesiones Flask |
| `DATABASE_URL` | postgresql://... | URL completa de PostgreSQL |
| `MONGO_URI` | mongodb://localhost:27017/sharelatex | URI de MongoDB de Overleaf |
| `MONGO_DB` | sharelatex | Nombre de la base de datos de Overleaf |
| `DEBUG` | true | Modo debug de Flask |
| `DOCKER_SOCKET` | unix:///var/run/docker.sock | Socket Docker para monitorización |
| `OVERLEAF_COMPOSE_PROJECT` | sharelatex | Nombre del proyecto Compose de Overleaf |
| `ADMIN_USERNAME` | admin | Solo para `create_admin.py` |
| `ADMIN_PASSWORD` | admin | Solo para `create_admin.py` |

---

## Flujo de uso recomendado

```
1. docker compose up -d db          # Levantar PostgreSQL
2. flask db init && flask db migrate && flask db upgrade  # Crear tablas
3. python scripts/create_admin.py   # Crear usuario admin
4. python run.py                    # Arrancar la app
5. # Abrir http://127.0.0.1:5000 y hacer login con admin/admin
6. # (En WSL) cd ~/overleaf/toolkit && ./bin/up   # Levantar Overleaf
7. python scripts/diagnose_overleaf.py  # Verificar conexión
8. python scripts/sync_manual.py    # Primera sincronización
9. # Navegar al dashboard para ver los datos sincronizados
```

---

## Licencia

Copyright © 2026 Miguel Álvarez Fernández.

Este proyecto se distribuye bajo **Creative Commons Reconocimiento-NoComercial 4.0
Internacional (CC BY-NC 4.0)**. El texto completo está en [`LICENSE`](LICENSE) y en
<https://creativecommons.org/licenses/by-nc/4.0/deed.es>.

En resumen:

| | |
|---|---|
| Puedes | Copiar, distribuir, modificar y crear obras derivadas |
| Con la condición de | Citar la autoría original |
| No puedes | Usarlo con fines comerciales |

> GitHub muestra la licencia como "Other" porque CC BY-NC 4.0 no está en su base de
> datos de detección automática. La licencia aplicable es la indicada aquí.
