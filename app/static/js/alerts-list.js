/**
 * Overleaf Admin Platform — Alerts list page
 *
 * Espera que el template haya definido antes de cargar este archivo:
 *   SEARCH_URL, RECALC_URL, CONFIG_URL, NOTIF_URL,
 *   BULK_READ_URL, BULK_RESOLVE_URL, BULK_REOPEN_URL,
 *   PER_PAGE, ALERT_DETAIL_URL_TPL
 */

// ── Estado ────────────────────────────────────────────────────────────────────
let _curPage       = 1;
let _totalPages    = 1;
let _totalAlerts   = 0;
let _debounce      = null;
let _autoTimer     = null;
let _pendingResolveUrl  = null;
let _pendingResolveIds  = null;
let _selectedIds   = new Set();
let _lastDataHash  = '';

// ── Filtros activos ───────────────────────────────────────────────────────────
let activeFilters = [];
let _nextId = 0;

const fQ = document.getElementById('f-q');

function currentParams(page) {
  const p = new URLSearchParams();
  const q = fQ.value.trim();
  if (q) p.set('q', q);
  p.set('page',     page || _curPage);
  p.set('per_page', PER_PAGE);
  activeFilters.forEach(f => {
    if (f.type === 'type')   p.set('type',   f.val);
    if (f.type === 'level')  p.set('level',  f.val);
    if (f.type === 'status') p.set('status', f.val);
    if (f.type === 'unread') p.set('unread', f.val);
    if (f.type === 'dates') {
      if (f.val.from) p.set('date_from', f.val.from);
      if (f.val.to)   p.set('date_to',   f.val.to);
    }
  });
  return p;
}

function addFilter(type, val, label) {
  activeFilters = activeFilters.filter(f => f.type !== type);
  activeFilters.push({ id: _nextId++, type, val, label });
  _curPage = 1;
  syncChips(); syncFilterBtns(); doFetch();
}

function removeFilter(id) {
  const f = activeFilters.find(f => f.id === id);
  if (f && f.type === 'dates') {
    document.getElementById('f-date-from').value = '';
    document.getElementById('f-date-to').value   = '';
  }
  activeFilters = activeFilters.filter(f => f.id !== id);
  _curPage = 1;
  syncChips(); syncFilterBtns(); doFetch();
}

function clearAllFilters() {
  activeFilters = [];
  fQ.value = '';
  document.getElementById('f-date-from').value = '';
  document.getElementById('f-date-to').value   = '';
  _curPage = 1;
  syncChips(); syncFilterBtns(); doFetch();
}

function syncChips() {
  const row = document.getElementById('chips-row');
  if (!activeFilters.length) { row.classList.add('d-none'); row.innerHTML = ''; return; }
  row.classList.remove('d-none');
  row.innerHTML = activeFilters.map(f => `
    <span class="filter-chip">
      ${esc(f.label)}
      <button class="chip-remove" data-remove="${f.id}" title="Quitar">✕</button>
    </span>`
  ).join('') + `
    <button type="button" id="btn-clear-all"
            class="btn btn-sm btn-link text-danger text-decoration-none p-0 ms-1">
      <i class="bi bi-x-circle me-1"></i>Limpiar todo
    </button>`;
  row.querySelectorAll('[data-remove]').forEach(b =>
    b.addEventListener('click', () => removeFilter(parseInt(b.dataset.remove)))
  );
  document.getElementById('btn-clear-all').addEventListener('click', clearAllFilters);
}

function syncFilterBtns() {
  const active = new Set(activeFilters.map(f => f.type));
  [['type','btn-f-type'],['level','btn-f-level'],['status','btn-f-status'],
   ['unread','btn-f-unread'],['dates','btn-f-date']].forEach(([type, id]) => {
    const btn = document.getElementById(id);
    if (!btn) return;
    const on = active.has(type);
    btn.classList.toggle('has-filter', on);
    btn.classList.toggle('btn-outline-secondary', !on);
  });
}

// ── Dropdown vanilla ──────────────────────────────────────────────────────────
(function () {
  function closeAll(except) {
    document.querySelectorAll('.filter-dropdown').forEach(d => {
      if (d === except) return;
      d.classList.remove('show');
      const m = d.querySelector('.dropdown-menu');
      if (m) m.classList.remove('show');
    });
  }
  document.querySelectorAll('.filter-dropdown').forEach(dropdown => {
    const btn  = dropdown.querySelector('.dropdown-toggle');
    const menu = dropdown.querySelector('.dropdown-menu');
    if (!btn || !menu) return;
    menu.style.position = 'absolute';
    menu.style.zIndex   = '1055';
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const isOpen = dropdown.classList.contains('show');
      closeAll();
      if (!isOpen) { dropdown.classList.add('show'); menu.classList.add('show'); }
    });
    menu.addEventListener('click', e => e.stopPropagation());
  });
  document.addEventListener('click', () => closeAll());
})();

function closeDropdown(btnId) {
  const dd = document.getElementById(btnId).closest('.filter-dropdown');
  dd.classList.remove('show');
  dd.querySelector('.dropdown-menu').classList.remove('show');
}

