/**
 * Overleaf Admin Platform — Projects list page
 *
 * Espera que el template defina antes de cargar este archivo:
 *   SEARCH_URL     — endpoint AJAX de búsqueda
 *   INITIAL_STATE  — { q, owner_id, owner_name, date_from, date_to,
 *                      indicators (array), sort, order }
 *
 * Globales de utils.js disponibles: esc()
 */

const OP_LABEL = { gt: 'Más de', eq: 'Igual a', lt: 'Menos de' };

// ── Estado central (seed desde template) ──────────────────────────────────────
const state = {
  ...INITIAL_STATE,
  page: 1,
};

// ── Parámetros de URL ─────────────────────────────────────────────────────────
function buildParams() {
  const p = new URLSearchParams();
  if (state.q)         p.set('q',         state.q);
  if (state.owner_id)  p.set('owner_id',  state.owner_id);
  if (state.date_from) p.set('date_from', state.date_from);
  if (state.date_to)   p.set('date_to',   state.date_to);
  if (state.size_op && state.size_mb != null) {
    p.set('size_op', state.size_op);
    p.set('size_mb', state.size_mb);
  }
  if (state.members_op && state.members_val != null) {
    p.set('members_op',  state.members_op);
    p.set('members_val', state.members_val);
  }
  p.set('sort',  state.sort);
  p.set('order', state.order);
  p.set('page',  state.page);
  return p;
}

// ── Fetch + render ────────────────────────────────────────────────────────────
async function doFetch(page) {
  state.page = page || 1;
  state.q    = document.getElementById('proj-search').value.trim();

  const params = buildParams();
  history.pushState(null, '', window.location.pathname + '?' + params.toString());

  const tbody = document.getElementById('projects-tbody');
  tbody.classList.add('tbody-loading');
  document.getElementById('proj-spinner').classList.remove('d-none');

  try {
    const resp = await fetch(SEARCH_URL + '?' + params.toString());
    if (!resp.ok) throw new Error('server error');
    const data = await resp.json();
    renderTable(data.projects);
    renderPagination(data);
    updateCounter(data.total);
    renderChips();
    requestAnimationFrame(() => tbody.classList.remove('tbody-loading'));
  } catch (e) {
    tbody.innerHTML = `
      <tr><td colspan="6" class="text-center py-4 text-danger">
        <i class="bi bi-exclamation-triangle me-2"></i>Error al cargar proyectos.
      </td></tr>`;
    requestAnimationFrame(() => tbody.classList.remove('tbody-loading'));
  } finally {
    document.getElementById('proj-spinner').classList.add('d-none');
  }
}

// Alias para handlers que llaman submitForm()
function submitForm() { doFetch(1); }
window.submitForm = submitForm;

// ── Render: tabla ─────────────────────────────────────────────────────────────
function renderTable(projects) {
  const tbody = document.getElementById('projects-tbody');
  if (!projects.length) {
    tbody.innerHTML = `<tr><td colspan="6" class="text-center py-5 text-muted">
      <i class="bi bi-folder-x fs-1 d-block mb-3 opacity-50"></i>
      No hay proyectos que coincidan con los filtros aplicados.
    </td></tr>`;
    return;
  }
  tbody.innerHTML = projects.map(buildRow).join('');
  attachTooltips();
}

function buildRow(p) {
  const url = esc(p.detail_url);

  // Propietario como "pill" clickable: deja claro hasta dónde llega el área
  // que lleva a /usuarios/<id>. El stopPropagation impide que el click se
  // propague al <tr> (que llevaría al detalle del proyecto).
  const ownerHtml = p.owner_name
    ? `<a href="${esc(p.owner_url)}"
          class="owner-pill text-decoration-none"
          onclick="event.stopPropagation()"
          title="Ver perfil de ${esc(p.owner_name)}">
         <i class="bi bi-person-fill"></i>${esc(p.owner_name)}
       </a>`
    : `<span class="text-muted">—</span>`;

  let membersHtml = `<span class="text-muted small">—</span>`;
  if (p.member_count > 0) {
    const tipContent = p.member_names.map(n => esc(n)).join('<br>');
    membersHtml = `<span class="collab-cell" onclick="event.stopPropagation()">
      <span class="badge bg-info-subtle text-info-emphasis">
        <i class="bi bi-people-fill me-1"></i>${p.member_count}
      </span>
      <span class="collab-tip">${tipContent}</span>
    </span>`;
  }

  const sizeHtml = p.size_fmt ? esc(p.size_fmt) : `<span class="opacity-50">—</span>`;

  return `<tr class="row-clickable" onclick="window.location='${url}'">
    <td class="ps-3 fw-medium small">
      <a href="${url}" class="text-decoration-none text-body" onclick="event.stopPropagation()">${esc(p.name) || '—'}</a>
    </td>
    <td class="small">${ownerHtml}</td>
    <td class="text-center">${membersHtml}</td>
    <td class="text-end small text-muted">${sizeHtml}</td>
    <td class="small text-muted">${p.last_updated_at || '—'}</td>
    <td class="small text-muted">${p.created_at || '—'}</td>
  </tr>`;
}

