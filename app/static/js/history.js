(() => {
  const { $, api, el } = window.SS;
  const id = document.body.dataset.interviewId;

  api(`/api/history/${id}`).then((state) => {
    $('loading').hidden = true;
    if (!state.finished || !state.report) {
      $('fatal').textContent = 'This interview was not finished, so there is no report to show.';
      $('fatal').hidden = false;
      return;
    }
    $('report-root').replaceChildren(window.SS.render.report(state, { signedIn: true }));
    $('actions').hidden = false;
    $('print').addEventListener('click', () => window.print());
  }).catch((err) => {
    $('loading').hidden = true;
    if (err.status === 401) { window.location.assign(`/login?next=/history/${id}`); return; }
    $('fatal').textContent = `${err.message} `;
    const link = el('a', '', 'Back to my progress');
    link.href = '/profile';
    $('fatal').appendChild(link);
    $('fatal').hidden = false;
  });
})();