// ── Filtros de lista ──────────────────────────────────────────────────────────
[
  { dropdownId: 'btn-f-type',   filterType: 'type'   },
  { dropdownId: 'btn-f-level',  filterType: 'level'  },
  { dropdownId: 'btn-f-status', filterType: 'status' },
  { dropdownId: 'btn-f-unread', filterType: 'unread' },
].forEach(({ dropdownId, filterType }) => {
  const dropdown = document.getElementById(dropdownId).closest('.filter-dropdown');
  dropdown.querySelectorAll('[data-val]').forEach(item => {
    item.addEventListener('click', e => {
      e.preventDefault();
      addFilter(filterType, item.dataset.val, item.dataset.label);
      closeDropdown(dropdownId);
    });
  });
});

// ── Filtro de fechas ──────────────────────────────────────────────────────────
document.getElementById('btn-date-apply').addEventListener('click', () => {
  const from = document.getElementById('f-date-from').value;
  const to   = document.getElementById('f-date-to').value;
  if (!from && !to) {
    activeFilters = activeFilters.filter(f => f.type !== 'dates');
    syncChips(); syncFilterBtns(); doFetch();
  } else {
    const parts = [];
    if (from) parts.push(`desde ${from}`);
    if (to)   parts.push(`hasta ${to}`);
    addFilter('dates', { from, to }, `Fecha: ${parts.join(' ')}`);
  }
  closeDropdown('btn-f-date');
});

// ── Buscador con debounce ─────────────────────────────────────────────────────
fQ.addEventListener('input', () => {
  clearTimeout(_debounce);
  _debounce = setTimeout(() => { _curPage = 1; doFetch(); }, 320);
});

// ── Cards resumen ─────────────────────────────────────────────────────────────
document.querySelectorAll('.summary-filter').forEach(card => {
  card.addEventListener('click', e => {
    e.preventDefault();
    activeFilters = [];
    fQ.value = '';
    document.getElementById('f-date-from').value = '';
    document.getElementById('f-date-to').value   = '';
    if (card.dataset.status && card.dataset.status !== 'all') {
      activeFilters.push({ id: _nextId++, type: 'status', val: card.dataset.status, label: 'Solo activas' });
    }
    if (card.dataset.unread) {
      activeFilters.push({ id: _nextId++, type: 'unread', val: 'yes', label: 'Sin leer' });
    }
    if (card.dataset.level) {
      const lbl = { critical: 'Crítico', danger: 'Peligro', warning: 'Aviso', info: 'Info' };
      activeFilters.push({ id: _nextId++, type: 'level', val: card.dataset.level,
                           label: `Nivel: ${lbl[card.dataset.level] || card.dataset.level}` });
    }
    _curPage = 1;
    syncChips(); syncFilterBtns(); doFetch();
  });
});

// ── Recalcular ────────────────────────────────────────────────────────────────
document.getElementById('btn-recalculate').addEventListener('click', () => {
  const btn = document.getElementById('btn-recalculate');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Calculando…';
  fetch(RECALC_URL, { method: 'POST', headers: { 'Accept': 'application/json' } })
    .then(() => doFetch())
    .finally(() => {
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-arrow-repeat me-1"></i>Recalcular';
    });
});

// ── Fetch (server-side pagination) ───────────────────────────────────────────
function doFetch(silent = false, keepSelection = false) {
  const tbody = document.getElementById('alerts-tbody');
  if (!silent) {
    document.getElementById('search-spinner').classList.remove('d-none');
    tbody.classList.add('tbody-loading');
  }
  fetch(`${SEARCH_URL}?${currentParams(_curPage)}`)
    .then(r => r.json())
    .then(data => {
      _totalAlerts = data.total;
      _totalPages  = data.pages || 1;
      if (!keepSelection) _selectedIds.clear();
      renderTable(data.alerts, data.total, data.pages, data.page);
      _lastDataHash = JSON.stringify(data.alerts.map(a => a.id + ':' + a.is_read + ':' + a.level + ':' + (a.resolved_at||'')));
      setText('cnt-active',   data.active_count);
      setText('cnt-unread',   data.unread_count);
      setText('cnt-critical', data.critical_count);
      if (data.last_recalc) {
        const el = document.getElementById('last-recalc-badge');
        el.textContent = 'Última comp.: ' + data.last_recalc;
        el.classList.remove('d-none');
      }
      syncBulkBar();
    })
    .finally(() => {
      document.getElementById('search-spinner').classList.add('d-none');
      document.getElementById('alerts-tbody').classList.remove('tbody-loading');
    });
}

function setText(id, val) {
  const el = document.getElementById(id);
  if (el) el.textContent = val;
}

// ── Auto-refresco ─────────────────────────────────────────────────────────────
function scheduleAutoRefresh() {
  clearTimeout(_autoTimer);
  _autoTimer = setTimeout(() => { _silentRefresh(); scheduleAutoRefresh(); }, 60_000);
}

