// Bob-only control: act as a dishonest verifier and forward a forged signature to Charlie.
document.addEventListener('DOMContentLoaded', () => {
  const btn = document.getElementById('btnDishonestForward');
  if (!btn) return;
  const label = btn.innerHTML;

  btn.addEventListener('click', async () => {
    btn.disabled = true;
    btn.textContent = 'Forging from Bob\'s own records and forwarding to Charlie...';
    try {
      const { status, data } = await api('/api/dishonest-bob-forward', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({})
      }, 'bob');
      if (status === 423) alert(`Forward link quarantined: ${data.detail.reason}. Ask the admin to reset it.`);
    } catch (err) {
      alert(err.message);
    } finally {
      btn.disabled = false;
      btn.innerHTML = label;
    }
  });
});
