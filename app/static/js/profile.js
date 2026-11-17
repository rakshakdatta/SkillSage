(() => {
  const { $, el, api, post, patch, del, tone, SKILLS, fmtDate, toast } = window.SS;
  const { ring, skillBars, lineChart } = window.SS.render;

  const TIPS = {
    relevance: 'Open with a one-sentence answer to the exact question, then add detail.',
    depth: 'Add one concrete example with a number from a real project to every answer.',
    clarity: 'Cut filler words and keep sentences short: one idea per sentence.',
    structure: 'Use a simple shape: answer, two supporting points, a closing line. Use STAR for stories.',
    grammar: 'Finish each thought in a complete sentence, check verb agreement and tense, and avoid long chains of "and".',
  };

  const empty = (icon, title, text, cta) => {
    const box = el('div', 'empty');
    box.appendChild(el('div', 'big', icon));
    box.appendChild(el('strong', '', title));
    box.appendChild(el('p', '', text));
    if (cta) { const a = el('a', 'btn primary', cta[0]); a.href = cta[1]; box.appendChild(a); }
    return box;
  };

  function tile(label, value, extra) {
    const t = el('div', 'tile');
    t.appendChild(el('div', 'label', label));
    t.appendChild(el('div', 'value', value));
    if (extra) t.appendChild(extra);
    return t;
  }

  function renderTiles(stats) {
    const tiles = $('tiles');
    tiles.replaceChildren();
    tiles.appendChild(tile('Interviews completed', String(stats.completed),
      stats.in_progress ? el('div', 'delta muted', `${stats.in_progress} unfinished`) : null));
    const avg = tile('Average score', stats.average === null ? '–' : `${stats.average}`);
    if (stats.average !== null) avg.querySelector('.value').classList.add(tone(stats.average));
    tiles.appendChild(avg);
    tiles.appendChild(tile('Best score', stats.best === null ? '–' : `${stats.best}`));
    let delta = null;
    if (stats.change !== null) {
      const up = stats.change > 0;
      delta = el('div', `delta ${stats.change === 0 ? 'muted' : up ? 'good' : 'bad'}`,
        `${up ? '▲' : stats.change < 0 ? '▼' : '■'} ${Math.abs(stats.change)} ${stats.completed >= 4 ? 'vs earlier' : 'since first'}`);
    }
    tiles.appendChild(tile('Latest score', stats.latest === null ? '–' : `${stats.latest}`, delta));
  }

  function renderHistory(list) {
    const box = $('history');
    box.replaceChildren();
    if (!list.length) {
      box.appendChild(empty('🎤', 'No interviews yet', 'Complete your first mock interview and it will appear here.', ['Start an interview', '/']));
      return;
    }
    const table = el('table', 'history');
    const head = el('tr');
    ['Date', 'Role', 'Level', 'Questions', 'Score', 'Status', ''].forEach((h) => head.appendChild(el('th', '', h)));
    const thead = el('thead'); thead.appendChild(head); table.appendChild(thead);
    const tbody = el('tbody');
    list.forEach((i) => {
      const tr = el('tr');
      tr.appendChild(el('td', '', fmtDate(i.finished_at || i.started_at)));
      tr.appendChild(el('td', '', i.role));
      tr.appendChild(el('td', 'cap', i.level));
      tr.appendChild(el('td', '', `${i.answered}/${i.total}`));
      const scoreCell = el('td'); if (i.overall !== null) scoreCell.appendChild(ring(i.overall, { small: true })); else scoreCell.textContent = '–';
      tr.appendChild(scoreCell);
      tr.appendChild(el('td')).appendChild(el('span', `status ${i.status}`, i.status === 'completed' ? 'Completed' : 'Unfinished'));
      const action = el('td');
      if (i.status === 'completed') { const a = el('a', 'btn small', 'View report'); a.href = `/history/${i.id}`; action.appendChild(a); }
      tr.appendChild(action);
      tbody.appendChild(tr);
    });
    table.appendChild(tbody);
    box.appendChild(table);
  }

  const levelWord = (n) => (n >= 8 ? 'Advanced' : n >= 6 ? 'Intermediate' : 'Beginner');

  function skillCards(skills) {
    const grid = el('div', 'skill-cards');
    Object.keys(SKILLS).forEach((key) => {
      if (skills[key] === undefined) return;
      const v = skills[key];
      const card = el('div', 'sc');
      const head = el('div', 'sc-head');
      head.appendChild(el('span', '', SKILLS[key].icon));
      head.appendChild(el('span', '', SKILLS[key].label));
      card.appendChild(head);
      card.appendChild(el('span', `lvl ${tone(v)}`, levelWord(v)));
      card.appendChild(el('div', `pct ${tone(v)}`, `${Math.round(v * 10)}%`));
      const rail = el('div', 'rail');
      const fill = el('i', tone(v));
      fill.style.width = `${Math.max(4, v * 10)}%`;
      rail.appendChild(fill);
      card.appendChild(rail);
      grid.appendChild(card);
    });
    return grid;
  }

  function renderBanner(stats) {
    if (stats.average === null) return;
    $('b-avg').textContent = `${Math.round(stats.average * 10)}%`;
    $('b-bar').style.width = `${Math.round(stats.average * 10)}%`;
    $('banner-sub').textContent = 'Overall skill score across your completed interviews.';
    $('b-delta').textContent = stats.change === null ? `${stats.completed} interview${stats.completed === 1 ? '' : 's'}`
      : `${stats.change > 0 ? '▲ +' : stats.change < 0 ? '▼ ' : '■ '}${stats.change} ${stats.completed >= 4 ? 'vs earlier' : 'since first'}`;
  }

  function render(data) {
    const { user, stats, recent } = data;
    $('p-name').textContent = user.name;
    $('p-first').textContent = user.name.split(' ')[0];
    $('p-meta').textContent = user.email;
    $('k-role').textContent = user.target_role || 'Not set';
    $('k-level').textContent = user.level;
    $('k-since').textContent = fmtDate(user.created_at);
    renderBanner(stats);
    $('f-name').value = user.name;
    $('f-role').value = user.target_role;
    $('f-level').value = user.level;

    renderTiles(stats);

    const trend = $('trend');
    trend.replaceChildren();
    if (stats.trend.length) { trend.appendChild(lineChart(stats.trend)); $('trend-note').textContent = `Last ${stats.trend.length} interview${stats.trend.length === 1 ? '' : 's'}`; }
    else trend.appendChild(empty('📈', 'Your progress will show here', 'Finish an interview to see your first score.'));

    const skills = $('skills'); const focus = $('focus'); const ready = $('ready');
    skills.replaceChildren(); focus.replaceChildren(); ready.replaceChildren();
    if (Object.keys(stats.skills).length) {
      skills.appendChild(skillCards(stats.skills));
      const row = el('div', 'ready');
      row.appendChild(ring(stats.average === null ? 0 : stats.average, { label: stats.average >= 8 ? 'Ready' : 'Getting there' }));
      row.appendChild(skillBars(stats.skills));
      ready.appendChild(row);
      const weak = stats.weakest;
      const note = el('div', 'alert info');
      note.appendChild(el('strong', '', `Focus on ${SKILLS[weak].icon} ${SKILLS[weak].label}`));
      note.appendChild(el('br'));
      note.appendChild(document.createTextNode(TIPS[weak]));
      focus.appendChild(note);
    } else skills.appendChild(empty('🧠', 'No skill data yet', 'Skill averages appear after your first completed interview.'));

    renderHistory(recent);
  }

  const showErr = (id, msg) => { $(id).textContent = msg; $(id).hidden = !msg; };

  $('profile-form').addEventListener('submit', async (e) => {
    e.preventDefault(); showErr('profile-error', '');
    try {
      const { user } = await patch('/api/profile', { name: $('f-name').value, target_role: $('f-role').value, level: $('f-level').value });
      $('p-name').textContent = user.name;
      toast('Profile saved');
    } catch (err) { showErr('profile-error', err.message); }
  });

  $('password-form').addEventListener('submit', async (e) => {
    e.preventDefault(); showErr('password-error', '');
    try {
      await post('/api/profile/password', { current_password: $('pw-current').value, new_password: $('pw-new').value });
      $('password-form').reset();
      toast('Password updated');
    } catch (err) { showErr('password-error', err.message); }
  });

  const dialog = $('delete-dialog');
  $('delete-open').addEventListener('click', () => { $('delete-password').value = ''; showErr('delete-error', ''); dialog.showModal(); $('delete-password').focus(); });
  $('delete-cancel').addEventListener('click', () => dialog.close());
  $('delete-form').addEventListener('submit', async (e) => {
    e.preventDefault(); showErr('delete-error', '');
    try { await del('/api/profile', { password: $('delete-password').value }); window.location.assign('/'); }
    catch (err) { showErr('delete-error', err.message); }
  });

  api('/api/profile').then(render).catch((err) => {
    if (err.status === 401) window.location.assign('/login?next=/profile');
    else toast(err.message, 'error');
  });
})();