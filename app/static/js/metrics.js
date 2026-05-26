/**
 * Overleaf Admin Platform — Metrics page (Chart.js)
 *
 * Espera que el template defina antes de cargar este archivo:
 *   CHART_DATA        — { growthUsers, growthProjects, topOwners, topStorage,
 *                         sizeBuckets, roleDistribution, syncSuccessRate }
 *   USER_DETAIL_BASE  — URL base del detalle de usuario (terminada en '/')
 *
 * El JS guarda cada instancia de Chart en `charts[id]` para poder:
 *   - llamar resize() cuando una tab oculta se muestra
 *   - mantenerlas accesibles para debug en consola
 */
(function () {
  'use strict';

  if (window.Chart) {
    Chart.defaults.font.family = "system-ui, -apple-system, sans-serif";
    Chart.defaults.color = '#495057';
  }

  // Registro de instancias por id de canvas
  const charts = {};

  const TRUNC = 22;
  const trunc = l => (typeof l === 'string' && l.length > TRUNC) ? l.slice(0, TRUNC - 1) + '…' : l;

  const vGrad = (canvas, top, bot) => {
    const g = canvas.getContext('2d').createLinearGradient(0, 0, 0, canvas.height || 260);
    g.addColorStop(0, top); g.addColorStop(1, bot); return g;
  };

  function userClick(userIds) {
    return function (evt, elements) {
      if (elements.length && userIds[elements[0].index]) {
        window.location.href = USER_DETAIL_BASE + userIds[elements[0].index];
      }
    };
  }

  // Helper: crea una instancia y la registra. Si el canvas no existe, no-op.
  function mountChart(id, configFactory) {
    const canvas = document.getElementById(id);
    if (!canvas) return null;
    const config = configFactory(canvas);
    if (!config) return null;
    charts[id] = new Chart(canvas, config);
    return charts[id];
  }

  /* ── Crecimiento usuarios ──────────────────────────────────────── */
  function growthUsersConfig(canvas) {
    const { growthUsers } = CHART_DATA;
    const labels = growthUsers.map(r => r.label);
    const values = growthUsers.map(r => r.count);
    const totals = growthUsers.map(r => r.total);
    const grad   = vGrad(canvas, 'rgba(102,16,242,.35)', 'rgba(102,16,242,0)');
    return {
      type: 'line',
      data: { labels, datasets: [
        { label: 'Nuevos usuarios', data: values, yAxisID: 'y',
          borderColor: 'rgba(102,16,242,.9)', backgroundColor: grad,
          tension: .35, fill: true, borderWidth: 2.2,
          pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: 'rgba(102,16,242,.9)' },
        { label: 'Total usuarios', data: totals, yAxisID: 'y1',
          borderColor: 'rgba(102,16,242,.35)', backgroundColor: 'transparent',
          tension: .35, fill: false, borderWidth: 1.8, borderDash: [5, 3],
          pointRadius: 2, pointHoverRadius: 4, pointBackgroundColor: 'rgba(102,16,242,.35)' },
      ] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: true, position: 'top',
            labels: { boxWidth: 12, boxHeight: 3, padding: 8, font: { size: 9.5 } } },
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
    };
  }
  mountChart('chartGrowthUsers', growthUsersConfig);

  /* ── Crecimiento proyectos ─────────────────────────────────────── */
  function growthProjectsConfig(canvas) {
    const { growthProjects } = CHART_DATA;
    const labels = growthProjects.map(r => r.label);
    const values = growthProjects.map(r => r.count);
    const totals = growthProjects.map(r => r.total);
    const grad   = vGrad(canvas, 'rgba(13,110,253,.35)', 'rgba(13,110,253,0)');
    return {
      type: 'line',
      data: { labels, datasets: [
        { label: 'Nuevos proyectos', data: values, yAxisID: 'y',
          borderColor: 'rgba(13,110,253,.9)', backgroundColor: grad,
          tension: .35, fill: true, borderWidth: 2.2,
          pointRadius: 3, pointHoverRadius: 5, pointBackgroundColor: 'rgba(13,110,253,.9)' },
        { label: 'Total proyectos', data: totals, yAxisID: 'y1',
          borderColor: 'rgba(13,110,253,.35)', backgroundColor: 'transparent',
          tension: .35, fill: false, borderWidth: 1.8, borderDash: [5, 3],
          pointRadius: 2, pointHoverRadius: 4, pointBackgroundColor: 'rgba(13,110,253,.35)' },
      ] },
      options: {
        responsive: true, maintainAspectRatio: false,
        plugins: {
          legend: { display: true, position: 'top',
            labels: { boxWidth: 12, boxHeight: 3, padding: 8, font: { size: 9.5 } } },
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
    };
  }
  mountChart('chartGrowthProjects', growthProjectsConfig);

  /* ── Top propietarios ──────────────────────────────────────────── */
  function topOwnersConfig(canvas) {
    const { topOwners } = CHART_DATA;
    const labels  = topOwners.map(r => r.label);
    const values  = topOwners.map(r => r.count);
    const userIds = topOwners.map(r => r.user_id);
    return {
      type: 'bar',
      data: { labels: labels.map(trunc), datasets: [{
        data: values,
        backgroundColor: vGrad(canvas, 'rgba(13,110,253,1)', 'rgba(13,110,253,.7)'),
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
    };
  }
  mountChart('chartTopOwners', topOwnersConfig);

  /* ── Top almacenamiento ────────────────────────────────────────── */
  function topStorageConfig(canvas) {
    const { topStorage } = CHART_DATA;
    const labels  = topStorage.map(r => r.label);
    const fmts    = topStorage.map(r => r.fmt);
    const bytes   = topStorage.map(r => r.bytes);
    const userIds = topStorage.map(r => r.user_id);
    const mbs     = bytes.map(b => +(b / (1024 * 1024)).toFixed(1));
    return {
      type: 'bar',
      data: { labels: labels.map(trunc), datasets: [{
        data: mbs,
        backgroundColor: vGrad(canvas, 'rgba(19,138,108,1)', 'rgba(19,138,108,.7)'),
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
    };
  }
  mountChart('chartTopStorage', topStorageConfig);

  /* ── Distribución por tamaño ───────────────────────────────────── */
  function sizesConfig(canvas) {
    const { sizeBuckets } = CHART_DATA;
    const labels = sizeBuckets.map(r => r.label);
    const values = sizeBuckets.map(r => r.count);
    const colors = ['rgba(32,201,151,.78)', 'rgba(61,139,61,.78)', 'rgba(255,193,7,.85)',
                    'rgba(253,126,20,.82)', 'rgba(220,53,69,.78)'];
    return {
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
    };
  }
  // El gráfico de tamaños aparece en Resumen y en Almacenamiento — dos canvases distintos.
  mountChart('chartSizes',  sizesConfig);
  mountChart('chartSizes2', sizesConfig);

  /* ── Distribución por rol (donut) ──────────────────────────────── */
  function rolesConfig(_canvas) {
    const { roleDistribution } = CHART_DATA;
    const labels = roleDistribution.map(r => r.name);
    const values = roleDistribution.map(r => r.count);
    const ROLE_COLORS = {
      alumno: 'rgba(61,139,61,.78)', profesor: 'rgba(255,193,7,.85)', admin: 'rgba(13,110,253,.72)',
    };
    const fallback = ['rgba(61,139,61,.78)', 'rgba(255,193,7,.85)', 'rgba(13,110,253,.72)',
                      'rgba(32,201,151,.78)', 'rgba(108,117,125,.7)'];
    const bg = labels.map((n, i) => ROLE_COLORS[n.toLowerCase()] || fallback[i % fallback.length]);
    return {
      type: 'doughnut',
      data: { labels, datasets: [{ data: values, backgroundColor: bg, borderColor: '#fff', borderWidth: 2 }] },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '60%',
        plugins: {
          legend: { position: 'bottom', labels: { boxWidth: 12, boxHeight: 12, padding: 10, font: { size: 10 } } },
          tooltip: { backgroundColor: 'rgba(33,37,41,.92)', padding: 10, cornerRadius: 6 },
        },
      },
    };
  }
  // El gráfico de roles aparece en Resumen y en Usuarios y proyectos — dos canvases distintos.
  mountChart('chartRoles',  rolesConfig);
  mountChart('chartRoles2', rolesConfig);

  /* ── Tasa de éxito de sync (donut) ─────────────────────────────── */
  mountChart('chartSyncRate', () => {
    const rate = CHART_DATA.syncSuccessRate || 0;
    return {
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
    };
  });

  /* ─────────────────────────────────────────────────────────────────
     Switcher de gráficas dentro de una card
     ─────────────────────────────────────────────────────────────────
     Cada `.chart-switch` tiene un `data-target` con el selector de los
     paneles hermanos (`.growth-panel`, `.ranking-panel`, ...). Los
     `<input class="btn-check">` llevan `data-show` con el nombre del
     panel a mostrar. Al cambiar, oculta los demás y redimensiona el
     canvas del panel activo. */
  document.querySelectorAll('.chart-switch').forEach(group => {
    const targetSel = group.getAttribute('data-target');
    if (!targetSel) return;
    const panels = document.querySelectorAll(targetSel);
    group.querySelectorAll('input.btn-check').forEach(input => {
      input.addEventListener('change', () => {
        if (!input.checked) return;
        const show = input.getAttribute('data-show');
        panels.forEach(p => {
          const isActive = p.getAttribute('data-panel') === show;
          p.classList.toggle('d-none', !isActive);
          if (isActive) {
            // Redimensiona el chart visible (puede haber crecido el contenedor)
            const canvas = p.querySelector('canvas');
            if (canvas && charts[canvas.id]) charts[canvas.id].resize();
          }
        });
      });
    });
  });

  /* ─────────────────────────────────────────────────────────────────
     Tabs: redimensionar charts al mostrar la pestaña (Chart.js no
     calcula bien las dimensiones cuando el canvas está oculto) y
     guardar la tab activa en el hash de URL para persistirla.
     ───────────────────────────────────────────────────────────────── */
  function resizeAllVisible() {
    Object.values(charts).forEach(c => {
      try { c.resize(); } catch (e) { /* ignore */ }
    });
  }

  // Activar tab desde hash (#tab-storage, etc.) en carga.
  if (window.location.hash && /^#tab-[\w-]+$/.test(window.location.hash)) {
    const btn = document.querySelector(`[data-bs-target="${window.location.hash}"]`);
    if (btn && window.bootstrap && bootstrap.Tab) {
      bootstrap.Tab.getOrCreateInstance(btn).show();
    }
  }

  // Cada vez que se muestra una tab, redimensionamos los charts y
  // sincronizamos el hash. Usamos un timeout corto para que Bootstrap
  // termine la transición CSS antes de medir.
  document.querySelectorAll('#metricsTabs button[data-bs-toggle="tab"]').forEach(btn => {
    btn.addEventListener('shown.bs.tab', (ev) => {
      const target = btn.getAttribute('data-bs-target');
      if (target) {
        // Reemplaza el hash sin generar entrada en historial
        if (history.replaceState) {
          history.replaceState(null, '', target);
        } else {
          window.location.hash = target;
        }
      }
      setTimeout(resizeAllVisible, 60);
    });
  });

})();
