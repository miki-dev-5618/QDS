document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('loginForm');
  const userInput = document.getElementById('username');
  const passInput = document.getElementById('password');
  const errorMsg = document.getElementById('errorMsg');
  const presetPills = document.querySelectorAll('.preset-pill');
  const params = new URLSearchParams(window.location.search);

  // Demo presets are only rendered by the server when built-in demo credentials are active.
  const presets = {
    admin: { user: 'admin', pass: 'admin2026' },
    bob: { user: 'bob', pass: 'quantum2026' },
    charlie: { user: 'charlie', pass: 'quantum2026' }
  };

  function selectPreset(role) {
    presetPills.forEach(p => {
      p.classList.toggle('active', p.dataset.role === role);
      p.setAttribute('aria-pressed', String(p.dataset.role === role));
    });
    if (presetPills.length && presets[role]) {
      userInput.value = presets[role].user;
      passInput.value = presets[role].pass;
    }
  }

  presetPills.forEach(pill => pill.addEventListener('click', () => selectPreset(pill.dataset.role)));
  if (params.get('role')) selectPreset(params.get('role'));

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorMsg.style.display = 'none';
    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        credentials: 'same-origin',
        body: JSON.stringify({ username: userInput.value, password: passInput.value })
      });
      if (!res.ok) throw new Error('Authentication failed: invalid credentials');
      const data = await res.json();
      const next = params.get('next');
      // Only follow `next` to this role's own page (same-origin path).
      window.location.href = (next && next === data.redirect_url) ? next : data.redirect_url;
    } catch (err) {
      errorMsg.textContent = err.message || 'Login failed. Check credentials.';
      errorMsg.style.display = 'block';
    }
  });
});