function _silentRefresh() {
  fetch(`${SEARCH_URL}?${currentParams(_curPage)}`)
    .then(r => r.json())
    .then(data => {
      setText('cnt-active',   data.active_count);
      setText('cnt-unread',   data.unread_count);
      setText('cnt-critical', data.critical_count);
      if (data.last_recalc) {
        const el = document.getElementById('last-recalc-badge');
        el.textContent = 'Última comp.: ' + data.last_recalc;
        el.classList.remove('d-none');
      }
      const hash = JSON.stringify(data.alerts.map(a => a.id + ':' + a.is_read + ':' + a.level + ':' + (a.resolved_at||'')));
      if (hash !== _lastDataHash) {
        _lastDataHash = hash;
        _totalAlerts = data.total;
        _totalPages  = data.pages || 1;
        renderTable(data.alerts, data.total, data.pages, data.page);
        syncBulkBar();
      }
    })
    .catch(() => {});
}

// ── Render tabla ──────────────────────────────────────────────────────────────
function renderTable(alerts, total, pages, page) {
  const tbody = document.getElementById('alerts-tbody');

  document.getElementById('result-count').innerHTML =
    `<strong>${total}</strong> alerta${total !== 1 ? 's' : ''}`;

  if (!total) {
    tbody.innerHTML = `
      <tr><td colspan="8" class="text-center py-5 text-muted">
        <i class="bi bi-shield-check fs-1 d-block mb-3 opacity-50"></i>
        <p class="fw-semibold mb-1">No hay alertas con los filtros actuales</p>
        <p class="small mb-0">La plataforma no presenta incidencias o están todas resueltas.</p>
      </td></tr>`;
    document.getElementById('alerts-pagination').classList.add('d-none');
    document.getElementById('chk-all').checked = false;
    return;
  }

  tbody.innerHTML = alerts.map(a => rowHtml(a)).join('');

  tbody.querySelectorAll('.row-check').forEach(chk => {
    chk.addEventListener('change', () => {
      const id = parseInt(chk.dataset.id);
      if (chk.checked) _selectedIds.add(id);
      else             _selectedIds.delete(id);
      syncBulkBar();
      syncSelectAll();
    });
  });

  tbody.querySelectorAll('.row-check').forEach(chk => {
    if (_selectedIds.has(parseInt(chk.dataset.id))) chk.checked = true;
  });
  syncSelectAll();

  tbody.querySelectorAll('[data-action]').forEach(btn => {
    btn.addEventListener('click', () => handleAction(btn));
  });

  renderPagination(total, pages, page);
}

// ── Helpers de fila ───────────────────────────────────────────────────────────
const EXTRA_DATA_LABELS = {
  email:            'Correo electronico',
  max_quota_bytes:  'Cuota maxima',
  quota_percent:    'Porcentaje de cuota usada',
  sync_run_id:      'ID de sincronizacion',
  status:           'Estado',
  project_count:    'Numero de proyectos',
  max_projects:     'Limite de proyectos',
  error_count:      'Errores detectados',
  hours:            'Ventana de tiempo (horas)',
  service_name:     'Nombre del servicio',
  detail:           'Detalle',
};
const BYTE_FIELDS = new Set(['max_quota_bytes']);

function translateExtraKey(key) {
  return EXTRA_DATA_LABELS[key] || key.replace(/_/g, ' ');
}

function formatExtraValue(key, val) {
  if (BYTE_FIELDS.has(key)) return formatBytes(val);
  if (key === 'quota_percent') return parseFloat(val).toFixed(1) + ' %';
  return String(val);
}

function levelTextHtml(a) {
  const cls   = `level-text-${a.level}`;
  const icons = {
    critical: 'bi-exclamation-octagon-fill',
    danger:   'bi-x-octagon',
    warning:  'bi-exclamation-triangle',
    info:     'bi-info-circle',
  };
  return `<span class="${cls} small"><i class="bi ${icons[a.level] || 'bi-bell'} me-1"></i>${esc(a.level_label)}</span>`;
}

function formatDateCell(dt) {
  if (!dt) return '<span class="text-muted">—</span>';
  const sp   = dt.indexOf(' ');
  const date = sp >= 0 ? dt.slice(0, sp) : dt;
  const time = sp >= 0 ? dt.slice(sp + 1) : '';
  return `<span class="d-block small text-muted">${esc(date)}</span>` +
         (time ? `<span class="d-block text-muted" style="font-size:.7rem;">${esc(time)}</span>` : '');
}

