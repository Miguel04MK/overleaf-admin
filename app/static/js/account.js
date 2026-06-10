/* account.js — interacciones de la pantalla "Mi cuenta".
 *
 * 1. Hint en vivo de coincidencia de contraseñas.
 * 2. Modal de confirmación antes de enviar el cambio de contraseña.
 */
(function () {
  "use strict";

  // ── Coincidencia de contraseñas ─────────────────────────────────────────
  const np   = document.getElementById("new_password");
  const cp   = document.getElementById("confirm_password");
  const hint = document.getElementById("pw-match-hint");

  function checkMatch() {
    if (!np || !cp || !hint) return;
    const a = np.value, b = cp.value;
    if (!a && !b) {
      hint.innerHTML = "Mínimo 8 caracteres y distinta de la actual.<br>Las contraseñas deben coincidir.";
      hint.className = "form-text small";
      return;
    }
    if (!b)       { hint.textContent = "Repite la nueva contraseña.";      hint.className = "form-text small"; return; }
    if (a === b)  { hint.textContent = "Las contraseñas coinciden.";  hint.className = "form-text small ok";  return; }
    hint.textContent = "Las contraseñas no coinciden.";
    hint.className   = "form-text small bad";
  }

  if (np && cp) {
    np.addEventListener("input", checkMatch);
    cp.addEventListener("input", checkMatch);
  }

  // ── Modal de confirmación de contraseña ─────────────────────────────────
  const form       = document.getElementById("pw-form");
  const updateBtn  = document.getElementById("pw-update-btn");
  const confirmBtn = document.getElementById("pw-confirm-btn");
  const modalEl    = document.getElementById("confirmPwModal");

  if (form && updateBtn && confirmBtn && modalEl) {
    const confirmModal = new bootstrap.Modal(modalEl);

    updateBtn.addEventListener("click", () => {
      if (!form.checkValidity()) {
        form.reportValidity();
        return;
      }
      confirmModal.show();
    });

    confirmBtn.addEventListener("click", () => {
      confirmBtn.disabled  = true;
      confirmBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span>Cambiando…';
      form.submit();
    });
  }
})();
