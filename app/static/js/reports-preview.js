/**
 * Overleaf Admin Platform — Reports preview general page
 *
 * Espera que el template defina antes de cargar este archivo:
 *   SECTION_RESUMEN_URL
 *   SECTION_USUARIOS_URL
 *   SECTION_PROYECTOS_URL
 *   SECTION_ALMACENAMIENTO_URL
 *   SECTION_SINCRONIZACION_URL
 *   SECTION_AUDITORIA_URL
 *
 * Globales de utils.js disponibles: esc()
 */
(function () {
  'use strict';

  function loadSection(url, containerId, renderFn) {
    fetch(url)
      .then(resp => {
        if (!resp.ok) throw new Error('Error ' + resp.status);
        return resp.json();
      })
      .then(data => { document.getElementById(containerId).innerHTML = renderFn(data); })
      .catch(err => {
        document.getElementById(containerId).innerHTML =
          `<div class="section-error"><i class="bi bi-exclamation-triangle me-1"></i>Error al cargar esta sección: ${esc(err.message)}</div>`;
      });
  }

  /* ── 1. Resumen ───────────────────────────────────────────────────────────── */
  loadSection(SECTION_RESUMEN_URL, 'resumen-content', d =>
    `<div class="card border-0 shadow-sm p-3"><div class="row g-3">
      <div class="col-6 col-md-3 gen-metric"><span class="label">Usuarios</span><br><span class="value">${d.total_users}</span></div>
      <div class="col-6 col-md-3 gen-metric"><span class="label">Proyectos</span><br><span class="value">${d.total_projects}</span></div>
      <div class="col-6 col-md-3 gen-metric"><span class="label">Almacenamiento</span><br><span class="value">${esc(d.total_storage_fmt)}</span></div>
      <div class="col-6 col-md-3 gen-metric"><span class="label">Sincronizaciones</span><br><span class="value">${d.total_syncs}</span></div>
      <div class="col-6 col-md-3 gen-metric"><span class="label">Admins internos</span><br><span class="value">${d.total_admins_internal}</span></div>
      <div class="col-6 col-md-3 gen-metric"><span class="label">Roles definidos</span><br><span class="value">${d.total_roles}</span></div>
      <div class="col-6 col-md-3 gen-metric"><span class="label">% Sync correctas</span><br><span class="value">${d.success_pct}%</span></div>
      <div class="col-6 col-md-3 gen-metric"><span class="label">Alertas (24 h)</span><br>
        <span class="value ${d.active_alerts_count > 0 ? 'text-danger' : ''}">${d.active_alerts_count}</span></div>
    </div></div>`
  );

  /* ── 2. Usuarios ──────────────────────────────────────────────────────────── */
  loadSection(SECTION_USUARIOS_URL, 'usuarios-content', d => {
    let html = '<div class="row g-3 mb-3">';
    html += '<div class="col-md-6"><div class="card border-0 shadow-sm p-3">';
    html += '<h6 class="small fw-semibold mb-2">Usuarios por rol</h6>';
    if (d.users_by_role && d.users_by_role.length) {
      html += '<table class="table table-sm table-borderless mb-0 small">';
      d.users_by_role.forEach(r => {
        html += `<tr><td>${esc(r.name)}</td><td class="text-end fw-semibold">${r.count}</td></tr>`;
      });
      html += `<tr class="border-top"><td class="text-muted">Sin rol asignado</td><td class="text-end fw-semibold">${d.users_no_role}</td></tr>`;
      html += '</table>';
    } else {
      html += '<span class="text-muted small">No hay roles definidos.</span>';
    }
    html += '</div></div>';
    html += '<div class="col-md-6"><div class="card border-0 shadow-sm p-3">';
    html += '<h6 class="small fw-semibold mb-2">Estado de cuotas</h6>';
    html += `<div class="gen-metric mb-1"><span class="label">Cuota excedida:</span> <span class="value ${d.users_exceeded_quota.length > 0 ? 'text-danger' : ''}">${d.users_exceeded_quota.length}</span></div>`;
    html += `<div class="gen-metric"><span class="label">Cerca de cuota (80-100%):</span> <span class="value ${d.users_near_quota.length > 0 ? 'text-warning' : ''}">${d.users_near_quota.length}</span></div>`;
    html += '</div></div></div>';
    if (d.users_exceeded_quota.length > 0) {
      html += '<div class="card border-0 shadow-sm p-3 mb-3">';
      html += '<h6 class="small fw-semibold text-danger mb-2"><i class="bi bi-exclamation-circle me-1"></i>Usuarios que superan cuota</h6>';
      html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0 small">';
      html += '<thead class="table-light"><tr><th>Email</th><th>Usado</th><th>Cuota</th><th>% Uso</th></tr></thead><tbody>';
      d.users_exceeded_quota.forEach(u => {
        html += `<tr><td>${esc(u.email)}</td><td>${esc(u.used_fmt)}</td><td>${esc(u.quota_fmt)}</td><td class="text-danger fw-semibold">${u.pct}%</td></tr>`;
      });
      html += '</tbody></table></div></div>';
    }
    return html;
  });

  /* ── 3. Proyectos ─────────────────────────────────────────────────────────── */
  loadSection(SECTION_PROYECTOS_URL, 'proyectos-content', d => {
    let html = '<div class="card border-0 shadow-sm p-3 mb-3"><div class="row g-3">';
    html += `<div class="col-6 col-md-3 gen-metric"><span class="label">Total</span><br><span class="value">${d.total_projects}</span></div>`;
    html += `<div class="col-6 col-md-3 gen-metric"><span class="label">Grandes (&gt;10 MB)</span><br><span class="value">${d.large_projects}</span></div>`;
    html += `<div class="col-6 col-md-3 gen-metric"><span class="label">Inactivos (&gt;90 días)</span><br><span class="value">${d.inactive_projects}</span></div>`;
    html += `<div class="col-6 col-md-3 gen-metric"><span class="label">Colaborativos</span><br><span class="value">${d.collaborative_projects}</span></div>`;
    html += '</div></div>';
    if (d.top_projects_size && d.top_projects_size.length) {
      html += '<div class="card border-0 shadow-sm p-3 mb-3">';
      html += '<h6 class="small fw-semibold mb-2">Top proyectos por tamaño</h6>';
      html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0 small">';
      html += '<thead class="table-light"><tr><th>Proyecto</th><th>Propietario</th><th>Tamaño</th></tr></thead><tbody>';
      d.top_projects_size.forEach(p => {
        html += `<tr><td>${esc(p.name)}</td><td>${esc(p.owner_email)}</td><td>${esc(p.size_fmt)}</td></tr>`;
      });
      html += '</tbody></table></div></div>';
    }
    return html;
  });

  /* ── 4. Almacenamiento y cuotas ───────────────────────────────────────────── */
  loadSection(SECTION_ALMACENAMIENTO_URL, 'almacenamiento-content', d => {
    let html = '<div class="card border-0 shadow-sm p-3 mb-3"><div class="row g-3">';
    html += `<div class="col-6 col-md-4 gen-metric"><span class="label">Total consumido</span><br><span class="value">${esc(d.total_storage_fmt)}</span></div>`;
    html += `<div class="col-6 col-md-4 gen-metric"><span class="label">Media por usuario</span><br><span class="value">${esc(d.avg_storage_per_user_fmt)}</span></div>`;
    html += `<div class="col-6 col-md-4 gen-metric"><span class="label">Media por proyecto</span><br><span class="value">${esc(d.avg_storage_per_project_fmt)}</span></div>`;
    html += '</div></div>';
    if (d.top_users_storage && d.top_users_storage.length) {
      html += '<div class="card border-0 shadow-sm p-3 mb-3">';
      html += '<h6 class="small fw-semibold mb-2">Top usuarios por almacenamiento</h6>';
      html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0 small">';
      html += '<thead class="table-light"><tr><th>Email</th><th>Espacio usado</th></tr></thead><tbody>';
      d.top_users_storage.forEach(u => {
        html += `<tr><td>${esc(u.email)}</td><td>${esc(u.used_fmt)}</td></tr>`;
      });
      html += '</tbody></table></div></div>';
    }
    return html;
  });

  /* ── 5. Sincronización ────────────────────────────────────────────────────── */
  loadSection(SECTION_SINCRONIZACION_URL, 'sincronizacion-content', d => {
    let html = '<div class="card border-0 shadow-sm p-3 mb-3"><div class="row g-3">';
    html += `<div class="col-6 col-md-3 gen-metric"><span class="label">Total ejecuciones</span><br><span class="value">${d.total_syncs}</span></div>`;
    html += `<div class="col-6 col-md-3 gen-metric"><span class="label">% Correctas</span><br><span class="value">${d.success_pct}%</span></div>`;
    html += `<div class="col-6 col-md-3 gen-metric"><span class="label">Duración media</span><br><span class="value">${d.avg_sync_duration !== null ? d.avg_sync_duration + ' s' : 'N/A'}</span></div>`;
    let lastSyncHtml = 'N/A';
    if (d.last_sync) {
      lastSyncHtml = esc(d.last_sync.started_at || 'N/A');
      if (d.last_sync.status === 'success')     lastSyncHtml += ' <span class="badge bg-success ms-1">OK</span>';
      else if (d.last_sync.status === 'error')  lastSyncHtml += ' <span class="badge bg-danger ms-1">Error</span>';
      else lastSyncHtml += ` <span class="badge bg-secondary ms-1">${esc(d.last_sync.status)}</span>`;
    }
    html += `<div class="col-6 col-md-3 gen-metric"><span class="label">Última sync</span><br><span class="value">${lastSyncHtml}</span></div>`;
    html += '</div></div>';
    if (d.failed_syncs_recent && d.failed_syncs_recent.length) {
      html += '<div class="card border-0 shadow-sm p-3 mb-3">';
      html += '<h6 class="small fw-semibold text-danger mb-2">Últimas sincronizaciones fallidas</h6>';
      html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0 small">';
      html += '<thead class="table-light"><tr><th>Fecha</th><th>Iniciado por</th><th>Mensaje</th></tr></thead><tbody>';
      d.failed_syncs_recent.forEach(sr => {
        html += `<tr><td>${esc(sr.started_at)}</td><td>${esc(sr.triggered_by)}</td><td class="text-truncate" style="max-width:250px;">${esc(sr.message || '—')}</td></tr>`;
      });
      html += '</tbody></table></div></div>';
    }
    return html;
  });

  /* ── 6. Auditoría e incidencias ───────────────────────────────────────────── */
  loadSection(SECTION_AUDITORIA_URL, 'auditoria-content', d => {
    let html = '';

    // Desglose por categoría (auth/admin/cuotas/sync/rol)
    if (d.by_category && d.by_category.length) {
      html += '<div class="card border-0 shadow-sm p-3 mb-3">';
      html += '<h6 class="small fw-semibold mb-2"><i class="bi bi-pie-chart me-1 text-muted"></i>Eventos por categoría</h6>';
      html += '<div class="row g-2">';
      d.by_category.forEach(c => {
        html += `<div class="col-6 col-md-4 col-lg-2"><div class="border rounded p-2 text-center">`;
        html += `<i class="bi ${esc(c.icon)} text-${esc(c.color)}" style="font-size:1rem;"></i>`;
        html += `<div class="text-muted" style="font-size:.7rem;">${esc(c.label)}</div>`;
        html += `<div class="fw-bold">${c.count}</div>`;
        html += `</div></div>`;
      });
      html += '</div></div>';
    }

    if (d.recent_errors && d.recent_errors.length) {
      html += '<div class="card border-0 shadow-sm p-3 mb-3">';
      html += '<h6 class="small fw-semibold mb-2">Errores y avisos recientes</h6>';
      html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0 small">';
      html += '<thead class="table-light"><tr><th>Fecha</th><th>Nivel</th><th>Actor</th><th>Acción</th><th>Detalle</th></tr></thead><tbody>';
      d.recent_errors.forEach(e => {
        const badge = e.level === 'error'
          ? '<span class="badge bg-danger">error</span>'
          : `<span class="badge bg-warning text-dark">${esc(e.level)}</span>`;
        // Acción legible + código técnico debajo
        const actionCell = `${esc(e.action_label || e.action)}<div class="text-muted" style="font-size:.65rem;"><code>${esc(e.action)}</code></div>`;
        html += `<tr><td>${esc(e.created_at)}</td><td>${badge}</td><td>${esc(e.actor)}</td><td>${actionCell}</td><td class="text-truncate" style="max-width:200px;">${esc(e.detail || '—')}</td></tr>`;
      });
      html += '</tbody></table></div></div>';
    } else {
      html += '<div class="text-muted small mb-3"><i class="bi bi-check-circle text-success me-1"></i>No hay errores ni avisos recientes.</div>';
    }
    if (d.recent_role_changes && d.recent_role_changes.length) {
      html += '<div class="card border-0 shadow-sm p-3 mb-3">';
      html += '<h6 class="small fw-semibold mb-2">Últimos cambios de rol/cuota</h6>';
      html += '<div class="table-responsive"><table class="table table-sm table-hover mb-0 small">';
      html += '<thead class="table-light"><tr><th>Fecha</th><th>Admin</th><th>Acción</th><th>Rol anterior</th><th>Rol nuevo</th></tr></thead><tbody>';
      d.recent_role_changes.forEach(rc => {
        html += `<tr><td>${esc(rc.changed_at)}</td><td>${esc(rc.changed_by)}</td><td>${esc(rc.action_label || rc.action)}</td><td>${esc(rc.role_from || '—')}</td><td>${esc(rc.role_to || '—')}</td></tr>`;
      });
      html += '</tbody></table></div></div>';
    }
    return html || '<div class="text-muted small"><i class="bi bi-check-circle text-success me-1"></i>Sin actividad de auditoría reciente.</div>';
  });

})();
