document.addEventListener('DOMContentLoaded', () => {
  const form = document.getElementById('loginForm');
  const userInput = document.getElementById('username');
  const passInput = document.getElementById('password');
  const errorMsg = document.getElementById('errorMsg');
  const presetPills = document.querySelectorAll('.preset-pill');

  const presets = {
    'admin': { user: 'admin', pass: 'admin2026' },
    'bob': { user: 'bob', pass: 'quantum2026' },
    'charlie': { user: 'charlie', pass: 'quantum2026' }
  };

  presetPills.forEach(pill => {
    pill.addEventListener('click', () => {
      presetPills.forEach(p => p.classList.remove('active'));
      pill.classList.add('active');
      const role = pill.dataset.role;
      if (presets[role]) {
        userInput.value = presets[role].user;
        passInput.value = presets[role].pass;
      }
    });
  });

  form.addEventListener('submit', async (e) => {
    e.preventDefault();
    errorMsg.style.display = 'none';

    try {
      const res = await fetch('/api/login', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          username: userInput.value,
          password: passInput.value
        })
      });

      if (!res.ok) {
        throw new Error('Authentication failed: Invalid credentials');
      }

      const data = await res.json();
      sessionStorage.setItem('hedwig_user', JSON.stringify(data));
      window.location.href = data.redirect_url;
    } catch (err) {
      errorMsg.textContent = err.message || 'Login failed. Check credentials.';
      errorMsg.style.display = 'block';
    }
  });
});
