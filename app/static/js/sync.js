/* sync.js — interacciones de /sincronizacion/
 *
 * - Filtros del historial: AJAX a /sincronizacion/buscar
 * - Confirmación al lanzar acciones marcadas con data-confirm
 * - Polling del estado actual cada 5s (cuando hay una sync en curso o cada 30s)
 * - Modal de detalle: AJAX a /sincronizacion/<id>
 */
(function () {
  "use strict";

  const URLS = window.SYNC_URLS || {};

  // ── Modal de confirmación para TODAS las acciones de sync ──────────────
  const confirmModalEl = document.getElementById("confirmSyncModal");
  const confirmModal   = (confirmModalEl && window.bootstrap)
                          ? new bootstrap.Modal(confirmModalEl) : null;
  let _pendingForm = null;

  document.querySelectorAll("form.sync-action-form").forEach((f) => {
    const btn = f.querySelector("button");
    if (!btn) return;
    btn.addEventListener("click", (ev) => {
      ev.preventDefault();
      _pendingForm = f;
      if (confirmModal) {
        document.getElementById("cs-title").innerHTML =
          `<i class="bi bi-question-circle me-2 text-warning-emphasis"></i>` +
          (f.getAttribute("data-confirm-title") || "Confirmar sincronización");
        document.getElementById("cs-message").textContent =
          f.getAttribute("data-confirm-msg") || "¿Quieres lanzar la sincronización?";
        confirmModal.show();
      } else {
        f.submit();
      }
    });
  });

  const confirmBtn = document.getElementById("cs-confirm-btn");
  if (confirmBtn) {
    confirmBtn.addEventListener("click", () => {
      if (!_pendingForm) return;

      // Marca el botón clicado con spinner y deshabilita los demás.
      const clickedBtn = _pendingForm.querySelector(".sync-action-btn");
      document.querySelectorAll(".sync-action-btn").forEach((b) => {
        b.disabled = true;
        if (b !== clickedBtn) {
          b.classList.add("opacity-50");
        }
      });
      if (clickedBtn) {
        clickedBtn.classList.add("sync-loading");
        const icon = clickedBtn.querySelector(".sync-action-icon");
        if (icon) {
          // Conserva la clase del icono original para restaurarla si hace falta
          icon.dataset.origClass = icon.className;
          icon.className = "spinner-border spinner-border-sm sync-action-icon";
        }
      }

      confirmBtn.disabled = true;
      confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Iniciando…';
      _pendingForm.submit();
    });
  }

  // ── Confirmación simple (window.confirm) para borrar programaciones ─────
  document.querySelectorAll("form[data-confirm]").forEach((f) => {
    // Evita doble vinculación con el modal: estos forms NO son sync-action-form
    if (f.classList.contains("sync-action-form")) return;
    const msg = f.getAttribute("data-confirm");
    f.addEventListener("submit", (ev) => {
      if (!window.confirm(msg)) ev.preventDefault();
    });
  });

  // ── Filtros del historial ─────────────────────────────────────────────
  const form = document.getElementById("hist-filters");
  const tbody = document.getElementById("hist-tbody");
  const pag = document.getElementById("hist-pagination");
  const total = document.getElementById("hist-total");
  let currentPage = 1;

  if (form && tbody) {
    form.addEventListener("submit", (e) => { e.preventDefault(); currentPage = 1; reloadHistory(); });
    document.getElementById("btn-clear-filters").addEventListener("click", () => {
      form.reset();
      currentPage = 1;
      reloadHistory();
    });
  }

  function reloadHistory() {
    if (!form) return;
    const fd = new URLSearchParams(new FormData(form));
    fd.set("page", currentPage);
    fd.set("per_page", 15);
    fetch(`${URLS.search}?${fd.toString()}`, { headers: { Accept: "application/json" } })
      .then((r) => r.json())
      .then((data) => renderHistory(data))
      .catch(() => {
        tbody.innerHTML = `<tr><td colspan="10" class="text-center text-danger py-3">Error al cargar el historial.</td></tr>`;
      });
  }

  function statusBadge(s) {
    if (s === "success") return '<span class="badge bg-success"><i class="bi bi-check-circle me-1"></i>Éxito</span>';
    if (s === "error")   return '<span class="badge bg-danger"><i class="bi bi-x-circle me-1"></i>Error</span>';
    if (s === "running") return '<span class="badge bg-info"><i class="bi bi-arrow-repeat me-1"></i>En curso</span>';
    if (s === "partial") return '<span class="badge bg-warning text-dark"><i class="bi bi-exclamation-circle me-1"></i>Parcial</span>';
    return `<span class="badge bg-secondary">${esc(s)}</span>`;
  }

  function deltaSpan(d) {
    if (d === null || d === undefined) return "";
    const cls = d > 0 ? "text-success" : (d < 0 ? "text-danger" : "");
    const sign = d > 0 ? "+" : "";
    return `<span class="text-muted ms-1" style="font-size:.7rem;"><span class="${cls}">${sign}${d}</span></span>`;
  }

  function renderHistory(data) {
    if (total) total.textContent = `${data.total} registros`;
    if (!data.items || !data.items.length) {
      tbody.innerHTML = `<tr><td colspan="10" class="text-center text-muted py-4"><i class="bi bi-search d-block fs-3 mb-1 opacity-50"></i>Sin resultados con esos filtros.</td></tr>`;
      pag.innerHTML = "";
      return;
    }
    let html = "";
    data.items.forEach((r) => {
      const triggered = r.triggered_by === "manual"
        ? `<i class="bi bi-hand-index me-1"></i>${esc(r.triggered_by_user || "manual")}`
        : '<i class="bi bi-clock me-1"></i>Programada';
      const dur = r.duration_seconds != null ? `${r.duration_seconds.toFixed(1)}s` : "—";
      const errCell = r.errors_count > 0
        ? `<span class="text-danger fw-medium">${r.errors_count}</span>`
        : `<span class="text-muted">0</span>`;
      html += `<tr data-id="${r.id}">
        <td class="ps-3 text-muted small">#${r.id}</td>
        <td class="small text-nowrap">${esc(r.started_at || "—")}</td>
        <td><span class="badge bg-light text-dark border" style="font-size:.7rem;">${esc(r.sync_type_label)}</span></td>
        <td>${statusBadge(r.status)}</td>
        <td class="small text-muted">${triggered}</td>
        <td class="small"><span class="fw-medium">${r.users_synced || 0}</span> <span class="text-muted">/ ${r.users_found || 0}</span>${deltaSpan(r.users_delta)}</td>
        <td class="small"><span class="fw-medium">${r.projects_synced || 0}</span> <span class="text-muted">/ ${r.projects_found || 0}</span>${deltaSpan(r.projects_delta)}</td>
        <td class="small text-muted">${dur}</td>
        <td class="small">${errCell}</td>
        <td class="text-end pe-3"><button type="button" class="btn btn-sm btn-outline-secondary py-0 px-2 btn-detail" data-id="${r.id}" title="Ver detalle"><i class="bi bi-search"></i></button></td>
      </tr>`;
    });
    tbody.innerHTML = html;
    bindDetailButtons();

    // Paginación — mismo HTML que el partial server-side
    // (templates/sync/_pagination.html) para que el handler delegado en
    // #hist-pagination funcione idénticamente.
    if (data.pages > 1) {
      let p = '<nav><ul class="pagination pagination-sm mb-0">';
      p += `<li class="page-item ${!data.has_prev ? "disabled" : ""}"><a class="page-link" href="#" data-page="${data.prev_num}"><i class="bi bi-chevron-left"></i></a></li>`;
      for (let i = 1; i <= data.pages; i++) {
        p += `<li class="page-item ${i === data.page ? "active" : ""}"><a class="page-link" href="#" data-page="${i}">${i}</a></li>`;
      }
      p += `<li class="page-item ${!data.has_next ? "disabled" : ""}"><a class="page-link" href="#" data-page="${data.next_num}"><i class="bi bi-chevron-right"></i></a></li>`;
      p += "</ul></nav>";
      pag.innerHTML = p;
    } else {
      pag.innerHTML = "";
    }
  }

  // Event delegation: un único listener en el contenedor cubre tanto la
  // paginación renderizada por Jinja en la carga inicial como la que
  // renderiza el JS tras un filtro/fetch.
  if (pag) {
    pag.addEventListener("click", (ev) => {
      const a = ev.target.closest("a[data-page]");
      if (!a) return;
      ev.preventDefault();
      const li = a.closest(".page-item");
      if (li && li.classList.contains("disabled")) return;
      const np = parseInt(a.getAttribute("data-page"), 10);
      if (np && np !== currentPage) {
        currentPage = np;
        reloadHistory();
      }
    });
  }

  // ── Polling del estado ─────────────────────────────────────────────────
  // - `wasRunning` arranca leyendo el estado inicial renderizado por el
  //   servidor (`#running-badge` existe si hay sync en curso al cargar).
  // - Cuando vemos la transición running → done (bien o mal) hacemos
  //   `window.location.reload()` para refrescar TODO: chips, historial,
  //   contadores y deshabilitado de botones.
  let wasRunning = document.getElementById("running-badge") !== null;

  function refreshState() {
    fetch(URLS.state, { headers: { Accept: "application/json" } })
      .then((r) => r.json())
      .then((s) => {
        // Errores 24h
        const errEl = document.getElementById("errors-24h");
        if (errEl) {
          errEl.textContent = s.totals_24h.error;
          errEl.classList.toggle("text-danger", s.totals_24h.error > 0);
        }

        // Transición de estado:
        //   - idle → running: recarga rápida para mostrar botones deshabilitados
        //   - running → idle: recarga completa (la sync acabó: bien o mal)
        const nowRunning = !!s.running;
        if (wasRunning && !nowRunning) {
          // Sync terminada — recargar para ver el resultado en el historial
          // y reactivar los botones de acción.
          window.location.reload();
          return;
        }
        if (!wasRunning && nowRunning) {
          // Empezó una sync mientras estábamos viendo la página.
          window.location.reload();
          return;
        }
        wasRunning = nowRunning;
      })
      .catch(() => {/* silent */});
  }
  refreshState();
  setInterval(() => refreshState(), 5000);

  // ── Modal de detalle ──────────────────────────────────────────────────
  const modalEl = document.getElementById("syncDetailModal");
  const modal = (modalEl && window.bootstrap) ? new bootstrap.Modal(modalEl) : null;

  function bindDetailButtons() {
    document.querySelectorAll(".btn-detail").forEach((b) => {
      b.addEventListener("click", () => openDetail(parseInt(b.getAttribute("data-id"), 10)));
    });
  }
  bindDetailButtons();

  function openDetail(id) {
    if (!modal) return;
    // Reset cabecera y body a estado "loading"
    const header = document.getElementById("sd-header");
    if (header) header.className = "detail-header-strip sd-strip-loading";
    document.getElementById("sd-header-content").innerHTML =
      `<div class="text-muted small">Cargando detalle #${id}…</div>`;
    document.getElementById("sd-body").innerHTML =
      '<div class="text-center text-muted py-4"><span class="spinner-border spinner-border-sm me-2"></span>Cargando…</div>';
    modal.show();
    const url = URLS.detail.replace("/0", "/" + id);
    fetch(url, { headers: { Accept: "application/json" } })
      .then((r) => r.ok ? r.json() : Promise.reject(new Error("HTTP " + r.status)))
      .then((data) => renderDetail(data))
      .catch((err) => {
        document.getElementById("sd-body").innerHTML =
          `<div class="alert alert-danger small mb-0">Error al cargar el detalle: ${esc(err.message)}</div>`;
      });
  }

  // Mapa de iconos por estado para badges grandes en la cabecera del modal
  const STATUS_META = {
    success: { cls: "bg-success",         icon: "bi-check-circle-fill",    label: "Éxito"    },
    error:   { cls: "bg-danger",          icon: "bi-x-octagon-fill",       label: "Error"    },
    partial: { cls: "bg-warning text-dark", icon: "bi-exclamation-triangle-fill", label: "Parcial" },
    running: { cls: "bg-info text-white", icon: "bi-arrow-repeat",         label: "En curso" },
  };

  function bigStatusBadge(status) {
    const m = STATUS_META[status] || { cls: "bg-secondary", icon: "bi-question-circle", label: status };
    return `<span class="badge ${m.cls}" style="font-size:.75rem;">
      <i class="bi ${m.icon} me-1"></i>${esc(m.label)}</span>`;
  }

  function renderDetail(data) {
    const r = data.run || {};

    // ── Cabecera con strip de color según estado ────────────────────────
    const header = document.getElementById("sd-header");
    if (header) {
      header.className = `detail-header-strip sd-strip-${r.status || "loading"}`;
    }
    const triggeredHtml = r.triggered_by === "manual"
      ? `<span class="badge bg-light text-dark border" style="font-size:.7rem;"><i class="bi bi-hand-index me-1"></i>${esc(r.triggered_by_user || "manual")}</span>`
      : `<span class="badge bg-light text-dark border" style="font-size:.7rem;"><i class="bi bi-clock me-1"></i>Programada</span>`;
    document.getElementById("sd-header-content").innerHTML = `
      <div class="d-flex align-items-center gap-2 flex-wrap mb-2">
        ${bigStatusBadge(r.status)}
        <span class="badge bg-secondary-subtle text-secondary border" style="font-size:.7rem;">
          ${esc(r.sync_type_label || "—")}
        </span>
        ${triggeredHtml}
      </div>
      <h5 class="fw-bold mb-1" style="line-height:1.3;">Sincronización #${r.id}</h5>
      <p class="text-muted mb-0" style="font-size:.78rem;">
        ${esc(r.started_at || "—")}
        ${r.duration_seconds != null ? ` &middot; ${r.duration_seconds.toFixed(1)}s` : ""}
      </p>`;

    // ── Body: ficha tipo "alert detail" ────────────────────────────────
    // ── Property grid compacto (4 campos) ──────────────────────────────
    let bodyHtml = `
      <div class="row g-2 mb-2">
        <div class="col-6 col-md-3">
          <div class="detail-field-label">Tipo</div>
          <div class="detail-field-value">${esc(r.sync_type_label || "—")}</div>
        </div>
        <div class="col-6 col-md-3">
          <div class="detail-field-label">Iniciada por</div>
          <div class="detail-field-value">${triggeredHtml}</div>
        </div>
        <div class="col-6 col-md-3">
          <div class="detail-field-label">Inicio</div>
          <div class="detail-field-value">${esc(r.started_at || "—")}</div>
        </div>
        <div class="col-6 col-md-3">
          <div class="detail-field-label">Fin</div>
          <div class="detail-field-value">${esc(r.finished_at || "en curso…")}</div>
        </div>
      </div>`;

    // ── Contadores compactos en una sola línea de chips ────────────────
    //   Ej.: 👥 0/0 (+0 nuevos, 0 actualizados) · 📁 0/0 (+0 nuevos, 0
    //   actualizados) · 👥 0 miembros sync.
    const usersChip = `
      <span class="sd-metric">
        <i class="bi bi-people"></i>
        <strong>${r.users_synced || 0}</strong>/<span class="text-muted">${r.users_found || 0}</span>
        <small class="text-muted ms-1">+${r.users_created || 0} nuevos · ${r.users_updated || 0} actualizados</small>
        ${deltaInline(r.users_delta)}
      </span>`;
    const projsChip = `
      <span class="sd-metric">
        <i class="bi bi-folder"></i>
        <strong>${r.projects_synced || 0}</strong>/<span class="text-muted">${r.projects_found || 0}</span>
        <small class="text-muted ms-1">+${r.projects_created || 0} nuevos · ${r.projects_updated || 0} actualizados</small>
        ${deltaInline(r.projects_delta)}
      </span>`;
    const membersChip = `
      <span class="sd-metric">
        <i class="bi bi-people-fill"></i>
        <strong>${r.members_synced || 0}</strong>
        <small class="text-muted ms-1">miembros sync.</small>
      </span>`;
    bodyHtml += `
      <div class="sd-metrics-row mb-2">
        ${usersChip}${projsChip}${membersChip}
      </div>`;

    // ── Mensaje (puede ser largo) ──────────────────────────────────────
    if (r.message) {
      bodyHtml += `
        <div class="mb-2">
          <div class="detail-field-label mb-1">Mensaje</div>
          <div class="detail-msg-box sd-msg">${esc(r.message)}</div>
        </div>`;
    }

    // ── Error técnico (sólo si existe). Su propio scroll interno. ─────
    if (r.error_detail) {
      bodyHtml += `
        <div class="mb-2">
          <div class="detail-field-label mb-1 text-danger">Error técnico</div>
          <div class="sd-error-box">${esc(r.error_detail)}</div>
        </div>`;
    }

    // ── Proyectos procesados — tabla con su propio scroll interno ─────
    if (data.project_logs && data.project_logs.length) {
      const projRows = data.project_logs.map((l) => {
        const evBadge = l.event === "created"
          ? '<span class="badge bg-success-subtle text-success border border-success-subtle" style="font-size:.62rem;">creado</span>'
          : '<span class="badge bg-info-subtle text-info-emphasis border border-info-subtle" style="font-size:.62rem;">actualizado</span>';
        const size = l.size_bytes != null ? humanBytes(l.size_bytes) : "—";
        return `<tr>
          <td class="py-1 px-2">${esc(l.project_name || "#" + l.project_id)}</td>
          <td class="py-1 px-2">${evBadge}</td>
          <td class="py-1 px-2 text-muted">${size}</td>
          <td class="py-1 px-2 text-muted">${l.member_count || 0}</td>
          <td class="py-1 px-2 text-end text-muted">${esc(l.synced_at || "—")}</td>
        </tr>`;
      }).join("");
      bodyHtml += `
        <div class="mb-1">
          <div class="detail-field-label mb-1">Proyectos procesados (${data.project_logs.length})</div>
          <div class="sd-list-scroll">
            <table class="table table-sm mb-0">
              <thead class="table-light sticky-top"><tr>
                <th class="py-1 px-2">Proyecto</th>
                <th class="py-1 px-2">Evento</th>
                <th class="py-1 px-2">Tamaño</th>
                <th class="py-1 px-2">Miembros</th>
                <th class="py-1 px-2 text-end">Fecha</th>
              </tr></thead>
              <tbody>${projRows}</tbody>
            </table>
          </div>
        </div>`;
    }

    document.getElementById("sd-body").innerHTML = bodyHtml;
  }

  // Versión inline del delta para los chips de métricas
  function deltaInline(d) {
    if (d == null || d === 0) return "";
    const cls = d > 0 ? "text-success" : "text-danger";
    const sign = d > 0 ? "+" : "";
    return ` <span class="${cls}" style="font-size:.7rem;">(${sign}${d})</span>`;
  }

  function deltaText(d) {
    if (d == null) return '<span class="text-muted">—</span>';
    if (d > 0) return `<span class="text-success">+${d}</span>`;
    if (d < 0) return `<span class="text-danger">${d}</span>`;
    return "0";
  }

  function humanBytes(n) {
    if (n === 0) return "0 B";
    const u = ["B","KB","MB","GB","TB"];
    let i = 0; let v = n;
    while (Math.abs(v) >= 1024 && i < u.length - 1) { v /= 1024; i++; }
    return `${v.toFixed(1)} ${u[i]}`;
  }

  function esc(s) {
    if (s == null) return "";
    return String(s)
      .replaceAll("&", "&amp;").replaceAll("<", "&lt;").replaceAll(">", "&gt;")
      .replaceAll('"', "&quot;").replaceAll("'", "&#39;");
  }
})();