function rowHtml(a) {
  const rowClass = a.is_resolved ? 'row-resolved' : `row-${a.level}`;

  const levelHtml = levelTextHtml(a) +
    (!a.is_read && !a.is_resolved
      ? `<br><span class="badge bg-primary-subtle text-primary border border-primary-subtle"
                   style="font-size:.6rem;margin-top:.1rem;">Nuevo</span>`
      : '');

  const typeHtml = `<span class="small">${esc(a.type_label)}</span>`;

  const msgHtml = `
    <div class="fw-medium small text-truncate" style="max-width:300px;" title="${esc(a.title)}">${esc(a.title)}</div>
    <div class="text-muted small text-truncate" style="max-width:300px;" title="${esc(a.message)}">${esc(a.message)}</div>`;

  let entityHtml = '<span class="text-muted small">—</span>';
  if (a.entity_type) {
    if (a.entity_url) {
      entityHtml = `<a href="${esc(a.entity_url)}" class="entity-link" title="Ver ${esc(a.entity_type)}">
        ${esc(a.entity_type)} <i class="bi bi-box-arrow-up-right ms-1"></i></a>`;
    } else {
      const showId = a.entity_id && !['latest','repeated_errors'].includes(a.entity_id);
      entityHtml = `<span class="entity-static">${esc(a.entity_type)}</span>` +
                   (showId ? `<span class="d-block text-muted" style="font-size:.68rem;">id: ${esc(a.entity_id)}</span>` : '');
    }
  }

  const dateHtml = formatDateCell(a.created_at);

  let statusHtml;
  if (a.is_resolved) {
    statusHtml =
      `<span class="badge bg-success-subtle text-success border border-success-subtle">Resuelta</span>` +
      (a.resolved_by ? `<span class="d-block small text-muted mt-1">por <strong>${esc(a.resolved_by)}</strong></span>` : '') +
      (a.resolved_at ? `<span class="d-block text-muted" style="font-size:.7rem;">${esc(a.resolved_at)}</span>` : '') +
      (a.resolution_comment
        ? `<span class="d-block small text-muted fst-italic text-truncate mt-1" style="max-width:150px;"
               title="${esc(a.resolution_comment)}">${esc(a.resolution_comment)}</span>`
        : '');
  } else {
    statusHtml = `<span class="badge bg-warning-subtle text-warning border border-warning-subtle">Activa</span>`;
  }

  let actions = `
    <button class="btn btn-outline-secondary btn-action" data-action="detalle"
            data-url="${esc(a.detail_url)}" title="Ver detalle">
      <i class="bi bi-eye"></i>
    </button>`;

  if (!a.is_resolved) {
    if (!a.is_read) {
      actions += `
        <button class="btn btn-outline-secondary btn-action" data-action="leer"
                data-url="${esc(a.read_url)}" title="Marcar como leída">
          <i class="bi bi-envelope-open"></i>
        </button>`;
    }
    actions += `
      <button class="btn btn-outline-success btn-action" data-action="resolver"
              data-url="${esc(a.resolve_url)}"
              data-title="${esc(a.title)}" data-message="${esc(a.message)}"
              title="Resolver alerta">
        <i class="bi bi-check-lg"></i>
      </button>`;
  } else {
    actions += `
      <button class="btn btn-outline-warning btn-action" data-action="reabrir"
              data-url="${esc(a.reopen_url)}" title="Reabrir alerta">
        <i class="bi bi-arrow-counterclockwise"></i>
      </button>`;
  }

  return `
  <tr class="${rowClass}">
    <td class="col-check ps-3 py-2">
      <input type="checkbox" class="form-check-input row-check" data-id="${a.id}">
    </td>
    <td class="py-2">${levelHtml}</td>
    <td class="py-2">${typeHtml}</td>
    <td class="py-2">${msgHtml}</td>
    <td class="py-2">${entityHtml}</td>
    <td class="py-2">${dateHtml}</td>
    <td class="py-2">${statusHtml}</td>
    <td class="text-center pe-3 py-2">
      <div class="d-flex justify-content-center gap-1">${actions}</div>
    </td>
  </tr>`;
}

// ── Select-all checkbox ───────────────────────────────────────────────────────
document.getElementById('chk-all').addEventListener('change', function() {
  document.querySelectorAll('.row-check').forEach(chk => {
    chk.checked = this.checked;
    const id = parseInt(chk.dataset.id);
    if (this.checked) _selectedIds.add(id);
    else              _selectedIds.delete(id);
  });
  syncBulkBar();
});

function syncSelectAll() {
  const checks = [...document.querySelectorAll('.row-check')];
  const chkAll = document.getElementById('chk-all');
  if (!checks.length) { chkAll.checked = false; chkAll.indeterminate = false; return; }
  const checked = checks.filter(c => c.checked).length;
  chkAll.checked       = checked === checks.length;
  chkAll.indeterminate = checked > 0 && checked < checks.length;
}

// ── Bulk bar ──────────────────────────────────────────────────────────────────
function syncBulkBar() {
  const bar = document.getElementById('bulk-bar');
  const n   = _selectedIds.size;
  if (n === 0) { bar.classList.add('d-none'); return; }
  bar.classList.remove('d-none');
  document.getElementById('bulk-count-num').textContent = n;
}

document.getElementById('btn-deselect-all').addEventListener('click', () => {
  _selectedIds.clear();
  document.querySelectorAll('.row-check').forEach(c => c.checked = false);
  document.getElementById('chk-all').checked = false;
  document.getElementById('chk-all').indeterminate = false;
  syncBulkBar();
});

function bulkPost(url, extraBody) {
  const ids = [..._selectedIds];
  return fetch(url, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body:    JSON.stringify({ ids, ...extraBody }),
  }).then(r => r.json());
}

document.getElementById('btn-bulk-read').addEventListener('click', () => {
  bulkPost(BULK_READ_URL).then(() => { _curPage = 1; doFetch(); });
});

document.getElementById('btn-bulk-reopen').addEventListener('click', () => {
  bulkPost(BULK_REOPEN_URL).then(() => { _curPage = 1; doFetch(); });
});

