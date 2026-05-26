/* notif-modal.js — modal "Preferencias de notificación" (compartido entre
 * /alertas/ y /mi-cuenta/).
 *
 * Espera que la página defina:
 *   - window.NOTIF_URL: endpoint GET/POST que devuelve {prefs: {...}}.
 *
 * Hook opcional:
 *   - window.NOTIF_ON_SAVE: callback al guardar OK (usado por /alertas/ para
 *     refrescar su tarjeta de resumen).
 *
 * Estructura de prefs (formato dos pestañas):
 *   {
 *     "digest_frequency": "disabled" | "12h" | "daily" | "3days" | "5days" |
 *                         "weekly" | "2weeks" | "monthly",
 *     "digest_hour":      0-23 | null,
 *     "immediate": { "notify_critical": true, ... },
 *     "digest":    { "notify_critical": false, ... }
 *   }
 */
(function () {
  "use strict";

  const NOTIF_URL = window.NOTIF_URL;
  if (!NOTIF_URL) return;

  const modalEl = document.getElementById("notifModal");
  if (!modalEl) return;

  const notifModal = new bootstrap.Modal(modalEl);

  document.querySelectorAll("[data-notif-open]").forEach((btn) => {
    btn.addEventListener("click", () => {
      notifModal.show();
      loadNotifPrefs();
    });
  });

  // Tipos disponibles. service_down se eliminó intencionadamente.
  const LEVEL_KEYS = [
    ["notify_critical",  "Nivel: Crítico"],
    ["notify_danger",    "Nivel: Peligro"],
    ["notify_warning",   "Nivel: Aviso"],
    ["notify_info",      "Nivel: Info"],
  ];
  const TYPE_KEYS = [
    ["notify_sync_failed",             "Fallo de sync"],
    ["notify_quota_exceeded",          "Cuota excedida"],
    ["notify_quota_warning",           "Cuota cercana"],
    ["notify_project_limit_exceeded",  "Límite proyectos superado"],
    ["notify_project_limit_warning",   "Proyectos cercano al límite"],
    ["notify_repeated_errors",         "Errores repetidos"],
    ["notify_administrative_warning",  "Aviso administrativo"],
  ];
  const ALL_KEYS = [...LEVEL_KEYS, ...TYPE_KEYS];

  function loadNotifPrefs() {
    document.getElementById("notif-body").innerHTML =
      '<div class="text-center py-4 text-muted">' +
      '<span class="spinner-border spinner-border-sm me-2"></span>Cargando…</div>';
    fetch(NOTIF_URL, { headers: { Accept: "application/json" } })
      .then((r) => r.json())
      .then((data) => renderNotifPrefs(data.prefs || {}))
      .catch(() => {
        document.getElementById("notif-body").innerHTML =
          '<p class="text-danger small">Error al cargar preferencias.</p>';
      });
  }

  const FREQ_OPTIONS = [
    ["disabled", "Desactivado"],
    ["12h",      "Cada 12 horas"],
    ["daily",    "Cada día"],
    ["3days",    "Cada 3 días"],
    ["5days",    "Cada 5 días"],
    ["weekly",   "Cada semana"],
    ["2weeks",   "Cada 2 semanas"],
    ["monthly",  "Cada mes"],
  ];

  function renderNotifPrefs(prefs) {
    // Normaliza formato nuevo ({immediate, digest}) y antiguo ({modes})
    let immediate = {};
    let digest    = {};
    const digestFreq = prefs.digest_frequency || "disabled";
    const digestHour = prefs.digest_hour != null ? prefs.digest_hour : 8;

    if (prefs.immediate && typeof prefs.immediate === "object") {
      immediate = prefs.immediate;
      digest    = prefs.digest || {};
    } else if (prefs.modes && typeof prefs.modes === "object") {
      // Formato anterior 3-estado → mapear
      ALL_KEYS.forEach(([k]) => {
        const mode = prefs.modes[k] || "off";
        immediate[k] = mode === "immediate";
        digest[k]    = mode === "digest";
      });
    } else {
      // Formato más antiguo — booleans planos
      ALL_KEYS.forEach(([k]) => {
        immediate[k] = !!prefs[k];
        digest[k]    = false;
      });
    }

    function switchRow(prefix, key, label, checked) {
      return `
        <div class="form-check form-switch mb-2">
          <input class="form-check-input" type="checkbox" role="switch"
                 id="modal-${prefix}-${key}" ${checked ? "checked" : ""}>
          <label class="form-check-label small" for="modal-${prefix}-${key}">${label}</label>
        </div>`;
    }

    function colsHtml(prefix, values) {
      return `
        <div class="row g-3">
          <div class="col-md-6">
            <p class="fw-semibold small text-muted mb-2">
              <i class="bi bi-layers me-1"></i>Por nivel de gravedad
            </p>
            ${LEVEL_KEYS.map(([k, l]) => switchRow(prefix, k, l, values[k])).join("")}
          </div>
          <div class="col-md-6">
            <p class="fw-semibold small text-muted mb-2">
              <i class="bi bi-tag me-1"></i>Por tipo de alerta
            </p>
            ${TYPE_KEYS.map(([k, l]) => switchRow(prefix, k, l, values[k])).join("")}
          </div>
        </div>`;
    }

    // Construir opciones de frecuencia
    const freqOptions = FREQ_OPTIONS.map(([val, lbl]) =>
      `<option value="${val}" ${digestFreq === val ? "selected" : ""}>${lbl}</option>`
    ).join("");

    // Construir opciones de hora (00:00 – 23:00)
    const hourOptions = Array.from({length: 24}, (_, h) => {
      const hh = String(h).padStart(2, "0");
      return `<option value="${h}" ${digestHour === h ? "selected" : ""}>${hh}:00</option>`;
    }).join("");

    document.getElementById("notif-body").innerHTML = `
      <ul class="nav nav-tabs nav-tabs-sm mb-3" id="notifModalTabs" role="tablist">
        <li class="nav-item" role="presentation">
          <button class="nav-link active fw-semibold" id="modal-imm-tab"
                  data-bs-toggle="tab" data-bs-target="#modal-imm-pane"
                  type="button" role="tab">
            <i class="bi bi-lightning-charge me-1 text-success"></i>Inmediato
          </button>
        </li>
        <li class="nav-item" role="presentation">
          <button class="nav-link fw-semibold" id="modal-dig-tab"
                  data-bs-toggle="tab" data-bs-target="#modal-dig-pane"
                  type="button" role="tab">
            <i class="bi bi-calendar-event me-1 text-primary"></i>Periódico
          </button>
        </li>
      </ul>

      <div class="tab-content" id="notifModalTabContent">

        <div class="tab-pane fade show active" id="modal-imm-pane" role="tabpanel">
          <p class="text-muted small mb-3">
            Recibirás un correo al instante cuando se genere una alerta
            de los tipos marcados.
          </p>
          ${colsHtml("imm", immediate)}
        </div>

        <div class="tab-pane fade" id="modal-dig-pane" role="tabpanel" style="margin-top:1rem;">
          <p class="text-muted small mb-3">
            Los tipos marcados se incluirán en el correo resumen periódico. Solo se envía si hay alertas pendientes.
          </p>
          <div class="d-flex flex-wrap gap-3 align-items-end mb-3 pb-3 border-bottom">
            <div>
              <label class="fw-semibold small mb-1" for="modal-digest-frequency">
                <i class="bi bi-calendar-event me-1"></i>Frecuencia del resumen
              </label>
              <select class="form-select form-select-sm mt-1" id="modal-digest-frequency"
                      style="min-width:200px;">
                ${freqOptions}
              </select>
            </div>
            <div id="modal-digest-hour-group" ${digestFreq === "disabled" ? 'style="display:none"' : ""}>
              <label class="fw-semibold small mb-1" for="modal-digest-hour">
                <i class="bi bi-alarm me-1"></i>Hora de envío
              </label>
              <select class="form-select form-select-sm mt-1" id="modal-digest-hour"
                      style="min-width:110px;">
                ${hourOptions}
              </select>
            </div>
          </div>
          ${colsHtml("dig", digest)}
        </div>

      </div>`;

    // Mostrar/ocultar selector de hora según frecuencia
    const freqSel = document.getElementById("modal-digest-frequency");
    const hourGrp = document.getElementById("modal-digest-hour-group");
    if (freqSel && hourGrp) {
      freqSel.addEventListener("change", function () {
        hourGrp.style.display = this.value === "disabled" ? "none" : "";
      });
    }
  }

  document.getElementById("notif-save-btn").addEventListener("click", () => {
    // Recoge los checkboxes de las dos pestañas
    const immediate = {};
    const digest    = {};
    ALL_KEYS.forEach(([k]) => {
      immediate[k] = !!(document.getElementById(`modal-imm-${k}`)?.checked);
      digest[k]    = !!(document.getElementById(`modal-dig-${k}`)?.checked);
    });
    const digestEl   = document.getElementById("modal-digest-frequency");
    const digestHrEl = document.getElementById("modal-digest-hour");
    const rawHour    = digestHrEl ? digestHrEl.value : null;
    const body = {
      immediate,
      digest,
      digest_frequency: digestEl ? digestEl.value : "disabled",
      digest_hour:      rawHour != null ? parseInt(rawHour, 10) : null,
    };

    const btn = document.getElementById("notif-save-btn");
    const msg = document.getElementById("notif-save-msg");
    btn.disabled  = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Guardando…';
    fetch(NOTIF_URL, {
      method:  "POST",
      headers: { "Content-Type": "application/json", Accept: "application/json" },
      body:    JSON.stringify(body),
    })
      .then((r) => r.json())
      .then((data) => {
        msg.className   = "small me-auto " + (data.ok ? "text-success" : "text-danger");
        msg.textContent = data.msg || (data.ok ? "Guardado." : "Error.");
        msg.classList.remove("d-none");
        setTimeout(() => msg.classList.add("d-none"), 3000);
        if (data.ok && typeof window.NOTIF_ON_SAVE === "function") {
          try { window.NOTIF_ON_SAVE(); } catch (e) { /* ignore */ }
        }
      })
      .catch(() => {
        msg.className   = "small me-auto text-danger";
        msg.textContent = "Error de red.";
        msg.classList.remove("d-none");
      })
      .finally(() => {
        btn.disabled  = false;
        btn.innerHTML = '<i class="bi bi-floppy me-1"></i>Guardar preferencias';
      });
  });
})();
