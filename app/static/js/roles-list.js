/**
 * Overleaf Admin Platform — Roles list page (Chart.js)
 *
 * Espera que el template defina antes de cargar este archivo:
 *   ROLES_DATA  — { [roleName]: { name, userCount, quotaBytes, maxProjects } }
 */
(function () {
  'use strict';

  // Iteramos todos los roles que vengan de Python (ya ordenados por
  // is_default desc + name asc). Esto permite añadir roles nuevos sin
  // tocar la gráfica.
  const ROLES       = Object.values(ROLES_DATA);
  const TOTAL_USERS = ROLES.reduce((s, r) => s + r.userCount, 0); // eslint-disable-line no-unused-vars

  /* ── Colores por métrica ─────────────────────────────────────────── */
  const COL = {
    users:    { bg: 'rgba(25,135,84,.50)',   border: '#198754' },
    quota:    { bg: 'rgba(13,110,253,.55)',  border: '#0d6efd' },
    projects: { bg: 'rgba(255,193,7,.50)',   border: '#ffc107' },
  };

  /* ── Plugin: valor encima de cada barra ──────────────────────────── */
  const valueLabels = {
    id: 'valueLabels',
    afterDatasetsDraw(chart) {
      const { ctx } = chart;
      chart.data.datasets.forEach((ds, di) => {
        chart.getDatasetMeta(di).data.forEach((bar, j) => {
          const val = ds.data[j];
          if (val == null) return;
          ctx.save();
          ctx.fillStyle    = '#495057';
          ctx.font         = '600 10px system-ui, sans-serif';
          ctx.textAlign    = 'center';
          ctx.textBaseline = 'bottom';
          ctx.fillText(ds.yAxisID === 'y1' ? val + ' MB' : String(val), bar.x, bar.y - 4);
          ctx.restore();
        });
      });
    },
  };

  /* ── Plugin: ∞ para barras nulas ─────────────────────────────────── */
  const infinityLabels = {
    id: 'infinityLabels',
    afterDatasetsDraw(chart) {
      const { ctx, chartArea } = chart;
      chart.data.datasets.forEach((ds, di) => {
        chart.getDatasetMeta(di).data.forEach((bar, j) => {
          if (ds.data[j] !== null) return;
          ctx.save();
          ctx.fillStyle    = '#adb5bd';
          ctx.font         = 'bold 15px system-ui, sans-serif';
          ctx.textAlign    = 'center';
          ctx.textBaseline = 'bottom';
          ctx.fillText('∞', bar.x, chartArea.bottom - 4);
          ctx.restore();
        });
      });
    },
  };

  const canvas = document.getElementById('rolesChart');
  if (!canvas) return;

  const BAR_OPTS = {
    borderWidth: 1, borderRadius: 4, borderSkipped: false,
    maxBarThickness: 52, categoryPercentage: 0.78, barPercentage: 0.82,
  };

  new Chart(canvas, {
    type: 'bar',
    plugins: [valueLabels, infinityLabels],
    data: {
      labels: ROLES.map(r => r.name.charAt(0).toUpperCase() + r.name.slice(1)),
      datasets: [
        {
          label: 'Usuarios', data: ROLES.map(r => r.userCount),
          yAxisID: 'y', backgroundColor: COL.users.bg, borderColor: COL.users.border, ...BAR_OPTS,
        },
        {
          label: 'Cuota (MB)',
          data: ROLES.map(r => r.quotaBytes != null ? Math.round(r.quotaBytes / (1024 * 1024)) : null),
          yAxisID: 'y1', backgroundColor: COL.quota.bg, borderColor: COL.quota.border, ...BAR_OPTS,
        },
        {
          label: 'Proyectos', data: ROLES.map(r => r.maxProjects),
          yAxisID: 'y', backgroundColor: COL.projects.bg, borderColor: COL.projects.border, ...BAR_OPTS,
        },
      ],
    },
    options: {
      responsive: true, maintainAspectRatio: false,
      layout: { padding: { top: 20, bottom: 2, left: 2, right: 2 } },
      plugins: {
        legend: {
          display: true, position: 'top', align: 'end',
          labels: {
            boxWidth: 12, boxHeight: 12, borderRadius: 2, useBorderRadius: true,
            padding: 14, font: { size: 11, weight: '500' }, color: '#495057',
          },
        },
        tooltip: {
          backgroundColor: 'rgba(33,37,41,.9)', padding: 10, cornerRadius: 5,
          callbacks: {
            label(ctx) {
              if (ctx.raw === null) return ` ${ctx.dataset.label}: ∞ Ilimitado`;
              if (ctx.dataset.yAxisID === 'y1') return ` ${ctx.dataset.label}: ${ctx.raw} MB`;
              return ` ${ctx.dataset.label}: ${ctx.raw}`;
            },
          },
        },
      },
      scales: {
        x: { grid: { display: false }, ticks: { font: { size: 12, weight: '600' }, color: '#343a40' } },
        y: {
          type: 'linear', position: 'left', beginAtZero: true,
          border: { dash: [3, 3] }, grid: { color: 'rgba(0,0,0,.05)' },
          ticks: { precision: 0, font: { size: 10 }, color: '#9ca3af' },
          title: { display: true, text: 'Cantidad', font: { size: 10, weight: '500' }, color: '#9ca3af' },
        },
        y1: {
          type: 'linear', position: 'right', beginAtZero: true,
          border: { dash: [3, 3] }, grid: { drawOnChartArea: false },
          ticks: { precision: 0, font: { size: 10 }, color: '#9ca3af' },
          title: { display: true, text: 'Cuota (MB)', font: { size: 10, weight: '500' }, color: '#9ca3af' },
        },
      },
    },
  });

})();