document.getElementById('btn-bulk-resolve').addEventListener('click', () => {
  _pendingResolveIds  = [..._selectedIds];
  _pendingResolveUrl  = null;
  document.getElementById('resolve-alert-title').textContent   = `${_pendingResolveIds.length} alerta(s) seleccionada(s)`;
  document.getElementById('resolve-alert-message').textContent = 'Se resolverán todas las alertas seleccionadas.';
  document.getElementById('resolve-comment').value             = '';
  resolveModal.show();
});

// ── Acciones AJAX individuales ────────────────────────────────────────────────
function handleAction(btn) {
  const action = btn.dataset.action;
  if (action === 'detalle')  { openDetailModal(btn.dataset.url); return; }
  if (action === 'resolver') { openResolveModal(btn.dataset.url, btn.dataset.title, btn.dataset.message); return; }
  btn.disabled = true;
  fetch(btn.dataset.url, { method: 'POST', headers: { 'Accept': 'application/json' } })
    .then(r => r.json())
    .then(() => doFetch())
    .catch(() => { btn.disabled = false; });
}

// ── Modal: Resolver ───────────────────────────────────────────────────────────
const resolveModal      = new bootstrap.Modal(document.getElementById('resolveModal'));
const resolveConfirmBtn = document.getElementById('resolve-confirm-btn');

function openResolveModal(url, title, message) {
  _pendingResolveUrl = url;
  _pendingResolveIds = null;
  document.getElementById('resolve-alert-title').textContent   = title   || '';
  document.getElementById('resolve-alert-message').textContent = message || '';
  document.getElementById('resolve-comment').value             = '';
  resolveModal.show();
}

resolveConfirmBtn.addEventListener('click', () => {
  resolveConfirmBtn.disabled = true;
  resolveConfirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Resolviendo…';
  const comment = document.getElementById('resolve-comment').value.trim();

  const p = _pendingResolveIds
    ? bulkPost(BULK_RESOLVE_URL, { comment })
    : fetch(_pendingResolveUrl, {
        method:  'POST',
        headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
        body:    JSON.stringify({ comment }),
      }).then(r => r.json());

  p.then(() => { resolveModal.hide(); _curPage = 1; doFetch(); })
   .catch(() => {})
   .finally(() => {
     resolveConfirmBtn.disabled = false;
     resolveConfirmBtn.innerHTML = '<i class="bi bi-check-lg me-1"></i>Resolver alerta';
     _pendingResolveUrl = null;
     _pendingResolveIds = null;
   });
});

// ── Modal: Detalle ────────────────────────────────────────────────────────────
const detailModal = new bootstrap.Modal(document.getElementById('detailModal'));

function openDetailModal(url) {
  document.getElementById('detail-header').className = 'detail-header-strip';
  document.getElementById('detail-header-content').innerHTML =
    '<div class="text-center py-3 text-muted"><span class="spinner-border spinner-border-sm me-2"></span>Cargando…</div>';
  document.getElementById('detail-body').innerHTML = '';
  document.getElementById('detail-footer').innerHTML = '';
  detailModal.show();
  fetch(url, { headers: { 'Accept': 'application/json' } })
    .then(r => r.json())
    .then(a => renderDetailModal(a))
    .catch(() => {
      document.getElementById('detail-body').innerHTML =
        '<p class="text-danger small p-3">Error al cargar el detalle.</p>';
    });
}

function levelBadgeHtml(level, label) {
  const map = {
    critical: { bg: 'bg-danger',         cls: '' },
    danger:   { bg: 'bg-danger-subtle',  cls: 'text-danger border border-danger-subtle' },
    warning:  { bg: 'bg-warning-subtle', cls: 'text-warning border border-warning-subtle' },
    info:     { bg: 'bg-primary-subtle', cls: 'text-primary border border-primary-subtle' },
  };
  const s = map[level] || map.info;
  const icons = { critical:'bi-exclamation-octagon-fill', danger:'bi-x-octagon', warning:'bi-exclamation-triangle', info:'bi-info-circle' };
  return `<span class="badge ${s.bg} ${s.cls}" style="font-size:.72rem;">
    <i class="bi ${icons[level] || 'bi-bell'} me-1"></i>${esc(label)}</span>`;
}

