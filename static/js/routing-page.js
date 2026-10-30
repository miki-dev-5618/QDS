/* Dedicated multi-hop routing page: live updates plus the link reset. Rendering lives in routing.js. */
document.addEventListener('DOMContentLoaded', () => {
  connectSocket('admin', msg => {
    if (msg.event === 'init_sync') renderLinks(msg.data.channel_state);
    else if (msg.event === 'new_transmission') { renderQubitFlow(msg.data.transmission, true); refreshTopology(); }
    else if (msg.event === 'channel_state') refreshTopology();
  }, online => setConnectionBadge(online, 'ONLINE'));
  document.getElementById('btnResetLinks').addEventListener('click', resetLinks);
  refreshTopology();
  loadLatestFlow();
});

async function resetLinks() {
  const message = document.getElementById('routingMessage');
  try {
    const { data } = await api('/api/channel/reset', {
      method: 'POST', headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify({ reason: document.getElementById('routingReason').value })
    }, 'admin');
    const n = (data.transitions || []).length;
    message.textContent = n
      ? `${n} link(s) reset: quarantined → probation, watch → open. Signed reset record #${data.reset_record.chain_seq}.`
      : 'No link needed a reset.';
    refreshTopology();
  } catch (err) {
    message.textContent = `Reset failed: ${err.message}`;
  }
}
