/**
 * Overleaf Admin Platform — Users list page
 *
 * Espera que el template defina antes de cargar este archivo:
 *   SEARCH_URL  — endpoint de búsqueda AJAX
 *   PER_PAGE    — filas por página
 *
 * Globales de utils.js disponibles: esc(), formatBytes(), debounce()
 */

// ── Estado ────────────────────────────────────────────────────────────────────
let sortState     = { col: 'email', order: 'asc' };
let debounceTimer = null;
let activeFilters = [];
let _nextId       = 0;
let _curPage      = 1;
let _totalRows    = 0;
let _totalPages   = 0;

// ── Búsqueda con debounce ─────────────────────────────────────────────────────
document.getElementById('user-search').addEventListener('input', () => {
  clearTimeout(debounceTimer);
  _curPage = 1;
  debounceTimer = setTimeout(doFetch, 350);
});

// ── Ordenación ────────────────────────────────────────────────────────────────
document.querySelectorAll('th.sortable').forEach(th => {
  th.addEventListener('click', () => {
    const col = th.dataset.col;
    sortState.order = (sortState.col === col && sortState.order === 'asc') ? 'desc' : 'asc';
    sortState.col   = col;
    updateSortUI();
    _curPage = 1;
    doFetch();
  });
});

function updateSortUI() {
  document.querySelectorAll('th.sortable').forEach(th => {
    const icon = th.querySelector('.sort-icon');
    th.classList.remove('sort-asc', 'sort-desc');
    if (sortState.col === th.dataset.col) {
      th.classList.add('sort-' + sortState.order);
      icon.className = `sort-icon bi bi-chevron-${sortState.order === 'asc' ? 'up' : 'down'}`;
    } else {
      icon.className = 'sort-icon bi bi-chevron-expand';
    }
  });
}

// ── Dropdown vanilla ──────────────────────────────────────────────────────────
(function () {
  function closeAll(except) {
    document.querySelectorAll('.dropdown').forEach(d => {
      if (d === except) return;
      d.classList.remove('show');
      const m = d.querySelector('.dropdown-menu');
      if (m) m.classList.remove('show');
    });
  }
  document.querySelectorAll('.dropdown').forEach(dropdown => {
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
  const dd = document.getElementById(btnId).closest('.dropdown');
  dd.classList.remove('show');
  dd.querySelector('.dropdown-menu').classList.remove('show');
}

// ── Gestión de filtros ────────────────────────────────────────────────────────
function addFilter(type, op, val, label) {
  activeFilters.push({ id: _nextId++, type, op, val, label });
  syncChips(); syncFilterBtns();
  _curPage = 1;
  doFetch();
}
function removeFilter(id) {
  activeFilters = activeFilters.filter(f => f.id !== id);
  syncChips(); syncFilterBtns();
  _curPage = 1;
  doFetch();
}
function clearAllFilters() {
  activeFilters = [];
  syncChips(); syncFilterBtns();
  _curPage = 1;
  doFetch();
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
  [['projects', 'btn-f-projects'], ['quota', 'btn-f-quota'], ['access', 'btn-f-access']].forEach(([type, id]) => {
    const btn = document.getElementById(id);
    const on  = active.has(type);
    btn.classList.toggle('has-filter', on);
    btn.classList.toggle('btn-outline-secondary', !on);
  });
}

// ── Filtro PROYECTOS ──────────────────────────────────────────────────────────
function addProjectsFilter() {
  const raw = document.getElementById('f-projects-val').value.trim();
  const val = parseInt(raw, 10);
  if (raw === '' || isNaN(val) || val < 0) return;
  const op    = document.getElementById('f-projects-op').value;
  const opSym = { gte: '≥', eq: '=', lte: '≤' }[op];
  addFilter('projects', op, val, `Proyectos ${opSym} ${val}`);
  document.getElementById('f-projects-val').value = '';
  closeDropdown('btn-f-projects');
}
document.getElementById('f-projects-add').addEventListener('click', addProjectsFilter);
document.getElementById('f-projects-val').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); addProjectsFilter(); }
});

// ── Filtro CUOTA ──────────────────────────────────────────────────────────────
function addQuotaFilter() {
  const raw = document.getElementById('f-quota-val').value.trim();
  const val = parseFloat(raw);
  if (raw === '' || isNaN(val) || val < 0) return;
  const op    = document.getElementById('f-quota-op').value;
  const opSym = { gte: '≥', lte: '≤' }[op];
  addFilter('quota', op, val, `Cuota ${opSym} ${val}%`);
  document.getElementById('f-quota-val').value = '';
  closeDropdown('btn-f-quota');
}
document.getElementById('f-quota-add').addEventListener('click', addQuotaFilter);
document.getElementById('f-quota-val').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); addQuotaFilter(); }
});
document.querySelectorAll('.f-quota-quick').forEach(btn => {
  btn.addEventListener('click', () => {
    addFilter('quota', btn.dataset.op, null, btn.dataset.label);
    closeDropdown('btn-f-quota');
  });
});

// ── Filtro ÚLTIMO ACCESO ──────────────────────────────────────────────────────
document.getElementById('btn-f-access').closest('.dropdown').querySelectorAll('[data-val]').forEach(item => {
  item.addEventListener('click', e => {
    e.preventDefault();
    activeFilters = activeFilters.filter(f => f.type !== 'access');
    addFilter('access', null, item.dataset.val, item.dataset.label);
    closeDropdown('btn-f-access');
  });
});

// ── Fetch (server-side) ───────────────────────────────────────────────────────
let _fetchController = null;