function renderDetailModal(a) {
  const stripLevel = a.is_resolved ? 'resolved' : a.level;
  document.getElementById('detail-header').className = `detail-header-strip level-strip-${stripLevel}`;

  const badges = [
    levelBadgeHtml(a.level, a.level_label),
    a.is_resolved
      ? '<span class="badge bg-success-subtle text-success border border-success-subtle" style="font-size:.72rem;"><i class="bi bi-check-circle me-1"></i>Resuelta</span>'
      : '<span class="badge bg-warning-subtle text-warning border border-warning-subtle" style="font-size:.72rem;">Activa</span>',
    !a.is_read && !a.is_resolved
      ? '<span class="badge bg-primary-subtle text-primary border border-primary-subtle" style="font-size:.65rem;">Sin leer</span>'
      : '',
  ].filter(Boolean).join(' ');

  document.getElementById('detail-header-content').innerHTML = `
    <div class="d-flex align-items-center gap-2 flex-wrap mb-2">${badges}</div>
    <h5 class="fw-bold mb-1" style="line-height:1.3;">${esc(a.title)}</h5>
    <p class="text-muted mb-0" style="font-size:.78rem;">Alerta #${a.id} &middot; ${esc(a.type_label)}</p>`;

  let entityHtml = '<span class="text-muted">—</span>';
  if (a.entity_type) {
    entityHtml = esc(a.entity_type) + (a.entity_id ? ' <span class="text-muted">&middot;</span> ' + esc(a.entity_id) : '');
    if (a.entity_url) {
      entityHtml = `<a href="${esc(a.entity_url)}" class="entity-link">${entityHtml} <i class="bi bi-box-arrow-up-right ms-1"></i></a>`;
    }
  }

  let bodyHtml = `
    <div class="row g-3 mb-3">
      <div class="col-6">
        <div class="detail-field-label">Tipo</div>
        <div class="detail-field-value">${esc(a.type_label)}</div>
      </div>
      <div class="col-6">
        <div class="detail-field-label">Entidad</div>
        <div class="detail-field-value">${entityHtml}</div>
      </div>
      <div class="col-6">
        <div class="detail-field-label">Fecha de creacion</div>
        <div class="detail-field-value">${esc(a.created_at) || '—'}</div>
      </div>
      <div class="col-6">
        <div class="detail-field-label">Estado de lectura</div>
        <div class="detail-field-value">${a.is_read
          ? '<i class="bi bi-envelope-open me-1 text-muted"></i>Leida'
          : '<i class="bi bi-envelope-fill me-1 text-primary"></i>Sin leer'}</div>
      </div>
    </div>`;

  if (a.message) {
    bodyHtml += `
    <div class="mb-3">
      <div class="detail-field-label mb-1">Mensaje</div>
      <div class="detail-msg-box">${esc(a.message)}</div>
    </div>`;
  }

  if (a.is_resolved) {
    bodyHtml += `
    <div class="detail-resolved-card mb-3">
      <div class="d-flex align-items-center gap-2 mb-2">
        <i class="bi bi-check-circle-fill text-success"></i>
        <span class="fw-semibold small text-success">Resolucion</span>
      </div>
      <div class="row g-2">
        ${a.resolved_by ? `<div class="col-6">
          <div class="detail-field-label">Resuelta por</div>
          <div class="detail-field-value fw-medium">${esc(a.resolved_by)}</div>
        </div>` : ''}
        ${a.resolved_at ? `<div class="col-6">
          <div class="detail-field-label">Fecha de resolucion</div>
          <div class="detail-field-value">${esc(a.resolved_at)}</div>
        </div>` : ''}
      </div>
      ${a.resolution_comment ? `
        <div class="mt-2 pt-2 border-top" style="border-color: rgba(25,135,84,.15) !important;">
          <div class="detail-field-label">Comentario</div>
          <div class="detail-field-value fst-italic">"${esc(a.resolution_comment)}"</div>
        </div>` : ''}
    </div>`;
  }

  if (!a.is_resolved && a.extra_data && Object.keys(a.extra_data).length) {
    const rows = Object.entries(a.extra_data)
      .map(([k, v]) => `<tr><th class="py-2 px-3">${esc(translateExtraKey(k))}</th><td class="py-2 px-3">${esc(formatExtraValue(k, v))}</td></tr>`)
      .join('');
    bodyHtml += `
    <div class="mb-2">
      <div class="detail-field-label mb-1">Datos adicionales</div>
      <div class="detail-extra-box">
        <table class="table table-sm mb-0">${rows}</table>
      </div>
    </div>`;
  }

  document.getElementById('detail-body').innerHTML = bodyHtml;

  let footerHtml = '';
  if (!a.is_resolved) {
    if (!a.is_read) {
      footerHtml += `<button class="btn btn-sm btn-outline-secondary" onclick="quickAction('${esc(a.read_url)}')">
        <i class="bi bi-envelope-open me-1"></i>Marcar leida</button>`;
    }
    footerHtml += `<button class="btn btn-sm btn-success ms-auto"
        onclick="detailModal.hide(); openResolveModal('${esc(a.resolve_url)}','${esc(a.title)}','${esc(a.message)}')">
        <i class="bi bi-check-lg me-1"></i>Resolver</button>`;
  } else {
    footerHtml += `<button class="btn btn-sm btn-outline-warning" onclick="quickAction('${esc(a.reopen_url)}')">
      <i class="bi bi-arrow-counterclockwise me-1"></i>Reabrir</button>`;
    footerHtml += `<span class="ms-auto"></span>`;
  }
  footerHtml += `<button type="button" class="btn btn-sm btn-outline-secondary"
      data-bs-dismiss="modal">Cerrar</button>`;
  document.getElementById('detail-footer').innerHTML = footerHtml;
}

function quickAction(url) {
  fetch(url, { method: 'POST', headers: { 'Accept': 'application/json' } })
    .then(() => { detailModal.hide(); doFetch(); });
}