// ── Render: paginación ────────────────────────────────────────────────────────
function renderPagination(data) {
  const wrap = document.getElementById('proj-pagination');
  const ul   = document.getElementById('proj-pages');
  if (data.pages <= 1) { wrap.classList.add('d-none'); return; }
  wrap.classList.remove('d-none');

  const start = data.per_page * (data.page - 1) + 1;
  const end   = Math.min(data.per_page * data.page, data.total);
  wrap.querySelector('span.small').textContent = `${start}–${end} de ${data.total}`;

  const pages = [];
  for (let i = 1; i <= data.pages; i++) {
    if (i <= 2 || i >= data.pages - 1 || Math.abs(i - data.page) <= 2) pages.push(i);
    else if (pages[pages.length - 1] !== null) pages.push(null);
  }

  ul.innerHTML = `
    <li class="page-item ${!data.has_prev ? 'disabled' : ''}">
      <button class="page-link" ${data.has_prev ? `onclick="doFetch(${data.prev_num})"` : ''}>‹</button>
    </li>
    ${pages.map(p => p === null
      ? `<li class="page-item disabled"><span class="page-link">…</span></li>`
      : `<li class="page-item ${p === data.page ? 'active' : ''}">
           <button class="page-link" onclick="doFetch(${p})">${p}</button>
         </li>`
    ).join('')}
    <li class="page-item ${!data.has_next ? 'disabled' : ''}">
      <button class="page-link" ${data.has_next ? `onclick="doFetch(${data.next_num})"` : ''}>›</button>
    </li>`;
}
window.doFetch = doFetch;

// ── Render: contador ──────────────────────────────────────────────────────────
function updateCounter(total) {
  document.getElementById('proj-counter').innerHTML =
    `<strong>${total}</strong> proyecto${total !== 1 ? 's' : ''}`;
}

// ── Tooltips colaboradores ────────────────────────────────────────────────────
function attachTooltips() {
  document.querySelectorAll('.collab-cell').forEach(cell => {
    const tip = cell.querySelector('.collab-tip');
    if (!tip) return;
    cell.addEventListener('mouseenter', () => {
      const r = cell.getBoundingClientRect();
      tip.style.top     = (r.top + r.height / 2) + 'px';
      tip.style.left    = (r.right + 10) + 'px';
      tip.style.display = 'block';
    });
    cell.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
  });
}

// ── Ordenación (server-side) ──────────────────────────────────────────────────
(function initSort() {
  document.querySelectorAll('th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const col = th.dataset.col;
      state.order = (state.sort === col && state.order === 'asc') ? 'desc' : 'asc';
      state.sort  = col;
      updateSortUI();
      doFetch(1);
    });
  });
  updateSortUI();
})();

function updateSortUI() {
  document.querySelectorAll('th.sortable').forEach(th => {
    const icon = th.querySelector('.sort-icon');
    th.classList.remove('sort-asc', 'sort-desc');
    if (state.sort === th.dataset.col) {
      th.classList.add('sort-' + state.order);
      icon.className = `sort-icon bi bi-chevron-${state.order === 'asc' ? 'up' : 'down'}`;
    } else {
      icon.className = 'sort-icon bi bi-chevron-expand';
    }
  });
}

