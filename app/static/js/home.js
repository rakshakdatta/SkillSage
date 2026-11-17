(() => {
  const { $, api, post } = window.SS;
  const form = $('setup-form');
  const errorBox = $('setup-error');
  const startBtn = $('start');
  const fileInput = $('resume-file');
  const resumeText = $('resume-text');
  const resumeStatus = $('resume-status');
  const roleInput = $('role');

  const showError = (msg) => { errorBox.textContent = msg; errorBox.hidden = !msg; };

  // defaults from the signed-in user's profile
  if (form.dataset.defaultRole) roleInput.value = form.dataset.defaultRole;
  const level = form.querySelector(`input[name="level"][value="${form.dataset.defaultLevel}"]`);
  if (level) level.checked = true;

  $('role-chips').addEventListener('click', (e) => {
    const chip = e.target.closest('[data-role]');
    if (chip) { roleInput.value = chip.dataset.role; roleInput.focus(); }
  });

  fileInput.addEventListener('change', async () => {
    const file = fileInput.files[0];
    if (!file) return;
    resumeStatus.textContent = 'Reading your resume…';
    const body = new FormData();
    body.append('file', file);
    try {
      const data = await api('/api/resume', { method: 'POST', body });
      resumeText.value = data.text;
      resumeStatus.textContent = `Read ${data.characters.toLocaleString()} characters. Emails, phone numbers and links were removed. You can edit the text.`;
    } catch (err) {
      resumeStatus.textContent = '';
      showError(err.message);
      fileInput.value = '';
    }
  });

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    showError('');
    const role = roleInput.value.trim();
    if (role.length < 2) { showError('Enter the role you are interviewing for.'); roleInput.focus(); return; }

    startBtn.disabled = true;
    startBtn.textContent = 'Preparing your interview…';
    try {
      const session = await post('/api/sessions', {
        role,
        level: form.querySelector('input[name="level"]:checked').value,
        total: Number(form.querySelector('input[name="total"]:checked').value),
        resume_text: resumeText.value,
      });
      window.location.assign(`/interview/${session.id}`);
    } catch (err) {
      showError(err.message);
      startBtn.disabled = false;
      startBtn.textContent = 'Start interview →';
    }
  });
})();