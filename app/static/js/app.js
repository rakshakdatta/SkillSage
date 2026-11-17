// Shared helpers. Everything a model or a user wrote is inserted with textContent, never as HTML.
(() => {
  const NS = 'http://www.w3.org/2000/svg';
  const $ = (id) => document.getElementById(id);

  const el = (tag, className, text) => {
    const node = document.createElement(tag);
    if (className) node.className = className;
    if (text !== undefined && text !== null) node.textContent = text;
    return node;
  };

  const svg = (tag, attrs = {}, text) => {
    const node = document.createElementNS(NS, tag);
    Object.entries(attrs).forEach(([k, v]) => node.setAttribute(k, String(v)));
    if (text !== undefined) node.textContent = text;
    return node;
  };

  async function api(url, options = {}) {
    const res = await fetch(url, options);
    let data = {};
    try { data = await res.json(); } catch (_) { /* non-JSON error page */ }
    if (!res.ok) {
      const err = new Error(data.error || 'Something went wrong. Please try again.');
      err.status = res.status;
      throw err;
    }
    return data;
  }
  const send = (method) => (url, body) => api(url, {
    method, headers: { 'Content-Type': 'application/json' }, body: JSON.stringify(body ?? {}),
  });

  const tone = (n) => (n >= 8 ? 'good' : n >= 6 ? 'mid' : 'bad');
  const verdict = (n) => (n >= 8 ? 'Strong' : n >= 6 ? 'Solid' : n >= 4 ? 'Needs work' : 'Keep practising');

  const SKILLS = {
    relevance: { label: 'Relevance', icon: '🎯', hint: 'Answers the question that was asked' },
    depth: { label: 'Depth', icon: '🔍', hint: 'Examples, numbers and trade-offs' },
    clarity: { label: 'Clarity', icon: '💬', hint: 'Concise and easy to follow' },
    structure: { label: 'Structure', icon: '🧩', hint: 'A logical order, like STAR' },
    grammar: { label: 'Grammar', icon: '✍️', hint: 'Complete, well-formed sentences' },
  };

  function fmtDate(iso, withTime = false) {
    if (!iso) return '';
    const d = new Date(iso);
    return withTime ? d.toLocaleString(undefined, { dateStyle: 'medium', timeStyle: 'short' }) : d.toLocaleDateString(undefined, { day: 'numeric', month: 'short', year: 'numeric' });
  }
  const initials = (name) => (name || '?').trim().split(/\s+/).slice(0, 2).map((w) => w[0]).join('').toUpperCase();

  function toast(message, kind = 'ok') {
    document.querySelectorAll('.toast').forEach((t) => t.remove());
    const t = el('div', `toast ${kind}`, message);
    t.setAttribute('role', 'status');
    document.body.appendChild(t);
    setTimeout(() => t.remove(), 3200);
  }

  // ── theme toggle and sign-out, present on every page ──
  const themeBtn = $('theme-toggle');
  if (themeBtn) {
    const sync = () => { themeBtn.textContent = document.documentElement.dataset.theme === 'dark' ? '☀️' : '🌙'; };
    sync();
    themeBtn.addEventListener('click', () => {
      const next = document.documentElement.dataset.theme === 'dark' ? 'light' : 'dark';
      document.documentElement.dataset.theme = next;
      try { localStorage.setItem('ss-theme', next); } catch (_) { /* ignore */ }
      sync();
    });
  }
  const signOut = $('sign-out');
  if (signOut) {
    signOut.addEventListener('click', async () => {
      try { await send('POST')('/api/auth/logout'); } finally { window.location.assign('/'); }
    });
  }

  window.SS = { $, el, svg, api, post: send('POST'), patch: send('PATCH'), del: send('DELETE'), tone, verdict, SKILLS, fmtDate, initials, toast };
})();