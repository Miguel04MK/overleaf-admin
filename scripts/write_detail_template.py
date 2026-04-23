"""Helper script — writes the user detail template. Run once then delete."""
import pathlib

HTML = """\
{% extends "base.html" %}
{% block title %}Usuario - {{ user.display_name }}{% endblock %}
{% block page_title %}Detalle de usuario{% endblock %}

{% block content %}
<div class="pt-3">

  <div class="mb-3">
    <a href="{{ url_for('users.list_users') }}" class="btn btn-sm btn-outline-secondary">
      <i class="bi bi-arrow-left me-1"></i>Volver al listado
    </a>
  </div>

  {% with messages = get_flashed_messages(with_categories=true) %}
    {% for category, message in messages %}
      <div class="alert alert-{{ category }} alert-dismissible fade show" role="alert">
        {{ message }}
        <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
      </div>
    {% endfor %}
  {% endwith %}

  <div class="row g-3">

    <!-- Left column: user info + quota -->
    <div class="col-12 col-lg-5">

      <!-- User info card -->
      <div class="card border-0 shadow-sm mb-3">
        <div class="card-body text-center py-4">
          <div class="rounded-circle bg-primary-subtle d-inline-flex align-items-center justify-content-center mb-3"
               style="width:72px;height:72px;">
            <i class="bi bi-person-fill fs-2 text-primary"></i>
          </div>
          <h5 class="fw-bold mb-1">{{ user.display_name }}</h5>
          <p class="text-muted mb-2">{{ user.email or "-" }}</p>
          {% if user.is_admin %}
            <span class="badge bg-warning text-dark">
              <i class="bi bi-shield-fill-check me-1"></i>Administrador Overleaf
            </span>
          {% else %}
            <span class="badge bg-secondary">Usuario estandar</span>
          {% endif %}
        </div>
        <div class="card-footer bg-white border-top">
          <dl class="row mb-0 small">
            <dt class="col-6 text-muted">ID plataforma</dt>
            <dd class="col-6 text-end fw-medium">{{ user.id }}</dd>

            <dt class="col-6 text-muted">ID Overleaf</dt>
            <dd class="col-6 text-end">
              <code class="small" title="{{ user.overleaf_id }}">{{ user.overleaf_id }}</code>
            </dd>

            <dt class="col-6 text-muted">Nombre</dt>
            <dd class="col-6 text-end">{{ user.first_name or "-" }}</dd>

            <dt class="col-6 text-muted">Apellidos</dt>
            <dd class="col-6 text-end">{{ user.last_name or "-" }}</dd>

            <dt class="col-6 text-muted">Registro</dt>
            <dd class="col-6 text-end">
              {{ user.signup_date.strftime('%d/%m/%Y') if user.signup_date else "-" }}
            </dd>

            <dt class="col-6 text-muted">Ultimo acceso</dt>
            <dd class="col-6 text-end">
              {{ user.last_login_at.strftime('%d/%m/%Y %H:%M') if user.last_login_at else "-" }}
            </dd>

            <dt class="col-6 text-muted">Sincronizado</dt>
            <dd class="col-6 text-end">
              {{ user.synced_at.strftime('%d/%m/%Y %H:%M') if user.synced_at else "-" }}
            </dd>
          </dl>
        </div>
      </div>

      <!-- Quota card -->
      <div class="card border-0 shadow-sm">
        <div class="card-header bg-white fw-semibold d-flex align-items-center justify-content-between">
          <span><i class="bi bi-hdd me-2 text-muted"></i>Cuota de almacenamiento</span>
          {% if user.quota_exceeded %}
            <span class="badge bg-danger">
              <i class="bi bi-exclamation-triangle-fill me-1"></i>Excedida
            </span>
          {% elif user.quota_percent is not none and user.quota_percent >= 80 %}
            <span class="badge bg-warning text-dark">
              <i class="bi bi-exclamation-circle me-1"></i>Cerca del limite
            </span>
          {% endif %}
        </div>
        <div class="card-body">

          <!-- Usage bar -->
          {% set pct = user.quota_percent %}
          <div class="mb-3">
            <div class="d-flex justify-content-between small text-muted mb-1">
              <span>Uso actual</span>
              <span class="fw-medium text-body">{{ user.quota_used_fmt }}</span>
            </div>
            {% if pct is not none %}
            <div class="progress mb-1" style="height:12px">
              <div class="progress-bar bg-{{ user.quota_status }}"
                   role="progressbar"
                   style="width:{{ [pct, 100]|min }}%"
                   aria-valuenow="{{ pct }}" aria-valuemin="0" aria-valuemax="100">
              </div>
            </div>
            <div class="d-flex justify-content-between small text-muted">
              <span>{{ pct }}% usado</span>
              <span>Limite: {{ user.quota_max_fmt }}</span>
            </div>
            {% else %}
            <div class="text-muted small fst-italic">Sin limite asignado</div>
            {% endif %}
          </div>

          <hr class="my-3">

          <!-- Edit quota form -->
          <form method="POST" action="{{ url_for('users.set_quota', user_id=user.id) }}">
            <label class="form-label fw-medium small">Asignar limite de cuota</label>
            <div class="input-group mb-2">
              <input type="number" name="quota_value" class="form-control"
                     placeholder="Ej: 500" min="0" step="any"
                     value="{{ '%.0f'|format(user.max_quota_bytes / (1024**2)) if user.max_quota_bytes else '' }}">
              <select name="quota_unit" class="form-select" style="max-width:90px">
                <option value="MB" {% if not user.max_quota_bytes or user.max_quota_bytes < 1024**3 %}selected{% endif %}>MB</option>
                <option value="GB" {% if user.max_quota_bytes and user.max_quota_bytes >= 1024**3 %}selected{% endif %}>GB</option>
                <option value="KB">KB</option>
              </select>
              <button type="submit" class="btn btn-primary">
                <i class="bi bi-check2 me-1"></i>Guardar
              </button>
            </div>
            <div class="form-text text-muted">
              Deja en blanco o pon 0 para almacenamiento ilimitado.
            </div>
          </form>

          <p class="small text-muted mt-3 mb-0">
            <i class="bi bi-info-circle me-1"></i>
            El uso incluye solo archivos binarios adjuntos (imagenes, PDFs, etc.).
            Los .tex se almacenan en el historial git de Overleaf y no se contabilizan aqui.
          </p>
        </div>
      </div>

    </div>

    <!-- Right column: projects -->
    <div class="col-12 col-lg-7">
      <div class="card border-0 shadow-sm">
        <div class="card-header bg-white border-bottom fw-semibold">
          <i class="bi bi-folder2-open me-2 text-muted"></i>
          Proyectos como propietario
          <span class="badge bg-secondary ms-2">{{ projects_owned|length }}</span>
        </div>
        <div class="card-body p-0">
          {% if projects_owned %}
          <div class="table-responsive">
            <table class="table table-sm table-hover align-middle mb-0">
              <thead class="table-light">
                <tr>
                  <th class="ps-3">Nombre</th>
                  <th class="text-end">Tamano</th>
                  <th class="text-center">Colaboradores</th>
                  <th>Creado</th>
                  <th>Actualizado</th>
                </tr>
              </thead>
              <tbody>
                {% for proj in projects_owned %}
                <tr>
                  <td class="ps-3 fw-medium small">{{ proj.name or "-" }}</td>
                  <td class="text-end small text-muted">
                    {% if proj.size_bytes and proj.size_bytes > 0 %}
                      {% set s = proj.size_bytes %}
                      {% if s >= 1073741824 %}
                        {{ "%.1f"|format(s / 1073741824) }} GB
                      {% elif s >= 1048576 %}
                        {{ "%.1f"|format(s / 1048576) }} MB
                      {% elif s >= 1024 %}
                        {{ "%.1f"|format(s / 1024) }} KB
                      {% else %}
                        {{ s }} B
                      {% endif %}
                    {% else %}
                      <span class="opacity-50">-</span>
                    {% endif %}
                  </td>
                  <td class="text-center small">
                    {% set n = proj.members.count() %}
                    {% if n > 0 %}
                      <span class="badge bg-info-subtle text-info-emphasis">
                        <i class="bi bi-people-fill me-1"></i>{{ n }}
                      </span>
                    {% else %}
                      <span class="text-muted opacity-75">Solo</span>
                    {% endif %}
                  </td>
                  <td class="small text-muted">
                    {{ proj.created_at.strftime('%d/%m/%Y') if proj.created_at else "-" }}
                  </td>
                  <td class="small text-muted">
                    {{ proj.last_updated_at.strftime('%d/%m/%Y') if proj.last_updated_at else "-" }}
                  </td>
                </tr>
                {% endfor %}
              </tbody>
              <tfoot class="table-light">
                <tr>
                  <td class="ps-3 small text-muted fw-semibold">Total</td>
                  <td class="text-end small fw-semibold">{{ user.quota_used_fmt }}</td>
                  <td colspan="3"></td>
                </tr>
              </tfoot>
            </table>
          </div>
          {% else %}
          <div class="text-center text-muted py-4 small">
            <i class="bi bi-folder-x d-block fs-3 mb-2 opacity-50"></i>
            Este usuario no tiene proyectos registrados como propietario.
          </div>
          {% endif %}
        </div>
      </div>
    </div>

  </div>
</div>
{% endblock %}
"""

dest = pathlib.Path(r"C:/Users/migue/OneDrive/Escritorio/uni/overleaf-admin/app/templates/users/detail.html")
dest.write_text(HTML, encoding="utf-8")
print(f"Written {len(HTML)} chars to {dest}")
