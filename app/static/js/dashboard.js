/**
 * Overleaf Admin Platform — Dashboard page (Chart.js)
 *
 * Espera que el template defina antes de cargar este archivo:
 *   ROLE_LABELS    — array de nombres de rol (keys de d.role_stats)
 *   ROLE_VALUES    — array de conteos       (values de d.role_stats)
 *   QUOTA_URL      — endpoint de paginación de usuarios con cuota alta
 *   USER_DETAIL_BASE — URL base del detalle de usuario (terminada en '/')
 *   QUOTA_TOTAL    — número total de usuarios cerca de cuota
 */
(function () {
  'use strict';

  /* ── 1. Role distribution doughnut ──────────────────────────────────────── */
  const rlCanvas = document.getElementById('chartRoles');
  if (rlCanvas && window.Chart) {
    Chart.defaults.font.family = getComputedStyle(document.body).fontFamily || "system-ui, -apple-system, sans-serif";
    Chart.defaults.font.weight = "400";
    Chart.defaults.color = '#495057';

    const ROLE_COLORS = {
      alumno:   'rgba(61,139,61,.78)',
      profesor: 'rgba(255,193,7,.85)',
      admin:    'rgba(13,110,253,.72)',
      gestor:   'rgba(32,201,151,.78)',
    };
    const fallback = ['rgba(61,139,61,.78)', 'rgba(255,193,7,.85)',
                      'rgba(13,110,253,.72)', 'rgba(32,201,151,.78)', 'rgba(108,117,125,.7)'];
    const bg = ROLE_LABELS.map((n, i) =>
      ROLE_COLORS[String(n).toLowerCase()] || fallback[i % fallback.length]
    );

    new Chart(rlCanvas, {
      type: 'doughnut',
      data: { labels: ROLE_LABELS, datasets: [{ data: ROLE_VALUES, backgroundColor: bg,
        borderColor: '#fff', borderWidth: 2 }] },
      options: {
        responsive: true, maintainAspectRatio: false, cutout: '52%',
        layout: { padding: { top: 2, bottom: 0 } },
        plugins: {
          legend: { position: 'bottom',
            labels: {
              boxWidth: 10, boxHeight: 10, padding: 7, font: { size: 11, weight: '400' },
              generateLabels(chart) {
                const ds = chart.data.datasets[0];
                return chart.data.labels.map((lbl, i) => ({
                  text: `${lbl}  (${ds.data[i]})`,
                  fillStyle: ds.backgroundColor[i],
                  strokeStyle: '#fff', lineWidth: 2, hidden: false, index: i,
                }));
              },
            },
          },
          tooltip: { backgroundColor: 'rgba(33,37,41,.92)', padding: 8, cornerRadius: 6 },
        },
      },
    });
  }

  /* ── 2. Quota users — paginated rotation ─────────────────────────────────── */
  const PER_PAGE  = 7;
  const ROTATE_MS = 10000;

  if (QUOTA_TOTAL > PER_PAGE) {
    const listEl     = document.getElementById('quotaList');
    const counterEl  = document.getElementById('quotaCounter');
    const prevBtn    = document.getElementById('quotaPrev');
    const nextBtn    = document.getElementById('quotaNext');
    const totalPages = Math.ceil(QUOTA_TOTAL / PER_PAGE);
    let currentPage  = 1;
    let autoTimer    = null;

    function pctColor(pct) {
      const t = Math.min(Math.max((pct - 80) / 40, 0), 1);
      const r = Math.round(245 - 25 * t);
      const g = Math.round(166 - 126 * t);
      const b = Math.round(35 - 5 * t);
      const a = (.55 + .40 * t).toFixed(2);
      return `rgba(${r},${g},${b},${a})`;
    }

    function renderPage(data) {
      if (!data.items.length) return;
      listEl.innerHTML = data.items.map(u => `
        <div class="quota-item">
          <a href="${USER_DETAIL_BASE}${u.id}" class="text-decoration-none text-dark truncate"
             style="max-width:140px;" title="${esc(u.label)}">${esc(u.label)}</a>
          <div class="quota-bar">
            <div class="quota-bar-fill" style="width:100%; background:${pctColor(u.pct)};"></div>
          </div>
          <span class="quota-pct">${u.pct}%</span>
        </div>`).join('');
      counterEl.textContent = `${data.page}/${totalPages} (${data.total})`;
    }

    function loadPage(page) {
      const p = ((page - 1) % totalPages + totalPages) % totalPages + 1;
      currentPage = p;
      listEl.classList.add('fading');
      setTimeout(() => {
        fetch(`${QUOTA_URL}?page=${p}&per_page=${PER_PAGE}`, {
          credentials: 'same-origin', headers: { Accept: 'application/json' },
        })
          .then(r => r.json())
          .then(data => { renderPage(data); listEl.classList.remove('fading'); })
          .catch(() => listEl.classList.remove('fading'));
      }, 250);
    }

    function resetTimer() {
      if (autoTimer) clearInterval(autoTimer);
      autoTimer = setInterval(() => loadPage(currentPage + 1), ROTATE_MS);
    }

    prevBtn.addEventListener('click', () => { loadPage(currentPage - 1); resetTimer(); });
    nextBtn.addEventListener('click', () => { loadPage(currentPage + 1); resetTimer(); });
    resetTimer();
  } else {
    const nav = document.querySelector('.quota-nav');
    if (nav) nav.style.display = 'none';
  }

})();
