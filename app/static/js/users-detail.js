/**
 * Overleaf Admin Platform — User detail page (Chart.js)
 *
 * Espera que el template defina antes de cargar este archivo:
 *   CHART_STORAGE  — { labels, values }
 *   CHART_PROJECTS — { labels, values }
 *   CHART_COLLABS  — { labels, values }
 *
 * Globales de utils.js disponibles: esc()
 */

/* ── toggleQuotaForm / switchTab — usados desde onclick en HTML estático ─── */
window.toggleQuotaForm = function () {
  const form = document.getElementById('quotaForm');
  const btn  = document.getElementById('quotaToggleBtn');
  if (form.style.display === 'none' || form.style.display === '') {
    form.style.display = 'block';
    btn.innerHTML = '<i class="bi bi-x"></i> cancelar';
  } else {
    form.style.display = 'none';
    btn.innerHTML = '<i class="bi bi-pencil-fill"></i> editar';
  }
};

window.switchTab = function (tab) {
  const ownedEl  = document.getElementById('table-owned');
  const collabEl = document.getElementById('table-collabs');
  const btnOwned = document.getElementById('tab-btn-owned');
  const btnCollab = document.getElementById('tab-btn-collabs');
  if (tab === 'owned') {
    ownedEl.style.display  = '';
    collabEl.style.display = 'none';
    btnOwned.classList.add('active');
    btnCollab.classList.remove('active');
  } else {
    ownedEl.style.display  = 'none';
    collabEl.style.display = '';
    btnOwned.classList.remove('active');
    btnCollab.classList.add('active');
  }
};

/* ── Metrics chart ───────────────────────────────────────────────────────── */
(function () {
  'use strict';

  const METRICS = {
    storage: {
      data: CHART_STORAGE, type: 'bar', label: 'MB',
      color: 'rgba(25,135,84,0.75)', border: 'rgba(25,135,84,1)',
      subtitle: 'Almacenamiento por proyecto (MB) — top 10', yLabel: 'MB',
    },
    projects: {
      data: CHART_PROJECTS, type: 'bar', label: 'Proyectos',
      color: 'rgba(13,110,253,0.7)', border: 'rgba(13,110,253,1)',
      subtitle: 'Proyectos creados por mes (últimos 12 meses)', yLabel: 'Proyectos',
    },
    collabs: {
      data: CHART_COLLABS, type: 'bar', label: 'MB',
      color: 'rgba(255,193,7,0.75)', border: 'rgba(255,193,7,1)',
      subtitle: 'Almacenamiento en colaboraciones (MB) — top 10', yLabel: 'MB',
    },
  };

  const canvas   = document.getElementById('metricsChart');
  const emptyMsg = document.getElementById('chart-empty');
  const subtitle = document.getElementById('chart-subtitle');
  if (!canvas) return;

  const ctx = canvas.getContext('2d');
  let chart = null;

  function buildChart(metricKey) {
    const m = METRICS[metricKey];
    const isEmpty = !m.data.values || m.data.values.length === 0
                    || m.data.values.every(v => v === 0);
    if (isEmpty) {
      canvas.style.display = 'none';
      emptyMsg.classList.remove('d-none');
      subtitle.textContent = '';
      if (chart) { chart.destroy(); chart = null; }
      return;
    }
    canvas.style.display = '';
    emptyMsg.classList.add('d-none');
    subtitle.textContent = m.subtitle;
    if (chart) chart.destroy();
    chart = new Chart(ctx, {
      type: m.type,
      data: {
        labels: m.data.labels,
        datasets: [{ label: m.label, data: m.data.values,
          backgroundColor: m.color, borderColor: m.border,
          borderWidth: 1, borderRadius: 4 }],
      },
      options: {
        responsive: true, maintainAspectRatio: true,
        animation: { duration: 200 },
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: c => ` ${c.parsed.y} ${m.label}` } },
        },
        scales: {
          x: { ticks: { maxRotation: 35, font: { size: 11 } }, grid: { display: false } },
          y: { beginAtZero: true, ticks: { font: { size: 11 } },
               title: { display: true, text: m.yLabel, font: { size: 11 } } },
        },
      },
    });
  }

  document.querySelectorAll('[data-metric]').forEach(btn => {
    btn.addEventListener('click', () => {
      document.querySelectorAll('[data-metric]').forEach(b => b.classList.remove('active'));
      btn.classList.add('active');
      buildChart(btn.dataset.metric);
    });
  });

  buildChart('storage');
})();

/* ── Collab-cell tooltips (position:fixed escapes table-responsive overflow) */
document.querySelectorAll('.collab-cell').forEach(cell => {
  const tip = cell.querySelector('.collab-tip');
  if (!tip) return;
  cell.addEventListener('mouseenter', () => {
    const r = cell.getBoundingClientRect();
    tip.style.top  = (r.top + r.height / 2) + 'px';
    tip.style.left = (r.right + 10) + 'px';
    tip.style.display = 'block';
  });
  cell.addEventListener('mouseleave', () => { tip.style.display = 'none'; });
});
