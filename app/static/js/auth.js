(() => {
  const { $, post } = window.SS;
  const mode = document.body.dataset.mode;
  const form = $('auth-form');
  const errorBox = $('auth-error');
  const submit = $('auth-submit');
  const params = new URLSearchParams(location.search);

  const showError = (msg) => { errorBox.textContent = msg; errorBox.hidden = !msg; };

  // Only follow a redirect that stays on this site.
  function destination() {
    const next = params.get('next') || '/profile';
    if (!next.startsWith('/') || next.startsWith('//') || next.includes('\\')) return '/profile';
    return params.get('save') === '1' ? `${next}${next.includes('?') ? '&' : '?'}save=1` : next;
  }

  $('pw-toggle').addEventListener('click', () => {
    const input = $('password');
    const hidden = input.type === 'password';
    input.type = hidden ? 'text' : 'password';
    $('pw-toggle').textContent = hidden ? 'Hide' : 'Show';
    $('pw-toggle').setAttribute('aria-label', hidden ? 'Hide password' : 'Show password');
  });

  if (mode === 'register') {
    $('password').addEventListener('input', () => {
      const v = $('password').value;
      let score = 0;
      if (v.length >= 8) score += 1;
      if (v.length >= 12) score += 1;
      if (/[a-z]/.test(v) && /[A-Z]/.test(v)) score += 1;
      if (/\d/.test(v)) score += 1;
      if (/[^A-Za-z0-9]/.test(v)) score += 1;
      const bar = $('pw-meter-bar');
      bar.style.width = `${(score / 5) * 100}%`;
      bar.style.background = score >= 4 ? 'var(--good)' : score >= 3 ? 'var(--mid)' : 'var(--bad)';
      $('pw-hint').textContent = !v ? 'Use at least 8 characters. A short sentence works well.'
        : v.length < 8 ? 'Too short. Use at least 8 characters.' : score >= 4 ? 'Strong password.' : 'Okay. A longer password is stronger.';
    });
  }

  form.addEventListener('submit', async (event) => {
    event.preventDefault();
    showError('');
    const email = $('email').value.trim();
    const password = $('password').value;
    const name = mode === 'register' ? $('name').value.trim() : '';
    if (mode === 'register' && !name) { showError('Enter your name.'); $('name').focus(); return; }
    if (!/^[^@\s]+@[^@\s]+\.[^@\s]{2,}$/.test(email)) { showError('Enter a valid email address.'); $('email').focus(); return; }
    if (password.length < 8) { showError('Your password needs at least 8 characters.'); $('password').focus(); return; }

    submit.disabled = true;
    const label = submit.textContent;
    submit.textContent = mode === 'register' ? 'Creating your account…' : 'Signing in…';
    try {
      await post(mode === 'register' ? '/api/auth/register' : '/api/auth/login', mode === 'register' ? { name, email, password } : { email, password });
      window.location.assign(destination());
    } catch (err) {
      showError(err.message);
      submit.disabled = false;
      submit.textContent = label;
    }
  });
})();