/**
 * Overleaf Admin Platform — Role detail / config page
 *
 * Espera que el template defina antes de cargar este archivo:
 *   ROLE_QUOTA_BYTES   — bytes de cuota actual (int | null)
 *   ROLE_MAX_PROJECTS  — máximo de proyectos actual (int | null)
 *   ALL_USERS          — array de { id, name, email, used_bytes, projects_count }
 *   ROLE_NAME          — nombre del rol (string)
 *   SEARCH_URL         — endpoint de búsqueda de usuarios para este rol
 *   ROLES_LIST_URL     — URL del listado de roles (para navegación tras guardar)
 *
 * Globales de utils.js disponibles: esc(), formatBytes()
 */
(function () {
  'use strict';

  // ── Estado ───────────────────────────────────────────────────────────────
  let dirty         = false;
  let simQ          = ROLE_QUOTA_BYTES;
  let simP          = ROLE_MAX_PROJECTS;
  let sortBy        = 'name';
  let sortDir       = 'asc';
  let curPage       = 1;
  const PER_PAGE    = 7;
  let pendingNavUrl = null;

  // ── Refs DOM ─────────────────────────────────────────────────────────────
  const inpQVal    = document.getElementById('inp-quota-value');
  const inpQUnit   = document.getElementById('inp-quota-unit');
  const inpProj    = document.getElementById('inp-max-projects');
  const inpDesc    = document.getElementById('inp-description');
  const tbody      = document.getElementById('users-tbody');
  const pagDiv     = document.getElementById('users-pagination');
  const form       = document.getElementById('config-form');
  const leaveModal = document.getElementById('unsavedLeaveModal');
  const saveModal  = document.getElementById('confirmSaveModal');

  // ── Bootstrap Modals ─────────────────────────────────────────────────────
  const _bsAvail = typeof bootstrap !== 'undefined' && bootstrap.Modal;
  const _bsLeave = (_bsAvail && leaveModal) ? new bootstrap.Modal(leaveModal) : null;
  const _bsSave  = (_bsAvail && saveModal)  ? new bootstrap.Modal(saveModal)  : null;

  // ── Valores originales (detección robusta de cambios) ────────────────────
  const ORIG = {
    qVal  : inpQVal  ? inpQVal.value  : '',
    qUnit : inpQUnit ? inpQUnit.value : 'MB',
    proj  : inpProj  ? inpProj.value  : '',
    desc  : inpDesc  ? inpDesc.value  : '',
  };

  function hasChanges() {
    return (
      (inpQVal  && inpQVal.value  !== ORIG.qVal)  ||
      (inpQUnit && inpQUnit.value !== ORIG.qUnit) ||
      (inpProj  && inpProj.value  !== ORIG.proj)  ||
      (inpDesc  && inpDesc.value  !== ORIG.desc)
    );
  }
  function shouldIntercept() { return dirty || hasChanges(); }

  // fmtBytes — wrapper sobre formatBytes() de utils.js
  function fmtBytes(b) { return formatBytes(b, { nullOnZero: true }); }

  function setText(id, v) { const el = document.getElementById(id); if (el) el.textContent = v; }
  function toggleClass(id, cls, on) { const el = document.getElementById(id); if (el) el.classList.toggle(cls, on); }

  // ── Leer inputs ──────────────────────────────────────────────────────────
  function readQuota() {
    if (!inpQVal) return null;
    const v = parseFloat(inpQVal.value);
    if (!v || v <= 0) return null;
    return Math.round(v * (inpQUnit.value === 'GB' ? 1073741824 : 1048576));
  }
  function readProjects() {
    if (!inpProj) return null;
    const v = parseInt(inpProj.value, 10);
    return v > 0 ? v : null;
  }

  // ── Cálculo de impacto ────────────────────────────────────────────────────
  function computeImpact(qBytes, maxP) {
    let low = 0, med = 0, high = 0, exc = 0, projExc = 0;
    for (const u of ALL_USERS) {
      if (qBytes) {
        const pct = (u.used_bytes / qBytes) * 100;
        if      (pct > 100) exc++;
        else if (pct >  75) high++;
        else if (pct >  25) med++;
        else                low++;
      }
      if (maxP && u.projects_count > maxP) projExc++;
    }
    return { low, med, high, exc, projExc };
  }

  // ── Panel de impacto ──────────────────────────────────────────────────────
  function updateImpactPanel() {
    const imp  = computeImpact(simQ, simP);
    const hasQ = !!simQ;
    setText('stat-low',      hasQ ? imp.low  : '—');
    setText('stat-medium',   hasQ ? imp.med  : '—');
    setText('stat-high',     hasQ ? imp.high : '—');
    setText('stat-exceeded', hasQ ? imp.exc  : '—');
    toggleClass('no-quota-note', 'd-none', hasQ);
    toggleClass('proj-impact',   'd-none', simP === null);
    if (simP !== null) setText('stat-proj-exceeded', imp.projExc);
  }

  // ── Tabla de usuarios ─────────────────────────────────────────────────────
  function sortedUsers() {
    return [...ALL_USERS].sort((a, b) => {
      let va, vb;
      if (sortBy === 'quota') {
        va = simQ ? a.used_bytes / simQ : 0;
        vb = simQ ? b.used_bytes / simQ : 0;
        return sortDir === 'asc' ? va - vb : vb - va;
      }
      if (sortBy === 'projects') {
        va = a.projects_count; vb = b.projects_count;
        return sortDir === 'asc' ? va - vb : vb - va;
      }
      va = (a.name || a.email).toLowerCase();
      vb = (b.name || b.email).toLowerCase();
      return sortDir === 'asc' ? va.localeCompare(vb) : vb.localeCompare(va);
    });
  }

  function renderTable() {
    if (!tbody) return;
    const sorted = sortedUsers();
    const slice  = sorted.slice((curPage - 1) * PER_PAGE, curPage * PER_PAGE);

    tbody.innerHTML = slice.map(u => {
      const qPct    = simQ ? (u.used_bytes / simQ) * 100 : null;
      const qOver   = qPct !== null && qPct > 100;
      const qHigh   = qPct !== null && qPct > 75;
      const qMed    = qPct !== null && qPct > 25;
      const qCls    = qOver ? 'text-danger fw-semibold' : qHigh ? 'text-warning-emphasis' : qMed ? '' : 'text-success';
      const usedFmt = fmtBytes(u.used_bytes) || '0 B';
      const limFmt  = simQ ? (fmtBytes(simQ) || '∞') : '∞';
      const pctStr  = qPct !== null ? ` · ${Math.round(qPct)} %` : '';
      const qIcon   = qOver ? ' <i class="bi bi-exclamation-triangle-fill"></i>' : '';
      const pOver   = simP && u.projects_count > simP;
      const pCls    = pOver ? 'text-danger fw-semibold' : '';
      const projStr = simP ? `${u.projects_count} / ${simP}` : String(u.projects_count);
      const pIcon   = pOver ? ' <i class="bi bi-exclamation-triangle-fill"></i>' : '';

      return `<tr>
        <td class="ps-3">
          <a href="/usuarios/${u.id}" class="text-decoration-none fw-medium text-body small">${esc(u.name)}</a>
          ${u.email ? `<div class="text-muted" style="font-size:.7rem;">${esc(u.email)}</div>` : ''}
        </td>
        <td class="small ${qCls}">${usedFmt} / ${limFmt}${pctStr}${qIcon}</td>
        <td class="text-center small ${pCls}">${projStr}${pIcon}</td>
        <td class="text-end pe-3">
          <a href="/usuarios/${u.id}" class="btn btn-sm btn-outline-secondary py-0 px-2">
            <i class="bi bi-box-arrow-up-right"></i>
          </a>
        </td>
      </tr>`;
    }).join('');

    renderPagination(sorted.length);
    refreshSortIcons();
  }

  function renderPagination(total) {
    if (!pagDiv) return;
    const pages = Math.ceil(total / PER_PAGE);
    if (pages <= 1) { pagDiv.classList.add('d-none'); return; }
    pagDiv.classList.remove('d-none');
    const from = (curPage - 1) * PER_PAGE + 1;
    const to   = Math.min(curPage * PER_PAGE, total);
    let html = `<span class="small text-muted">${from}–${to} de ${total}</span>
                <nav><ul class="pagination pagination-sm mb-0">`;
    html += `<li class="page-item ${curPage === 1 ? 'disabled' : ''}">
               <button class="page-link" onclick="goPage(${curPage - 1})">‹</button></li>`;
    for (let p = 1; p <= pages; p++) {
      html += `<li class="page-item ${p === curPage ? 'active' : ''}">
                 <button class="page-link" onclick="goPage(${p})">${p}</button></li>`;
    }
    html += `<li class="page-item ${curPage === pages ? 'disabled' : ''}">
               <button class="page-link" onclick="goPage(${curPage + 1})">›</button></li>`;
    html += '</ul></nav>';
    pagDiv.innerHTML = html;
  }

  function refreshSortIcons() {
    document.querySelectorAll('#users-table th.sortable').forEach(th => {
      const active = th.dataset.sort === sortBy;
      th.classList.toggle('sort-active', active);
      const icon = th.querySelector('.sort-icon');
      if (!icon) return;
      icon.style.opacity = '';
      icon.style.color   = '';
      icon.className = active
        ? `bi bi-arrow-${sortDir === 'asc' ? 'up' : 'down'} sort-icon ms-1`
        : 'bi bi-arrow-down-up sort-icon ms-1';
    });
  }

  // ── Cambio de inputs ──────────────────────────────────────────────────────
  function onInputChange() {
    simQ = readQuota();
    simP = readProjects();
    setDirty(true);
    updateImpactPanel();
    curPage = 1;
    renderTable();
  }

  function setDirty(on) {
    dirty = on;
    toggleClass('sim-badge',       'd-none', !on);
    toggleClass('sim-table-badge', 'd-none', !on);
    const btn = document.getElementById('save-btn');
    if (btn) {
      btn.disabled = !on;
      btn.classList.toggle('btn-ol',        on);
      btn.classList.toggle('btn-secondary', !on);
    }
  }

  // Exponer goPage para onclick inline en paginación renderizada
  window.goPage = p => { curPage = p; renderTable(); };

  // ── Ordenación ────────────────────────────────────────────────────────────
  document.querySelectorAll('#users-table th.sortable').forEach(th => {
    th.addEventListener('click', () => {
      const f = th.dataset.sort;
      sortDir = (sortBy === f && sortDir === 'asc') ? 'desc' : 'asc';
      sortBy  = f;
      curPage = 1;
      renderTable();
    });
  });

  // ── Modal: Guardar ────────────────────────────────────────────────────────
  document.getElementById('save-btn').addEventListener('click', () => {
    if (!shouldIntercept()) { form.submit(); return; }
    const imp = computeImpact(simQ, simP);
    setText('modal-old-quota',    fmtBytes(ROLE_QUOTA_BYTES) ?? '∞');
    setText('modal-new-quota',    fmtBytes(simQ)             ?? '∞');
    setText('modal-old-projects', ROLE_MAX_PROJECTS          ?? '∞');
    setText('modal-new-projects', simP                       ?? '∞');
    setText('modal-impact-quota', imp.exc);
    setText('modal-impact-proj',  imp.projExc);
    if (_bsSave) _bsSave.show();
  });

  document.getElementById('confirm-save-btn').addEventListener('click', () => {
    dirty = false;
    saveModal.addEventListener('hidden.bs.modal', () => form.submit(), { once: true });
    if (_bsSave) _bsSave.hide();
  });

  // ── Modal: Cambios sin guardar ────────────────────────────────────────────
  function showLeaveModal(href) {
    pendingNavUrl = href;
    if (!_bsLeave) { console.error('[dirty-guard] Modal no disponible'); return; }
    setTimeout(() => _bsLeave.show(), 0);
  }

  function isInternalLink(a) {
    const href = a.getAttribute('href');
    if (!href || href === '#' || href.startsWith('javascript:') || href.startsWith('mailto:')) return false;
    if (a.dataset.bsToggle || a.dataset.bsDismiss || a.dataset.bsTarget) return false;
    return true;
  }

  // Capa 1: capture phase — intercepta antes de que el navegador navegue
  document.addEventListener('click', function (e) {
    if (!shouldIntercept()) return;
    const a = e.target.closest('a');
    if (!a || !isInternalLink(a)) return;
    e.preventDefault();
    showLeaveModal(a.getAttribute('href'));
  }, true);

  // Capa 2: listeners directos en sidebar y botón volver (backup)
  document.querySelectorAll('#sidebar a[href]').forEach(a => {
    if (!isInternalLink(a)) return;
    a.addEventListener('click', function (e) {
      if (!shouldIntercept()) return;
      e.preventDefault();
      showLeaveModal(a.getAttribute('href'));
    });
  });

  const btnBack = document.getElementById('btn-back');
  if (btnBack) {
    btnBack.addEventListener('click', function (e) {
      if (!shouldIntercept()) return;
      e.preventDefault();
      showLeaveModal(btnBack.getAttribute('href'));
    });
  }

  // "Guardar y salir"
  document.getElementById('leave-save-btn').addEventListener('click', () => {
    dirty = false;
    const dest = pendingNavUrl || ROLES_LIST_URL;
    leaveModal.addEventListener('hidden.bs.modal', () => {
      const fd = new FormData(form);
      fetch(form.action, { method: 'POST', body: fd })
        .then(() => { window.location.href = dest; })
        .catch(() => { window.location.href = dest; });
    }, { once: true });
    if (_bsLeave) _bsLeave.hide();
  });

  // "Salir sin guardar"
  document.getElementById('leave-discard-btn').addEventListener('click', () => {
    dirty = false;
    const dest = pendingNavUrl || ROLES_LIST_URL;
    leaveModal.addEventListener('hidden.bs.modal', () => { window.location.href = dest; }, { once: true });
    if (_bsLeave) _bsLeave.hide();
  });

  // ── Modal: Administrar usuarios del rol ───────────────────────────────────
  const manageModal  = document.getElementById('manageUsersModal');
  const confirmModal = document.getElementById('confirmRoleModal');
  const searchInput  = document.getElementById('manage-user-search');
  const resultsDiv   = document.getElementById('manage-user-results');

  const _bsManage  = _bsAvail && manageModal  ? new bootstrap.Modal(manageModal)  : null;
  const _bsConfirm = _bsAvail && confirmModal ? new bootstrap.Modal(confirmModal) : null;

  let searchTimer = null;

  if (searchInput) {
    searchInput.addEventListener('input', function () {
      clearTimeout(searchTimer);
      const q = this.value.trim();
      if (q.length < 2) {
        resultsDiv.innerHTML =
          '<div class="text-center text-muted small py-3">Escribe al menos 2 caracteres para buscar.</div>';
        return;
      }
      resultsDiv.innerHTML =
        '<div class="text-center text-muted small py-3"><i class="bi bi-hourglass-split me-1"></i>Buscando…</div>';
      searchTimer = setTimeout(() => fetchUsers(q), 300);
    });
  }

  function fetchUsers(q) {
    fetch(SEARCH_URL + '?q=' + encodeURIComponent(q))
      .then(r => r.json())
      .then(users => {
        if (!users.length) {
          resultsDiv.innerHTML =
            '<div class="text-center text-muted small py-3">No se encontraron usuarios.</div>';
          return;
        }
        resultsDiv.innerHTML = users.map(u => {
          const hasRole    = u.has_role;
          const btnCls     = hasRole ? 'btn-outline-danger'  : 'btn-outline-success';
          const btnIcon    = hasRole ? 'bi-person-dash'      : 'bi-person-plus';
          const btnText    = hasRole ? 'Quitar'              : 'Añadir';
          const badgeCls   = hasRole ? 'bg-success-subtle text-success' : 'bg-secondary-subtle text-secondary';
          return `<div class="list-group-item d-flex justify-content-between align-items-center py-2">
            <div class="flex-grow-1 min-width-0">
              <div class="fw-medium small">${esc(u.name)}</div>
              <div class="text-muted" style="font-size:.72rem;">${esc(u.email)}</div>
            </div>
            <div class="d-flex align-items-center gap-2 flex-shrink-0">
              <span class="badge ${badgeCls}" style="font-size:.68rem;">${esc(u.current_role)}</span>
              <button type="button" class="btn btn-sm ${btnCls} py-0 px-2"
                      data-uid="${u.id}" data-name="${esc(u.name)}"
                      data-email="${esc(u.email)}" data-role="${esc(u.current_role)}"
                      data-has-role="${hasRole}" style="font-size:.75rem;">
                <i class="bi ${btnIcon} me-1"></i>${btnText}
              </button>
            </div>
          </div>`;
        }).join('');

        resultsDiv.querySelectorAll('[data-uid]').forEach(btn => {
          btn.addEventListener('click', () => openConfirm(btn));
        });
      })
      .catch(() => {
        resultsDiv.innerHTML =
          '<div class="text-center text-danger small py-3">Error al buscar usuarios.</div>';
      });
  }

  function openConfirm(btn) {
    const uid     = btn.dataset.uid;
    const name    = btn.dataset.name;
    const email   = btn.dataset.email;
    const curRole = btn.dataset.role;
    const hasRole = btn.dataset.hasRole === 'true';
    const action  = hasRole ? 'remove' : 'assign';

    document.getElementById('confirm-user-name').textContent  = name;
    document.getElementById('confirm-user-email').textContent = email;
    document.getElementById('action-user-id').value = uid;
    document.getElementById('action-type').value    = action;

    const titleEl   = document.getElementById('confirm-title');
    const descEl    = document.getElementById('confirm-description');
    const detailEl  = document.getElementById('confirm-detail-text');
    const actionBtn = document.getElementById('confirm-action-btn');

    if (hasRole) {
      titleEl.innerHTML   = '<i class="bi bi-person-dash me-2 text-danger"></i>Confirmar retirada';
      descEl.innerHTML    = '¿Quitar el rol <strong>' + esc(ROLE_NAME) + '</strong> a:';
      detailEl.textContent = 'Se le asignará el rol por defecto de forma inmediata.';
      actionBtn.className  = 'btn btn-sm btn-danger';
      actionBtn.innerHTML  = '<i class="bi bi-person-dash me-1"></i>Quitar rol';
    } else {
      titleEl.innerHTML   = '<i class="bi bi-person-plus me-2 text-success"></i>Confirmar asignación';
      descEl.innerHTML    = '¿Asignar el rol <strong>' + esc(ROLE_NAME) + '</strong> a:';
      detailEl.textContent = 'Rol actual: ' + curRole + '. Se cambiará de forma inmediata.';
      actionBtn.className  = 'btn btn-sm btn-ol';
      actionBtn.innerHTML  = '<i class="bi bi-check2 me-1"></i>Confirmar';
    }

    if (_bsManage) _bsManage.hide();
    manageModal.addEventListener('hidden.bs.modal', () => {
      if (_bsConfirm) _bsConfirm.show();
    }, { once: true });
  }

  document.getElementById('confirm-action-back').addEventListener('click', () => {
    if (_bsConfirm) _bsConfirm.hide();
    confirmModal.addEventListener('hidden.bs.modal', () => {
      if (_bsManage) _bsManage.show();
    }, { once: true });
  });

  if (manageModal) {
    manageModal.addEventListener('shown.bs.modal', () => {
      searchInput.value = '';
      resultsDiv.innerHTML =
        '<div class="text-center text-muted small py-3">Escribe al menos 2 caracteres para buscar.</div>';
      searchInput.focus();
    });
  }

  // ── Listeners de inputs ───────────────────────────────────────────────────
  [inpQVal, inpQUnit, inpProj, inpDesc].forEach(el => {
    if (!el) return;
    el.addEventListener('input',  onInputChange);
    el.addEventListener('change', onInputChange);
  });

  // ── Render inicial ────────────────────────────────────────────────────────
  updateImpactPanel();
  renderTable();

})();
