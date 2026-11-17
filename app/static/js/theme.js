// Runs before the page paints, so there is no light/dark flash.
(() => {
  let saved = null;
  try { saved = localStorage.getItem('ss-theme'); } catch (_) { /* storage can be unavailable */ }
  const dark = window.matchMedia && window.matchMedia('(prefers-color-scheme: dark)').matches;
  document.documentElement.dataset.theme = saved || (dark ? 'dark' : 'light');
})();