// ── Buscador (debounce + Enter) ───────────────────────────────────────────────
(function () {
  const input = document.getElementById('proj-search');
  let timer = null;
  input.addEventListener('input', () => {
    clearTimeout(timer);
    timer = setTimeout(() => doFetch(1), 400);
  });
  input.addEventListener('keydown', e => {
    if (e.key === 'Enter') { e.preventDefault(); clearTimeout(timer); doFetch(1); }
  });
})();

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
  document.querySelectorAll('.dropdown').forEach(dd => {
    const btn  = dd.querySelector('.dropdown-toggle');
    const menu = dd.querySelector('.dropdown-menu');
    if (!btn || !menu) return;
    menu.style.position = 'absolute';
    menu.style.zIndex   = '1055';
    btn.addEventListener('click', e => {
      e.stopPropagation();
      const open = dd.classList.contains('show');
      closeAll();
      if (!open) { dd.classList.add('show'); menu.classList.add('show'); }
    });
    menu.addEventListener('click', e => e.stopPropagation());
  });
  document.addEventListener('click', () => closeAll());
})();

function closeDropdown(id) {
  const dd = document.getElementById(id);
  if (!dd) return;
  dd.classList.remove('show');
  const m = dd.querySelector('.dropdown-menu');
  if (m) m.classList.remove('show');
}
window.closeDropdown = closeDropdown;

// ── Filtro: PROPIETARIO ───────────────────────────────────────────────────────
document.getElementById('owner-search-input').addEventListener('input', function () {
  const q = this.value.toLowerCase();
  document.querySelectorAll('#owner-list .owner-option').forEach(opt => {
    opt.style.display = opt.dataset.name.toLowerCase().includes(q) ? '' : 'none';
  });
});

document.querySelectorAll('.owner-option').forEach(btn => {
  btn.addEventListener('click', () => {
    const id   = btn.dataset.id;
    const name = btn.dataset.name;
    state.owner_id   = id ? parseInt(id) : null;
    state.owner_name = id ? name : '';

    const lblEl  = document.getElementById('owner-btn-label');
    const btnEl  = document.getElementById('btn-f-owner');
    const iconEl = btnEl.querySelector('i');
    if (id) {
      lblEl.textContent = name;
      btnEl.classList.add('has-filter');
      iconEl.className = 'bi bi-person-fill me-1';
    } else {
      lblEl.textContent = 'Propietario';
      btnEl.classList.remove('has-filter');
      iconEl.className = 'bi bi-person me-1';
    }
    closeDropdown('dd-owner');
    doFetch(1);
  });
});

// ── Filtro: FECHAS ────────────────────────────────────────────────────────────
function applyDateFilter() {
  state.date_from = document.getElementById('f-date-from').value;
  state.date_to   = document.getElementById('f-date-to').value;
  const btn  = document.getElementById('btn-f-date');
  const icon = btn.querySelector('i');
  if (state.date_from || state.date_to) {
    btn.classList.add('has-filter');
    icon.className = 'bi bi-calendar-check me-1';
  } else {
    btn.classList.remove('has-filter');
    icon.className = 'bi bi-calendar3 me-1';
  }
  closeDropdown('dd-date');
  doFetch(1);
}
function clearDateFilter() {
  state.date_from = '';
  state.date_to   = '';
  document.getElementById('f-date-from').value = '';
  document.getElementById('f-date-to').value   = '';
  const btn = document.getElementById('btn-f-date');
  btn.classList.remove('has-filter');
  btn.querySelector('i').className = 'bi bi-calendar3 me-1';
  closeDropdown('dd-date');
  doFetch(1);
}
window.applyDateFilter  = applyDateFilter;
window.clearDateFilter  = clearDateFilter;

// ── Filtro: TAMAÑO ────────────────────────────────────────────────────────────
function applySizeFilter() {
  const op  = document.getElementById('f-size-op').value;
  const raw = document.getElementById('f-size-val').value.trim();
  const val = parseFloat(raw);
  if (raw === '' || isNaN(val) || val < 0) {
    state.size_op = null; state.size_mb = null;
  } else {
    state.size_op = op; state.size_mb = val;
  }
  document.getElementById('btn-f-size').classList.toggle('has-filter', !!state.size_op);
  closeDropdown('dd-size');
  doFetch(1);
}
document.getElementById('f-size-add').addEventListener('click', applySizeFilter);
document.getElementById('f-size-val').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); applySizeFilter(); }
});

