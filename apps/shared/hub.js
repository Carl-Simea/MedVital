// Tiny helpers shared by the MedVital apps. Everything talks to the spacecraft hub on the same origin.
export async function api(path, body, method) {
  const opts = { cache: "no-store", method: method || (body === undefined ? "GET" : "POST") };
  if (body !== undefined) { opts.body = JSON.stringify(body); opts.headers = { "Content-Type": "application/json" }; }
  const r = await fetch(path, opts);
  let data = null;
  try { data = await r.json(); } catch { /* empty body */ }
  if (!r.ok) { const e = new Error((data && (data.error || data.detail)) || `HTTP ${r.status}`); e.status = r.status; e.data = data; throw e; }
  return data;
}

export function el(tag, cls, text) {
  const n = document.createElement(tag);
  if (cls) n.className = cls;
  if (text !== undefined && text !== null) n.textContent = text;   // textContent: data can never inject HTML
  return n;
}

export const clock = (t) => new Date(t).toLocaleTimeString([], { hour: "2-digit", minute: "2-digit", second: "2-digit" });

// Line chart on a canvas: values plus an optional shaded band (the astronaut's personal range).
export function spark(canvas, values, { color = "#333", band = null, min = null, max = null, baseline = null } = {}) {
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth, h = canvas.clientHeight;
  if (!w || !h) return;
  canvas.width = w * dpr; canvas.height = h * dpr;
  const g = canvas.getContext("2d");
  g.scale(dpr, dpr);
  g.clearRect(0, 0, w, h);
  const pts = values.filter((v) => v !== null && Number.isFinite(v));
  if (!pts.length) return;
  let lo = min ?? Math.min(...pts, band ? band[0] : Infinity, baseline ?? Infinity);
  let hi = max ?? Math.max(...pts, band ? band[1] : -Infinity, baseline ?? -Infinity);
  if (hi - lo < 1e-6) { hi += 1; lo -= 1; }
  const pad = (hi - lo) * 0.12; lo -= pad; hi += pad;
  const y = (v) => h - ((v - lo) / (hi - lo)) * h;
  const x = (i) => (values.length < 2 ? w : (i / (values.length - 1)) * w);
  if (band) {
    g.fillStyle = color + "1f";
    g.fillRect(0, y(band[1]), w, y(band[0]) - y(band[1]));
  }
  if (baseline !== null) {
    g.strokeStyle = color + "88"; g.setLineDash([4, 4]); g.lineWidth = 1;
    g.beginPath(); g.moveTo(0, y(baseline)); g.lineTo(w, y(baseline)); g.stroke(); g.setLineDash([]);
  }
  g.strokeStyle = color; g.lineWidth = 2.25; g.lineJoin = "round";
  g.beginPath();
  let started = false;
  values.forEach((v, i) => {
    if (v === null || !Number.isFinite(v)) { started = false; return; }
    if (!started) { g.moveTo(x(i), y(v)); started = true; } else g.lineTo(x(i), y(v));
  });
  g.stroke();
  const last = values.length - 1;
  if (values[last] !== null && Number.isFinite(values[last])) {
    g.fillStyle = color; g.beginPath(); g.arc(x(last) - 3, y(values[last]), 4, 0, Math.PI * 2); g.fill();
  }
}
