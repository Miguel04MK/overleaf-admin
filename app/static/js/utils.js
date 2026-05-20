/**
 * Overleaf Admin Platform — shared JS utilities
 * Cargado globalmente en base.html antes de extra_js.
 */

/**
 * Escapa caracteres HTML en una cadena.
 * @param {*} s - Valor a escapar
 * @returns {string}
 */
function esc(s) {
  if (s == null) return '';
  return String(s)
    .replace(/&/g, '&amp;')
    .replace(/</g, '&lt;')
    .replace(/>/g, '&gt;')
    .replace(/"/g, '&quot;');
}

/**
 * Convierte bytes a formato legible (KB, MB, GB…).
 * @param {number|string} bytes
 * @param {object} [opts]
 * @param {boolean} [opts.nullOnZero=false] - Devuelve null si bytes <= 0
 * @returns {string|null}
 */
function formatBytes(bytes, { nullOnZero = false } = {}) {
  const n = Number(bytes);
  if (isNaN(n)) return String(bytes);
  if (n <= 0) return nullOnZero ? null : '0 B';
  const units = ['B', 'KB', 'MB', 'GB', 'TB'];
  const i = Math.min(Math.floor(Math.log(n) / Math.log(1024)), units.length - 1);
  const val = n / Math.pow(1024, i);
  return (val % 1 === 0 ? val : val.toFixed(1)) + ' ' + units[i];
}

/**
 * Crea una versión debounced de una función.
 * @param {Function} fn
 * @param {number} delay - ms
 * @returns {Function}
 */
function debounce(fn, delay) {
  let timer;
  return function (...args) {
    clearTimeout(timer);
    timer = setTimeout(() => fn.apply(this, args), delay);
  };
}
