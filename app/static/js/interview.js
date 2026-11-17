(() => {
  const { $, el, api, post, toast } = window.SS;
  const sessionId = document.body.dataset.sessionId;
  const maxAnswer = Number(document.body.dataset.maxAnswer || 4000);
  const signedIn = document.body.dataset.signedIn === 'true';
  const WPM = 130;

  let state = null;

  const show = (...ids) => ['loading', 'fatal', 'interview', 'report', 'question-card', 'thinking', 'feedback-card']
    .forEach((id) => { $(id).hidden = !ids.includes(id); });

  function renderStepper(s, currentIndex) {
    const box = $('stepper');
    box.replaceChildren();
    for (let i = 1; i <= s.total; i += 1) {
      const done = i <= s.answered;
      const dot = el('span', `dot${done ? ' done' : ''}${i === currentIndex ? ' current' : ''}`, done ? '✓' : String(i));
      box.appendChild(dot);
      if (i < s.total) box.appendChild(el('span', `bar${i <= s.answered ? ' done' : ''}`));
    }
  }

  function updateMeters() {
    const text = $('answer').value;
    const words = (text.trim().match(/\S+/g) || []).length;
    const seconds = Math.round((words / WPM) * 60);
    $('m-words').textContent = `${words} word${words === 1 ? '' : 's'}`;
    $('m-words').className = `meter${words >= 40 ? ' ok' : ''}`;
    $('m-time').textContent = `≈ ${seconds}s spoken`;
    $('m-time').className = `meter${seconds >= 30 && seconds <= 120 ? ' ok' : ''}`;
  }

  function showQuestion(s) {
    const q = s.current_question;
    $('role-label').textContent = `${s.role} · ${s.level}`;
    $('progress-label').textContent = `Question ${q.index} of ${s.total}`;
    renderStepper(s, q.index);
    $('q-topic').textContent = q.topic;
    $('q-text').textContent = q.text;
    $('answer').value = '';
    updateMeters();
    $('answer-error').hidden = true;
    $('submit').disabled = false;
    show('interview', 'question-card');
    $('answer').focus();
  }

  function showFeedback(result) {
    state = result;
    renderStepper(result, 0);
    $('feedback-body').replaceChildren(window.SS.render.feedback(result.evaluation));
    $('fb-progress').textContent = `${result.answered} of ${result.total} answered`;
    $('next').textContent = result.finished ? 'See my report →' : 'Next question →';
    show('interview', 'feedback-card');
    $('feedback-card').scrollIntoView({ behavior: 'smooth', block: 'start' });
    $('next').focus({ preventScroll: true });
  }

  async function save(btn) {
    if (btn) { btn.disabled = true; btn.textContent = 'Saving…'; }
    try {
      state = await post(`/api/sessions/${sessionId}/save`);
      toast('Saved to your profile');
      showReport(state);
    } catch (err) {
      toast(err.message, 'error');
      if (btn) { btn.disabled = false; btn.textContent = 'Save to my profile'; }
    }
  }

  function showReport(s) {
    $('report-root').replaceChildren(window.SS.render.report(s, { signedIn, onSave: save }));
    show('report');
    window.scrollTo({ top: 0 });
  }

  async function submit() {
    const answer = $('answer').value.trim();
    const err = $('answer-error');
    err.hidden = true;
    if (!answer) { err.textContent = 'Write an answer before submitting.'; err.hidden = false; $('answer').focus(); return; }
    $('submit').disabled = true;
    show('interview', 'thinking');
    try {
      showFeedback(await post(`/api/sessions/${sessionId}/answer`, { answer }));
    } catch (e) {
      show('interview', 'question-card');
      err.textContent = e.message;
      err.hidden = false;
      $('submit').disabled = false;
    }
  }

  $('answer').addEventListener('input', updateMeters);
  $('answer').addEventListener('keydown', (e) => { if ((e.ctrlKey || e.metaKey) && e.key === 'Enter') submit(); });
  $('submit').addEventListener('click', submit);
  $('next').addEventListener('click', () => { if (state.finished) showReport(state); else showQuestion(state); });
  $('print').addEventListener('click', () => window.print());
  window.addEventListener('beforeunload', (e) => {
    if (!$('question-card').hidden && $('answer').value.length > 30) { e.preventDefault(); e.returnValue = ''; }
  });

  async function init() {
    try {
      state = await api(`/api/sessions/${sessionId}`);
      const wantsSave = new URLSearchParams(location.search).get('save') === '1';
      if (state.finished && !state.saved && signedIn && wantsSave) { await save(null); return; }
      if (state.finished) showReport(state); else showQuestion(state);
    } catch (e) {
      $('fatal').textContent = `${e.message} `;
      const link = el('a', '', 'Start a new interview');
      link.href = '/';
      $('fatal').appendChild(link);
      show('fatal');
    }
  }
  init();
})();