// ── Filtro: COLABORADORES ─────────────────────────────────────────────────────
function applyMembersFilter() {
  const op  = document.getElementById('f-members-op').value;
  const raw = document.getElementById('f-members-val').value.trim();
  const val = parseInt(raw, 10);
  if (raw === '' || isNaN(val) || val < 0) {
    state.members_op = null; state.members_val = null;
  } else {
    state.members_op = op; state.members_val = val;
  }
  document.getElementById('btn-f-members').classList.toggle('has-filter', !!state.members_op);
  closeDropdown('dd-members');
  doFetch(1);
}
document.getElementById('f-members-add').addEventListener('click', applyMembersFilter);
document.getElementById('f-members-val').addEventListener('keydown', e => {
  if (e.key === 'Enter') { e.preventDefault(); applyMembersFilter(); }
});

// ── Chips ─────────────────────────────────────────────────────────────────────
function renderChips() {
  const chipsData = [];

  if (state.owner_id && state.owner_name) {
    chipsData.push({
      label: state.owner_name, icon: 'bi-person-fill',
      clear: () => {
        state.owner_id   = null;
        state.owner_name = '';
        const btnEl  = document.getElementById('btn-f-owner');
        document.getElementById('owner-btn-label').textContent = 'Propietario';
        btnEl.classList.remove('has-filter');
        btnEl.querySelector('i').className = 'bi bi-person me-1';
        doFetch(1);
      },
    });
  }

  if (state.date_from || state.date_to) {
    let label = '';
    if (state.date_from && state.date_to) label = state.date_from + ' – ' + state.date_to;
    else if (state.date_from) label = 'Desde ' + state.date_from;
    else                      label = 'Hasta ' + state.date_to;
    chipsData.push({ label, icon: 'bi-calendar3', clear: () => clearDateFilter() });
  }

  if (state.size_op && state.size_mb != null) {
    chipsData.push({
      label: `Tamaño ${OP_LABEL[state.size_op]} ${state.size_mb} MB`,
      icon: 'bi-hdd',
      clear: () => {
        state.size_op = null; state.size_mb = null;
        document.getElementById('btn-f-size').classList.remove('has-filter');
        document.getElementById('f-size-val').value = '';
        doFetch(1);
      },
    });
  }

  if (state.members_op && state.members_val != null) {
    chipsData.push({
      label: `Colaboradores ${OP_LABEL[state.members_op]} ${state.members_val}`,
      icon: 'bi-people',
      clear: () => {
        state.members_op = null; state.members_val = null;
        document.getElementById('btn-f-members').classList.remove('has-filter');
        document.getElementById('f-members-val').value = '';
        doFetch(1);
      },
    });
  }

  const row = document.getElementById('chips-row');
  if (!chipsData.length) { row.classList.add('d-none'); row.innerHTML = ''; return; }
  row.classList.remove('d-none');

  // "Limpiar todo" se muestra siempre que haya al menos 1 filtro.
  row.innerHTML = chipsData.map((c, i) => `
    <span class="filter-chip" data-chip="${i}">
      <i class="bi ${esc(c.icon)} me-1"></i>${esc(c.label)}
      <button class="chip-remove" data-chip="${i}" title="Quitar">✕</button>
    </span>`
  ).join('') + `
    <button type="button" class="btn btn-sm btn-link text-danger text-decoration-none p-0 ms-1"
            id="btn-clear-all">
      <i class="bi bi-x-circle me-1"></i>Limpiar todo
    </button>`;

  chipsData.forEach((c, i) => {
    row.querySelector(`[data-chip="${i}"].chip-remove`)
       .addEventListener('click', () => c.clear());
  });

  document.getElementById('btn-clear-all').addEventListener('click', () => {
    state.owner_id    = null; state.owner_name = '';
    state.date_from   = '';   state.date_to    = '';
    state.size_op     = null; state.size_mb    = null;
    state.members_op  = null; state.members_val = null;
    state.q = '';
    document.getElementById('proj-search').value = '';
    document.getElementById('btn-f-owner').classList.remove('has-filter');
    document.getElementById('owner-btn-label').textContent = 'Propietario';
    document.getElementById('btn-f-owner').querySelector('i').className = 'bi bi-person me-1';
    document.getElementById('btn-f-date').classList.remove('has-filter');
    document.getElementById('btn-f-date').querySelector('i').className = 'bi bi-calendar3 me-1';
    document.getElementById('btn-f-size').classList.remove('has-filter');
    document.getElementById('f-size-val').value = '';
    document.getElementById('btn-f-members').classList.remove('has-filter');
    document.getElementById('f-members-val').value = '';
    doFetch(1);
  });
}

// ── Init ──────────────────────────────────────────────────────────────────────
renderChips();
attachTooltips();
