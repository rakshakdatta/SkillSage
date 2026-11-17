// Charts, score displays, and the feedback / report views shared by several pages.
(() => {
  const { el, svg, tone, verdict, SKILLS, fmtDate } = window.SS;
  const DIMS = Object.keys(SKILLS);

  // ── small building blocks ──
  function ring(value, { small = false, label = '/ 10' } = {}) {
    const wrap = el('div', `ring ${tone(value)}${small ? ' small' : ''}`);
    wrap.style.setProperty('--pct', String(Math.max(0, Math.min(100, value * 10))));
    wrap.setAttribute('role', 'img');
    wrap.setAttribute('aria-label', `Score ${value} out of 10`);
    const inner = el('span');
    const num = el('div');
    num.appendChild(el('b', '', Number(value).toFixed(1).replace(/\.0$/, '')));
    if (label && !small) num.appendChild(el('small', '', label));
    inner.appendChild(num);
    wrap.appendChild(inner);
    return wrap;
  }

  function skillBars(scores) {
    const box = el('div', 'skills');
    DIMS.filter((d) => scores[d] !== undefined).forEach((d) => {
      const value = scores[d];
      const row = el('div', 'skill');
      row.title = SKILLS[d].hint;
      row.appendChild(el('span', '', `${SKILLS[d].icon} ${SKILLS[d].label}`));
      const rail = el('div', 'rail');
      const fill = el('i', tone(value));
      fill.style.width = `${Math.max(4, value * 10)}%`;
      rail.appendChild(fill);
      row.appendChild(rail);
      row.appendChild(el('span', `val ${tone(value)}`, String(value)));
      box.appendChild(row);
    });
    return box;
  }

  function radar(scores) {
    const size = 300, c = 150, R = 98;
    const dims = DIMS.filter((d) => scores[d] !== undefined);
    const angle = (i) => (-Math.PI / 2) + (i * 2 * Math.PI) / dims.length;
    const point = (i, r) => [c + r * Math.cos(angle(i)), c + r * Math.sin(angle(i))];
    const chart = svg('svg', { viewBox: `-55 0 ${size + 110} ${size}`, class: 'radar', role: 'img', width: 340, height: 254,
      'aria-label': `Skill profile: ${dims.map((d) => `${SKILLS[d].label} ${scores[d]}`).join(', ')}` });
    [2, 4, 6, 8, 10].forEach((lvl) => {
      chart.appendChild(svg('polygon', { class: 'grid', points: dims.map((_, i) => point(i, (R * lvl) / 10).join(',')).join(' ') }));
    });
    dims.forEach((_, i) => { const [x, y] = point(i, R); chart.appendChild(svg('line', { class: 'axis', x1: c, y1: c, x2: x, y2: y })); });
    chart.appendChild(svg('polygon', { class: 'shape', points: dims.map((d, i) => point(i, (R * scores[d]) / 10).join(',')).join(' ') }));
    dims.forEach((d, i) => { const [x, y] = point(i, (R * scores[d]) / 10); chart.appendChild(svg('circle', { class: 'pt', cx: x, cy: y, r: 3.6 })); });
    dims.forEach((d, i) => {
      const [x, y] = point(i, R + 22);
      const anchor = Math.abs(x - c) < 6 ? 'middle' : x > c ? 'start' : 'end';
      chart.appendChild(svg('text', { x, y: y + 4, 'text-anchor': anchor }, SKILLS[d].label));
    });
    return chart;
  }

  function lineChart(points) {
    const W = 620, H = 220, pl = 34, pr = 16, pt = 14, pb = 30;
    const chart = svg('svg', { viewBox: `0 0 ${W} ${H}`, class: 'line', role: 'img', width: '100%',
      'aria-label': `Overall score over your last ${points.length} interviews: ${points.map((p) => p.overall).join(', ')}` });
    const x = (i) => (points.length === 1 ? (W + pl - pr) / 2 : pl + (i * (W - pl - pr)) / (points.length - 1));
    // zoom the y-axis to the data so real improvement is visible (never below 0, always up to 10)
    const lo = Math.max(0, Math.floor(Math.min(...points.map((p) => p.overall)) - 1));
    const y = (v) => pt + (H - pt - pb) * (1 - (v - lo) / (10 - lo));
    [lo, Math.round((lo + 10) / 2), 10].forEach((v) => {
      chart.appendChild(svg('line', { class: 'grid', x1: pl, x2: W - pr, y1: y(v), y2: y(v) }));
      chart.appendChild(svg('text', { x: pl - 8, y: y(v) + 4, 'text-anchor': 'end' }, String(v)));
    });
    const coords = points.map((p, i) => [x(i), y(p.overall)]);
    if (points.length > 1) {
      chart.appendChild(svg('polygon', { class: 'area', points: `${coords[0][0]},${y(lo)} ${coords.map((q) => q.join(',')).join(' ')} ${coords[coords.length - 1][0]},${y(lo)}` }));
      chart.appendChild(svg('polyline', { class: 'path', points: coords.map((q) => q.join(',')).join(' ') }));
    }
    points.forEach((p, i) => {
      const dot = svg('circle', { class: 'pt', cx: coords[i][0], cy: coords[i][1], r: 5 });
      dot.appendChild(svg('title', {}, `${fmtDate(p.date)} · ${p.role} · ${p.overall}/10`));
      chart.appendChild(dot);
    });
    chart.appendChild(svg('text', { x: pl, y: H - 8, 'text-anchor': 'start' }, fmtDate(points[0].date)));
    if (points.length > 1) chart.appendChild(svg('text', { x: W - pr, y: H - 8, 'text-anchor': 'end' }, fmtDate(points[points.length - 1].date)));
    return chart;
  }

  const bullets = (items, empty) => {
    const ul = el('ul', 'bullets');
    (items && items.length ? items : [empty]).forEach((t) => ul.appendChild(el('li', '', t)));
    return ul;
  };

  // ── grammar + delivery ──
  function grammarSection(ev) {
    const box = el('section');
    const head = el('div', 'grammar-head');
    head.appendChild(el('h3', '', '✍️ Grammar check'));
    const issues = ev.grammar_issues || [];
    head.appendChild(el('span', `chip ${issues.length ? '' : 'plain'}`, issues.length ? `${issues.length} to fix` : 'Well formed'));
    box.appendChild(head);
    if (!issues.length) {
      box.appendChild(el('div', 'alert ok', 'No sentence-structure problems found. Your sentences were complete and well formed.'));
      return box;
    }
    issues.forEach((i) => {
      const card = el('div', 'issue');
      const pair = el('div', 'pair');
      const before = el('div', 'before'); before.appendChild(el('span', 'tag', 'You said')); before.appendChild(el('p', '', i.original));
      const after = el('div', 'after'); after.appendChild(el('span', 'tag', 'Try')); after.appendChild(el('p', '', i.suggestion));
      pair.appendChild(before); pair.appendChild(after);
      card.appendChild(pair);
      const why = el('p', 'why');
      if (i.kind) why.appendChild(el('span', 'kind', i.kind));
      if (i.note) why.appendChild(document.createTextNode(` ${i.note}`));
      card.appendChild(why);
      box.appendChild(card);
    });
    return box;
  }

  function deliveryChips(d) {
    const box = el('div');
    if (!d || !d.words) return box;
    const chips = el('div', 'delivery');
    chips.appendChild(el('span', 'meter', `${d.words} words`));
    chips.appendChild(el('span', 'meter', `≈ ${d.speaking_seconds}s spoken`));
    chips.appendChild(el('span', 'meter', `${d.avg_sentence_words} words per sentence`));
    const fillers = Object.entries(d.fillers || {});
    chips.appendChild(fillers.length
      ? el('span', 'meter', `Filler words: ${fillers.map(([w, n]) => `${w} ×${n}`).join(', ')}`)
      : el('span', 'meter ok', 'No filler words'));
    box.appendChild(chips);
    box.appendChild(el('p', 'hint', d.pace));
    return box;
  }

  // ── one answer's feedback ──
  function feedback(ev) {
    const root = el('div');
    const grid = el('div', 'feedback-grid');
    const score = el('div', 'score-box');
    score.appendChild(ring(ev.overall));
    score.appendChild(el('div', `chip ${ev.overall >= 6 ? '' : 'plain'}`, verdict(ev.overall)));
    score.appendChild(el('div', 'muted small', 'Overall for this answer'));
    grid.appendChild(score);
    grid.appendChild(skillBars(ev.scores));
    root.appendChild(grid);

    root.appendChild(el('p', 'feedback-text', ev.feedback));
    const lists = el('div', 'lists');
    const worked = el('div'); worked.appendChild(el('h3', '', '👍 What worked')); worked.appendChild(bullets(ev.strengths, 'Nothing stood out yet. Focus on the fixes.'));
    const fix = el('div'); fix.appendChild(el('h3', '', '🛠 Improve next time')); fix.appendChild(bullets(ev.improvements, 'Nothing major to fix here.'));
    lists.appendChild(worked); lists.appendChild(fix);
    root.appendChild(lists);

    root.appendChild(el('hr', 'rule'));
    root.appendChild(grammarSection(ev));
    root.appendChild(deliveryChips(ev.delivery));

    const sample = el('details', 'sample');
    sample.appendChild(el('summary', '', 'See a strong sample answer'));
    sample.appendChild(el('p', '', ev.sample_answer || 'No sample answer was provided.'));
    root.appendChild(sample);
    return root;
  }

  // ── full report ──
  function report(state, { signedIn = false, onSave = null } = {}) {
    const r = state.report;
    const root = el('div');

    const head = el('div', 'card report-head');
    head.appendChild(ring(r.overall));
    const grow = el('div', 'grow');
    grow.appendChild(el('span', 'eyebrow', 'Interview report'));
    grow.appendChild(el('h1', '', `${state.role} · ${state.level}`));
    grow.appendChild(el('p', 'muted small', `${state.total} questions · ${state.provider.name}${state.finished_at ? ` · ${fmtDate(state.finished_at)}` : ''}`));
    if (r.summary_degraded) grow.appendChild(el('div', 'alert warn', 'The written summary could not be generated, so this one is based on your scores.'));
    grow.appendChild(el('p', '', r.summary));
    const chips = el('div', 'chips');
    chips.appendChild(el('span', `chip ${r.grammar_issue_count ? 'plain' : ''}`, `✍️ ${r.grammar_issue_count || 0} grammar point${r.grammar_issue_count === 1 ? '' : 's'}`));
    chips.appendChild(el('span', 'chip plain', `🗣 ${r.filler_total || 0} filler word${r.filler_total === 1 ? '' : 's'}`));
    grow.appendChild(chips);
    head.appendChild(grow);
    root.appendChild(head);

    if (!state.saved) {
      const banner = el('div', 'card save-banner no-print');
      const text = el('div');
      text.appendChild(el('h3', '', 'Save this report to your profile'));
      text.appendChild(el('p', 'muted', 'Track your scores over time and see which skills are improving.'));
      banner.appendChild(text);
      if (signedIn && onSave) {
        const btn = el('button', 'btn primary', 'Save to my profile');
        btn.type = 'button';
        btn.addEventListener('click', () => onSave(btn));
        banner.appendChild(btn);
      } else {
        const actions = el('div', 'chips');
        [['Create free account', `/register?next=${encodeURIComponent(location.pathname)}&save=1`, 'btn primary'],
         ['Sign in', `/login?next=${encodeURIComponent(location.pathname)}&save=1`, 'btn']].forEach(([label, href, cls]) => {
          const a = el('a', cls, label); a.href = href; actions.appendChild(a);
        });
        banner.appendChild(actions);
      }
      root.appendChild(banner);
    }

    const skills = el('div', 'card');
    skills.appendChild(el('h3', '', 'Your skill profile'));
    const wrap = el('div', 'radar-wrap');
    wrap.appendChild(radar(r.by_dimension));
    wrap.appendChild(skillBars(r.by_dimension));
    skills.appendChild(wrap);
    root.appendChild(skills);

    const two = el('div', 'grid-2');
    const s = el('div', 'card'); s.appendChild(el('h3', '', '💪 Strengths')); s.appendChild(bullets(r.strengths, 'Complete a few more answers to reveal clear strengths.'));
    const w = el('div', 'card'); w.appendChild(el('h3', '', '🎯 Work on')); w.appendChild(bullets(r.weaknesses, 'No major weak spots. Nice work.'));
    two.appendChild(s); two.appendChild(w);
    root.appendChild(two);

    const plan = el('div', 'card');
    plan.appendChild(el('h3', '', '📅 Your practice plan'));
    const ol = el('ol', 'plan');
    r.practice_plan.forEach((p) => { const li = el('li'); li.appendChild(el('strong', '', p.focus)); li.appendChild(document.createTextNode(p.action)); ol.appendChild(li); });
    plan.appendChild(ol);
    root.appendChild(plan);

    const review = el('div', 'card review');
    review.appendChild(el('h3', '', 'Question by question'));
    state.history.forEach((h) => {
      const d = el('details');
      const sum = el('summary');
      sum.appendChild(ring(h.evaluation.overall, { small: true }));
      const t = el('span'); t.appendChild(document.createTextNode(`${h.index}. ${h.question}`)); t.appendChild(el('br')); t.appendChild(el('span', 'muted small', h.topic));
      sum.appendChild(t);
      sum.appendChild(el('span', `score ${tone(h.evaluation.overall)}`, `${h.evaluation.overall}/10`));
      d.appendChild(sum);
      d.appendChild(el('div', 'answer-text', h.answer));
      d.appendChild(feedback(h.evaluation));
      review.appendChild(d);
    });
    root.appendChild(review);
    return root;
  }

  window.SS.render = { ring, skillBars, radar, lineChart, feedback, report, bullets };
})();