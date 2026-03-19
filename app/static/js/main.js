/**
 * Overleaf Admin Platform — main JS
 */

document.addEventListener("DOMContentLoaded", function () {
  // Sidebar toggle
  const toggleBtn = document.getElementById("sidebarToggle");
  const sidebar = document.getElementById("sidebar");

  if (toggleBtn && sidebar) {
    toggleBtn.addEventListener("click", function () {
      sidebar.classList.toggle("collapsed");
    });
  }

  // Auto-dismiss alerts after 5 seconds
  const alerts = document.querySelectorAll(".alert.alert-dismissible");
  alerts.forEach(function (alert) {
    setTimeout(function () {
      const bsAlert = bootstrap.Alert.getOrCreateInstance(alert);
      bsAlert.close();
    }, 5000);
  });

  // Inject current year into footer if needed
  const yearSpans = document.querySelectorAll(".current-year");
  yearSpans.forEach(function (el) {
    el.textContent = new Date().getFullYear();
  });
});
