/* admins.js — interacciones de la pantalla /administradores/.
 *
 * 1. Búsqueda en cliente (filtra filas por usuario o email).
 * 2. Modal de crear admin: hint de coincidencia de contraseñas.
 * 3. Modal de reset password: rellena el username y la action del form, hint.
 * 4. Modal de activar/desactivar: rellena título, mensaje y action según el caso.
 */
(function () {
  "use strict";

  // ── Filtro en cliente (cards) ───────────────────────────────────────────
  const search = document.getElementById("admin-search");
  const cards  = document.querySelectorAll("#admins-list [data-search]");
  const empty  = document.getElementById("empty-search-state");

  if (search) {
    search.addEventListener("input", () => {
      const q = search.value.trim().toLowerCase();
      let visible = 0;
      cards.forEach((card) => {
        const hay = card.getAttribute("data-search") || "";
        const match = !q || hay.indexOf(q) !== -1;
        card.style.display = match ? "" : "none";
        if (match) visible++;
      });
      if (empty) empty.classList.toggle("d-none", visible > 0 || !q);
    });
  }

  // ── Inicialización de tooltips Bootstrap ────────────────────────────────
  document.querySelectorAll('[data-bs-toggle="tooltip"]').forEach((el) => {
    new bootstrap.Tooltip(el);
  });

  // ── Helper: hint de coincidencia entre dos campos password ──────────────
  function bindPasswordMatch(newId, confirmId, hintId) {
    const a = document.getElementById(newId);
    const b = document.getElementById(confirmId);
    const h = document.getElementById(hintId);
    if (!a || !b || !h) return;
    function check() {
      const va = a.value, vb = b.value;
      if (!va && !vb) { h.textContent = "";                            h.className = "form-text small";    return; }
      if (!vb)        { h.textContent = "Repite la contraseña.";       h.className = "form-text small";    return; }
      if (va === vb)  { h.textContent = "Las contraseñas coinciden.";  h.className = "form-text small ok"; return; }
      h.textContent = "Las contraseñas no coinciden.";
      h.className   = "form-text small bad";
    }
    a.addEventListener("input", check);
    b.addEventListener("input", check);
  }
  bindPasswordMatch("ca-password", "ca-confirm", "ca-match-hint");
  bindPasswordMatch("rp-new",      "rp-confirm", "rp-match-hint");

  // ── Bloquea submit si la confirmación no coincide ─────────────────────
  const resetForm = document.getElementById("reset-pw-form");
  if (resetForm) {
    resetForm.addEventListener("submit", (event) => {
      const a = document.getElementById("rp-new");
      const b = document.getElementById("rp-confirm");
      const h = document.getElementById("rp-match-hint");
      if (!a || !b || !h) return;
      if (a.value && b.value && a.value !== b.value) {
        event.preventDefault();
        h.textContent = "Las contraseñas no coinciden.";
        h.className = "form-text small bad";
      }
    });
  }

  // ── Modal: reset password (rellena action + username dinámicamente) ─────
  const resetModal = document.getElementById("resetPwModal");
  if (resetModal) {
    resetModal.addEventListener("show.bs.modal", (event) => {
      const trigger = event.relatedTarget;
      const id      = trigger.getAttribute("data-admin-id");
      const uname   = trigger.getAttribute("data-admin-username");
      const url     = window.ADMINS_URLS.reset.replace("/0/", "/" + id + "/");
      document.getElementById("reset-pw-form").action = url;
      document.getElementById("rp-username").textContent = uname;
      // Limpia campos al abrir
      document.getElementById("rp-new").value     = "";
      document.getElementById("rp-confirm").value = "";
      const hint = document.getElementById("rp-match-hint");
      if (hint) { hint.textContent = ""; hint.className = "form-text small"; }
    });
  }

  // ── Modal: activar/desactivar (rellena título, mensaje y action) ────────
  const toggleModal = document.getElementById("toggleStateModal");
  if (toggleModal) {
    toggleModal.addEventListener("show.bs.modal", (event) => {
      const trigger = event.relatedTarget;
      const id      = trigger.getAttribute("data-admin-id");
      const uname   = trigger.getAttribute("data-admin-username");
      const state   = trigger.getAttribute("data-target-state"); // "on" | "off"

      const isOn   = state === "on";
      const urlTpl = isOn ? window.ADMINS_URLS.activate : window.ADMINS_URLS.deactivate;
      const action = urlTpl.replace("/0/", "/" + id + "/");
      document.getElementById("toggle-state-form").action = action;

      const titleEl = document.getElementById("ts-title");
      const msgEl   = document.getElementById("ts-message");
      const iconEl  = document.getElementById("ts-icon");
      const btn     = document.getElementById("ts-confirm-btn");

      if (isOn) {
        titleEl.textContent = "Activar administrador";
        msgEl.innerHTML     = 'Vas a <strong>activar</strong> a <strong>' + uname + '</strong>. Podrá iniciar sesión inmediatamente.';
        iconEl.className    = "bi bi-play-circle me-2 text-success";
        btn.className       = "btn btn-sm btn-success";
        btn.innerHTML       = '<i class="bi bi-check2-circle me-1"></i>Sí, activar';
      } else {
        titleEl.textContent = "Desactivar administrador";
        msgEl.innerHTML     = 'Vas a <strong>desactivar</strong> a <strong>' + uname + '</strong>. No podrá iniciar sesión hasta que vuelva a activarse.';
        iconEl.className    = "bi bi-pause-circle me-2 text-warning";
        btn.className       = "btn btn-sm btn-warning";
        btn.innerHTML       = '<i class="bi bi-pause-circle me-1"></i>Sí, desactivar';
      }
    });
  }
})();