function doFetch() {
  if (_fetchController) _fetchController.abort();
  _fetchController = new AbortController();

  const q      = document.getElementById('user-search').value.trim();
  const params = new URLSearchParams({
    q, sort: sortState.col, order: sortState.order,
    page: _curPage, per_page: PER_PAGE,
  });

  if (activeFilters.length) {
    const serverFilters = activeFilters.map(f => ({ type: f.type, op: f.op, val: f.val }));
    params.set('filters', JSON.stringify(serverFilters));
  }

  const tbody = document.getElementById('users-tbody');
  if (_totalRows > 0) tbody.classList.add('tbody-loading');
  document.getElementById('search-spinner').classList.remove('d-none');

  fetch(`${SEARCH_URL}?${params}`, { signal: _fetchController.signal })
    .then(r => r.json())
    .then(data => {
      _totalRows  = data.total;
      _totalPages = data.pages;
      _curPage    = data.page;
      renderRows(data.users);
      renderPagination();
      updateCounter();
    })
    .catch(err => { if (err.name !== 'AbortError') console.error(err); })
    .finally(() => document.getElementById('search-spinner').classList.add('d-none'));
}

// ── Render rows ───────────────────────────────────────────────────────────────
function renderRows(users) {
  const tbody = document.getElementById('users-tbody');

  if (!users.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center py-5 text-muted">
      <i class="bi bi-people fs-1 d-block mb-3 opacity-50"></i>No se encontraron usuarios.
    </td></tr>`;
    requestAnimationFrame(() => tbody.classList.remove('tbody-loading'));
    return;
  }

  tbody.innerHTML = users.map(u => `
    <tr class="row-clickable" data-href="${esc(u.detail_url)}">
      <td class="ps-3 small"><span class="fw-medium">${esc(u.email) || '—'}</span></td>
      <td class="text-muted small">${esc(u.display_name) || '—'}</td>
      <td class="text-center small">${roleBadgeHtml(u)}</td>
      <td class="text-center small"><span class="badge bg-secondary">${u.projects_count}</span></td>
      <td class="small">${quotaCell(u)}</td>
      <td class="small text-muted">${u.signup_date || '—'}</td>
    </tr>`).join('');

  tbody.querySelectorAll('tr[data-href]').forEach(row =>
    row.addEventListener('click', () => { window.location.href = row.dataset.href; })
  );

  requestAnimationFrame(() => tbody.classList.remove('tbody-loading'));
}

function updateCounter() {
  const el = document.getElementById('result-count');
  el.innerHTML = `<strong>${_totalRows}</strong> usuario${_totalRows !== 1 ? 's' : ''}`;
}

// ── Paginación (server-side) ──────────────────────────────────────────────────
function goToPage(page) {
  if (page < 1 || page > _totalPages || page === _curPage) return;
  _curPage = page;
  document.getElementById('users-tbody').classList.add('tbody-loading');
  doFetch();
}
window.goToPage = goToPage;

function renderPagination() {
  const container = document.getElementById('users-pagination');
  if (_totalPages <= 1) { container.classList.add('d-none'); container.innerHTML = ''; return; }
  container.classList.remove('d-none');

  const start = PER_PAGE * (_curPage - 1) + 1;
  const end   = Math.min(PER_PAGE * _curPage, _totalRows);

  const pArr = [];
  for (let i = 1; i <= _totalPages; i++) {
    if (i <= 2 || i >= _totalPages - 1 || Math.abs(i - _curPage) <= 2) pArr.push(i);
    else if (pArr[pArr.length - 1] !== null) pArr.push(null);
  }

  container.innerHTML = `
    <span class="small text-muted">${start}–${end} de ${_totalRows}</span>
    <nav><ul class="pagination pagination-sm mb-0">
      <li class="page-item ${_curPage <= 1 ? 'disabled' : ''}">
        <button class="page-link" ${_curPage > 1 ? `onclick="goToPage(${_curPage - 1})"` : ''}>‹</button>
      </li>
      ${pArr.map(p => p === null
        ? `<li class="page-item disabled"><span class="page-link">…</span></li>`
        : `<li class="page-item ${p === _curPage ? 'active' : ''}">
             <button class="page-link" onclick="goToPage(${p})">${p}</button>
           </li>`
      ).join('')}
      <li class="page-item ${_curPage >= _totalPages ? 'disabled' : ''}">
        <button class="page-link" ${_curPage < _totalPages ? `onclick="goToPage(${_curPage + 1})"` : ''}>›</button>
      </li>
    </ul></nav>`;
}

// ── Helpers de celda ──────────────────────────────────────────────────────────
function roleBadgeHtml(u) {
  return u.is_admin
    ? `<span class="badge bg-warning text-dark"><i class="bi bi-shield-fill-check me-1"></i>Admin</span>`
    : `<span class="text-muted small">Usuario</span>`;
}

function quotaCell(u) {
  if (u.quota_percent === null) {
    return `<span class="small text-muted">${esc(u.quota_used_fmt)} <span class="opacity-50">/ sin límite</span></span>`;
  }
  const pct      = Math.min(u.quota_percent, 100);
  const exceeded = u.quota_exceeded
    ? `<span class="badge bg-danger mb-1"><i class="bi bi-exclamation-triangle-fill me-1"></i>Excedida</span><br>`
    : '';
  return `${exceeded}
    <div class="d-flex align-items-center gap-2">
      <div class="progress flex-grow-1" style="height:7px">
        <div class="progress-bar bg-${esc(u.quota_status)}" style="width:${pct}%"></div>
      </div>
      <span class="small text-muted text-nowrap">${pct}%</span>
    </div>
    <div class="small text-muted">${esc(u.quota_used_fmt)} / ${esc(u.quota_max_fmt)}</div>`;
}

// ── Init ──────────────────────────────────────────────────────────────────────
updateSortUI();
doFetch();