// ── Paginación ────────────────────────────────────────────────────────────────
function renderPagination(total, pages, page) {
  const el = document.getElementById('alerts-pagination');
  if (pages <= 1) { el.classList.add('d-none'); return; }
  el.classList.remove('d-none');

  const start = PER_PAGE * (page - 1) + 1;
  const end   = Math.min(PER_PAGE * page, total);

  const pArr = [];
  for (let i = 1; i <= pages; i++) {
    if (i <= 2 || i >= pages - 1 || Math.abs(i - page) <= 2) pArr.push(i);
    else if (pArr[pArr.length - 1] !== null) pArr.push(null);
  }

  el.innerHTML = `
    <span class="small text-muted">${start}–${end} de ${total}</span>
    <nav><ul class="pagination pagination-sm mb-0">
      <li class="page-item ${page <= 1 ? 'disabled' : ''}">
        <button class="page-link" onclick="goToPage(${page - 1})">‹</button>
      </li>
      ${pArr.map(p => p === null
        ? `<li class="page-item disabled"><span class="page-link">…</span></li>`
        : `<li class="page-item ${p === page ? 'active' : ''}">
             <button class="page-link" onclick="goToPage(${p})">${p}</button>
           </li>`
      ).join('')}
      <li class="page-item ${page >= pages ? 'disabled' : ''}">
        <button class="page-link" onclick="goToPage(${page + 1})">›</button>
      </li>
    </ul></nav>`;
}

function goToPage(p) {
  _curPage = p;
  doFetch(false, true);
  document.querySelector('.table-responsive')
          .scrollIntoView({ behavior: 'smooth', block: 'nearest' });
}

// ── Configuración de umbrales ─────────────────────────────────────────────────
const THRESHOLD_META = {
  'alert.quota_exceeded_pct':  { label: 'Cuota — exceso',       unit: '%',  icon: 'bi-hdd-fill',           color: '#dc3545', bg: 'rgba(220,53,69,.1)',
    tip: 'Genera una alerta critica cuando un usuario supera este porcentaje de uso de su cuota asignada.' },
  'alert.quota_warning_pct':   { label: 'Cuota — aviso',        unit: '%',  icon: 'bi-hdd',                color: '#fd7e14', bg: 'rgba(253,126,20,.1)',
    tip: 'Genera un aviso preventivo cuando un usuario alcanza este porcentaje de uso de su cuota.' },
  'alert.repeated_errors_n':   { label: 'Errores repetidos',    unit: 'nº', icon: 'bi-exclamation-circle', color: '#6f42c1', bg: 'rgba(111,66,193,.1)',
    tip: 'Numero de errores similares necesarios para generar una alerta por repeticion.' },
  'alert.repeated_errors_hrs': { label: 'Ventana de errores',   unit: 'h',  icon: 'bi-clock-history',      color: '#6f42c1', bg: 'rgba(111,66,193,.08)',
    tip: 'Periodo de tiempo usado para agrupar errores recientes de sincronizacion.' },
  'alert.sync_max_hours':      { label: 'Horas sin sync',       unit: 'h',  icon: 'bi-arrow-repeat',       color: '#0d6efd', bg: 'rgba(13,110,253,.08)',
    tip: 'Numero maximo de horas permitidas sin una sincronizacion correcta antes de generar una alerta.' },
};
let _thresholdData = {};

document.getElementById('btn-toggle-config').addEventListener('click', () => {
  const panel   = document.getElementById('threshold-panel');
  const isHidden = panel.classList.contains('d-none');
  panel.classList.toggle('d-none', !isHidden);
  if (isHidden) loadThresholds();
});

document.getElementById('btn-close-config').addEventListener('click', () => {
  document.getElementById('threshold-panel').classList.add('d-none');
});

function loadThresholds() {
  fetch(CONFIG_URL, { headers: { 'Accept': 'application/json' } })
    .then(r => r.json())
    .then(data => {
      _thresholdData = data.thresholds || {};
      const fields = document.getElementById('threshold-fields');
      fields.innerHTML = Object.entries(_thresholdData).map(([key, info]) => {
        const meta  = THRESHOLD_META[key] || { label: key, unit: '', icon: 'bi-sliders', color: '#6c757d', bg: '#f8f9fa', tip: '' };
        const domId = 'thr-' + key.replace(/\./g, '_');
        const tipAttr = meta.tip
          ? `data-bs-toggle="tooltip" data-bs-placement="top" data-bs-title="${esc(meta.tip)}"`
          : '';
        return `
        <div class="thr-tile" ${tipAttr} style="border-left: 3px solid ${meta.color};">
          <div class="thr-icon" style="background:${meta.bg};">
            <i class="bi ${meta.icon}" style="color:${meta.color};"></i>
          </div>
          <div class="flex-grow-1">
            <div class="thr-label">
              ${esc(meta.label)}
              ${meta.tip ? `<i class="bi bi-question-circle ms-1 opacity-50" style="font-size:.65rem;"></i>` : ''}
            </div>
            <div class="thr-val d-flex align-items-center gap-1 mt-1">
              <input type="number" id="${domId}" data-key="${key}"
                     value="${info.value}" min="1" max="9999"
                     style="border-color:${meta.color}40;">
              <span class="text-muted small">${esc(meta.unit)}</span>
            </div>
          </div>
        </div>`;
      }).join('');
      document.querySelectorAll('#threshold-fields [data-bs-toggle="tooltip"]').forEach(
        el => new bootstrap.Tooltip(el)
      );
    })
    .catch(() => {
      document.getElementById('threshold-fields').innerHTML =
        '<span class="text-danger small"><i class="bi bi-x-circle me-1"></i>Error al cargar la configuración.</span>';
    });
}

