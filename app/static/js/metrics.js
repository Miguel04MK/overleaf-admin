/**
 * Overleaf Admin Platform — Metrics page (Chart.js)
 *
 * Espera que el template defina antes de cargar este archivo:
 *   CHART_DATA        — { growthUsers, growthProjects, topOwners, topStorage,
 *                         sizeBuckets, roleDistribution, syncSuccessRate }
 *   USER_DETAIL_BASE  — URL base del detalle de usuario (terminada en '/')
 */
(function () {
  'use strict';

  if (window.Chart) {
    Chart.defaults.font.family = "system-ui, -apple-system, sans-serif";
    Chart.defaults.color = '#495057';
  }

  const TRUNC = 22;
  const trunc = l => (typeof l === 'string' && l.length > TRUNC) ? l.slice(0, TRUNC - 1) + '…' : l;

  const vGrad = (canvas, top, bot) => {
    const g = canvas.getContext('2d').createLinearGradient(0, 0, 0, canvas.height || 260);
    g.addColorStop(0, top); g.addColorStop(1, bot); return g;
  };

  // Click en barra → navegar al detalle del usuario
  function userClick(userIds) {
    return function (evt, elements) {
      if (elements.length && userIds[elements[0].index]) {
        window.location.href = USER_DETAIL_BASE + userIds[elements[0].index];
      }
    };
  }

  /* ── Crecimiento de usuarios ──────────────────────────────────── */
  const guCanvas = document.getElementById('chartGrowthUsers');
  if (guCanvas) {
    const { growthUsers } = CHART_DATA;
    const labels = growthUsers.map(r => r.label);
    const values = growthUsers.map(r => r.count);
    const totals = growthUsers.map(r => r.total);
    const grad   = vGrad(guCanvas, 'rgba(102,16,242,.35)', 'rgba(102,16,242,0)');
    new Chart(guCanvas, {
      type: 'line',
      data: { labels, datasets: [
        {
          label: 'Nuevos usuarios', data: values, yAxisID: 'y',
          borderColor: 'rgba(102,16,242,.9)', backgroundColor: grad,
          tension: .35, fill: true, borderWidth: 2.2,
          pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: 'rgba(102,16,242,.9)',
        }, {
          label: 'Total usuarios', data: totals, yAxisID: 'y1',
          borderColor: 'rgba(102,16,242,.35)', backgroundColor: 'transparent',
          tension: .35, fill: false, borderWidth: 1.8, borderDash: [5, 3],
          pointRadius: 2, pointHoverRadius: 4, pointBackgroundColor: 'rgba(102,16,242,.35)',
        },
      ] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: true, position: 'top',
            labels: { boxWidth: 12, boxHeight: 3, padding: 8, font: { size: 9.5 }, usePointStyle: false } },
          tooltip: { backgroundColor: 'rgba(33,37,41,.92)', padding: 10, cornerRadius: 6 },
        },
        scales: {
          x:  { grid: { display: false }, ticks: { font: { size: 10 }, color: '#9ca3af' } },
          y:  { beginAtZero: true, grid: { color: 'rgba(0,0,0,.05)' },
                ticks: { precision: 0, font: { size: 10 }, color: '#9ca3af' } },
          y1: { position: 'right', grid: { drawOnChartArea: false },
                ticks: { precision: 0, font: { size: 9 }, color: 'rgba(102,16,242,.4)' } },
        },
      },
    });
  }

  /* ── Crecimiento de proyectos ─────────────────────────────────── */
  const gpCanvas = document.getElementById('chartGrowthProjects');
  if (gpCanvas) {
    const { growthProjects } = CHART_DATA;
    const labels = growthProjects.map(r => r.label);
    const values = growthProjects.map(r => r.count);
    const totals = growthProjects.map(r => r.total);
    const grad   = vGrad(gpCanvas, 'rgba(13,110,253,.35)', 'rgba(13,110,253,0)');
    new Chart(gpCanvas, {
      type: 'line',
      data: { labels, datasets: [
        {
          label: 'Nuevos proyectos', data: values, yAxisID: 'y',
          borderColor: 'rgba(13,110,253,.9)', backgroundColor: grad,
          tension: .35, fill: true, borderWidth: 2.2,
          pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: 'rgba(13,110,253,.9)',
        }, {
          label: 'Total proyectos', data: totals, yAxisID: 'y1',
          borderColor: 'rgba(13,110,253,.35)', backgroundColor: 'transparent',
          tension: .35, fill: false, borderWidth: 1.8, borderDash: [5, 3],
          pointRadius: 2, pointHoverRadius: 4, pointBackgroundColor: 'rgba(13,110,253,.35)',
        },
      ] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: true, position: 'top',
            labels: { boxWidth: 12, boxHeight: 3, padding: 8, font: { size: 9.5 }, usePointStyle: false } },
          tooltip: { backgroundColor: 'rgba(33,37,41,.92)', padding: 10, cornerRadius: 6 },
        },
        scales: {
          x:  { grid: { display: false }, ticks: { font: { size: 10 }, color: '#9ca3af' } },
          y:  { beginAtZero: true, grid: { color: 'rgba(0,0,0,.05)' },
                ticks: { precision: 0, font: { size: 10 }, color: '#9ca3af' } },
          y1: { position: 'right', grid: { drawOnChartArea: false },
                ticks: { precision: 0, font: { size: 9 }, color: 'rgba(13,110,253,.4)' } },
        },
      },
    });
  }

  /* ── Top propietarios ─────────────────────────────────────────── */
  const toCanvas = document.getElementById('chartTopOwners');
  if (toCanvas) {
    const { topOwners } = CHART_DATA;
    const labels  = topOwners.map(r => r.label);
    const values  = topOwners.map(r => r.count);
    const userIds = topOwners.map(r => r.user_id);
    new Chart(toCanvas, {
      type: 'bar',
      data: { labels: labels.map(trunc), datasets: [{
        data: values,
        backgroundColor: vGrad(toCanvas, 'rgba(13,110,253,1)', 'rgba(13,110,253,.7)'),
        borderColor: 'rgba(13,110,253,1)', borderWidth: 1, borderRadius: 4, maxBarThickness: 20,
      }] },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        onClick: userClick(userIds),
        plugins: { legend: { display: false },
          tooltip: { backgroundColor: 'rgba(33,37,41,.92)', padding: 10, cornerRadius: 6,
            callbacks: { title: i => labels[i[0].dataIndex], label: ctx => ` ${ctx.raw} proyectos` } } },
        scales: {
          x: { beginAtZero: true, ticks: { precision: 0, font: { size: 10 }, color: '#9ca3af' }, grid: { color: 'rgba(0,0,0,.05)' } },
          y: { ticks: { font: { size: 10 }, color: '#495057', autoSkip: false }, grid: { display: false } },
        },
      },
    });
  }

  /* ── Top almacenamiento ───────────────────────────────────────── */
  const tsCanvas = document.getElementById('chartTopStorage');
  if (tsCanvas) {
    const { topStorage } = CHART_DATA;
    const labels  = topStorage.map(r => r.label);
    const fmts    = topStorage.map(r => r.fmt);
    const bytes   = topStorage.map(r => r.bytes);
    const userIds = topStorage.map(r => r.user_id);
    const mbs     = bytes.map(b => +(b / (1024 * 1024)).toFixed(1));
    new Chart(tsCanvas, {
      type: 'bar',
      data: { labels: labels.map(trunc), datasets: [{
        data: mbs,
        backgroundColor: vGrad(tsCanvas, 'rgba(19,138,108,1)', 'rgba(19,138,108,.7)'),
        borderColor: 'rgba(14,109,86,1)', borderWidth: 1, borderRadius: 4, maxBarThickness: 20,
      }] },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        onClick: userClick(userIds),
        plugins: { legend: { display: false },
          tooltip: { backgroundColor: 'rgba(33,37,41,.92)', padding: 10, cornerRadius: 6,
            callbacks: {
              title: i => labels[i[0].dataIndex],
              label: ctx => ` ${fmts[ctx.dataIndex]} (${ctx.raw} MB)`,
            } } },
        scales: {
          x: { beginAtZero: true,
               ticks: { precision: 0, font: { size: 10 }, color: '#9ca3af', callback: v => v + ' MB' },
               grid: { color: 'rgba(0,0,0,.05)' } },
          y: { ticks: { font: { size: 10 }, color: '#495057', autoSkip: false }, grid: { display: false } },
        },
      },
    });
  }

  /* ── Distribución por tamaño ──────────────────────────────────── */
  const szCanvas = document.getElementById('chartSizes');
  if (szCanvas) {
    const { sizeBuckets } = CHART_DATA;
    const labels = sizeBuckets.map(r => r.label);
    const values = sizeBuckets.map(r => r.count);
    const colors = ['rgba(32,201,151,.78)', 'rgba(61,139,61,.78)', 'rgba(255,193,7,.85)',
                    'rgba(253,126,20,.82)', 'rgba(220,53,69,.78)'];
    new Chart(szCanvas, {
      type: 'bar',
      data: { labels, datasets: [{ data: values, backgroundColor: colors,
        borderColor: colors.map(c => c.replace(/[\d.]+\)$/, '1)')),
        borderWidth: 1, borderRadius: 4, maxBarThickness: 18 }] },
      options: {
        indexAxis: 'y', responsive: true, maintainAspectRatio: false,
        plugins: { legend: { display: false },
          tooltip: { backgroundColor: 'rgba(33,37,41,.92)', padding: 10, cornerRadius: 6,
            callbacks: { label: ctx => ` ${ctx.raw} proyectos` } } },
        scales: {
          x: { beginAtZero: true, ticks: { precision: 0, font: { size: 10 }, color: '#9ca3af' }, grid: { color: 'rgba(0,0,0,.05)' } },
          y: { ticks: { font: { size: 10 }, color: '#495057' }, grid: { display: false } },
        },
      },
    });
  }

  /* ── Distribución por rol (donut) ─────────────────────────────── */
  const rlCanvas = document.getElementById('chartRoles');
  if (rlCanvas) {
    const { roleDistribution } = CHART_DATA;
    const labels = roleDistribution.map(r => r.name);
    const values = roleDistribution.map(r => r.count);
    const ROLE_COLORS = {
      alumno: 'rgba(61,139,61,.78)', profesor: 'rgba(255,193,7,.85)', admin: 'rgba(13,110,253,.72)',
    };
    const fallback = ['rgba(61,139,61,.78)', 'rgba(255,193,7,.85)', 'rgba(13,110,253,.72)',
                      'rgba(32,201,151,.78)', 'rgba(108,117,125,.7)'];
    const bg = labels.map((n, i) => ROLE_COLORS[n.toLowerCase()] || fallback[i % fallback.length]);
    new Chart(rlCanvas, {
      type: 'doughnut',
      data: { labels, datasets: [{ data: values, backgroundColor: bg, borderColor: '#fff', borderWidth: 2 }] },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '60%',
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, boxHeight: 12, padding: 10, font: { size: 10 } } },
          tooltip: { backgroundColor: 'rgba(33,37,41,.92)', padding: 10, cornerRadius: 6 },
        },
      },
    });
  }

  /* ── Tasa de éxito de sync (donut) ───────────────────────────── */
  const srCanvas = document.getElementById('chartSyncRate');
  if (srCanvas) {
    const rate = CHART_DATA.syncSuccessRate || 0;
    new Chart(srCanvas, {
      type: 'doughnut',
      data: { labels: ['Exitosas', 'Fallidas'],
        datasets: [{ data: [rate, 100 - rate],
          backgroundColor: ['rgba(25,135,84,.78)', 'rgba(220,53,69,.35)'], borderWidth: 0 }] },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '72%',
        plugins: {
          legend: { display: false },
          tooltip: { callbacks: { label: ctx => ` ${ctx.raw.toFixed(1)}%` } },
        },
      },
    });
  }

})();
