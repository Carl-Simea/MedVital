// Live link from the spacecraft hub to the 3D body. Active only when opened as /body/?astronaut=<id>
// (the MedVital station links here). Without that parameter the dashboard works on its own, as before.
const id = new URLSearchParams(location.search).get('astronaut');

async function waitForApi() {
  for (let i = 0; i < 200 && !window.AstroBody; i++) await new Promise(r => setTimeout(r, 100));
  return window.AstroBody;
}

async function pull(api) {
  try {
    const r = await fetch(`/hub/body/${encodeURIComponent(id)}`, { cache: 'no-store' });
    if (!r.ok) return;
    const d = await r.json();
    const name = document.getElementById('crewName');
    if (name && document.activeElement !== name) name.value = d.name;
    api.setMeasurements(d.measurements);
    const env = [];
    if (d.alert && d.alert.status === 'active' && d.alert.code !== 'INFO') env.push({ text: `${d.alert.code}: ${d.alert.message}`, note: 'Spacecraft alert' });
    env.push({ text: 'Live data from the spacecraft hub', note: 'Every 5 s' });
    api.setEnvironment(env);
  } catch (e) { /* hub restarting: keep the last values */ }
}

if (id) {
  waitForApi().then(api => { if (!api) return; pull(api); setInterval(() => pull(api), 5000); });
}