// ── Confirm threshold save modal ──────────────────────────────────────────────
const confirmThresholdModal = new bootstrap.Modal(document.getElementById('confirmThresholdModal'));
let _pendingThresholdBody = {};

document.getElementById('btn-save-thresholds').addEventListener('click', () => {
  const newVals = {};
  document.querySelectorAll('#threshold-fields input[data-key]').forEach(inp => {
    newVals[inp.dataset.key] = parseInt(inp.value) || 0;
  });

  const diffBody = document.getElementById('threshold-diff-body');
  let rows = '';
  let hasChanges = false;
  for (const [key, info] of Object.entries(_thresholdData)) {
    const meta   = THRESHOLD_META[key] || { label: key, unit: '', icon: 'bi-sliders', color: '#6c757d' };
    const oldVal = info.value;
    const newVal = newVals[key] ?? oldVal;
    const changed = oldVal !== newVal;
    if (changed) hasChanges = true;
    rows += `<tr${changed ? ' class="table-warning"' : ''}>
      <td><i class="bi ${meta.icon} me-1" style="color:${meta.color};"></i>${esc(meta.label)}</td>
      <td class="text-muted">${oldVal} ${esc(meta.unit)}</td>
      <td class="fw-semibold">${changed ? newVal + ' ' + esc(meta.unit) : '<span class=text-muted>sin cambios</span>'}</td>
    </tr>`;
  }
  diffBody.innerHTML = rows;

  if (!hasChanges) {
    document.getElementById('threshold-panel').classList.add('d-none');
    return;
  }

  _pendingThresholdBody = newVals;
  confirmThresholdModal.show();
});

document.getElementById('confirm-threshold-btn').addEventListener('click', () => {
  const btn = document.getElementById('confirm-threshold-btn');
  btn.disabled = true;
  btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Guardando…';
  fetch(CONFIG_URL, {
    method:  'POST',
    headers: { 'Content-Type': 'application/json', 'Accept': 'application/json' },
    body:    JSON.stringify(_pendingThresholdBody),
  })
    .then(r => r.json())
    .then(data => {
      confirmThresholdModal.hide();
      if (data.ok) {
        document.getElementById('threshold-panel').classList.add('d-none');
        fetch(RECALC_URL, { method: 'POST', headers: { 'Accept': 'application/json' } })
          .then(() => doFetch());
      } else {
        const msg = document.getElementById('threshold-msg');
        msg.className = 'small ms-1 text-danger';
        msg.textContent = data.msg || 'Error al guardar.';
        msg.classList.remove('d-none');
        setTimeout(() => msg.classList.add('d-none'), 4000);
      }
    })
    .catch(() => {
      confirmThresholdModal.hide();
      const msg = document.getElementById('threshold-msg');
      msg.className = 'small ms-1 text-danger';
      msg.textContent = 'Error de red.';
      msg.classList.remove('d-none');
    })
    .finally(() => {
      btn.disabled = false;
      btn.innerHTML = '<i class="bi bi-check2 me-1"></i>Confirmar y guardar';
    });
});

// ── Preferencias de notificación ──────────────────────────────────────────────
// La lógica del modal (abrir, cargar, renderizar, guardar) vive en
// js/notif-modal.js y se activa con [data-notif-open]. Aquí sólo dejamos el
// resumen específico de esta página, que se vuelve a calcular tras guardar
// (ver window.NOTIF_ON_SAVE definido en alerts/list.html).
function loadNotifSummary() {
  fetch(NOTIF_URL, { headers: { 'Accept': 'application/json' } })
    .then(r => r.json())
    .then(data => {
      const prefs = data.prefs || {};
      // Contar cuántos tipos tienen al menos un modo activo (inmediato o periódico)
      const imm   = prefs.immediate || {};
      const dig   = prefs.digest    || {};
      const keys  = Object.keys(Object.keys(imm).length ? imm : dig);
      const total  = keys.length;
      const active = keys.filter(k => imm[k] || dig[k]).length;
      const el     = document.getElementById('notif-summary-val');
      const color  = active === 0 ? 'text-muted' : active < 4 ? 'text-warning' : 'text-primary';
      el.innerHTML = `<span class="${color}">${active}</span><span class="text-muted fw-normal" style="font-size:.72rem;"> / ${total} activas</span>`;
    })
    .catch(() => {
      const el = document.getElementById('notif-summary-val');
      if (el) el.innerHTML = '<span class="text-muted small">—</span>';
    });
}

// ── Init ──────────────────────────────────────────────────────────────────────
doFetch();
scheduleAutoRefresh();
loadNotifSummary();

// Auto-open desde dashboard con ?open=<id>
(function () {
  const params  = new URLSearchParams(window.location.search);
  const openId  = params.get('open');
  if (openId) {
    const url = ALERT_DETAIL_URL_TPL.replace('/0', '/' + openId);
    setTimeout(() => openDetailModal(url), 400);
  }
})();
