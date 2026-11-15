// Spacecraft hub screen: the network as a tree. NASA sits outside, above Cloudflare. Inside Cloudflare: the Worker
// with its D1 database, DONKI space weather and the checker; inside that, the private network, the spacecraft hub,
// the onboard AI agent and every astronaut's wearable. Every moving dot is real traffic from the hub's log; its colour
// says which hop it is on (legend under the drawing). Click any box to open it in the side panel.
import { api, el, clock } from "/apps/shared/hub.js";

const $ = (id) => document.getElementById(id);
const SVG = "http://www.w3.org/2000/svg";

// Okabe-Ito colours: tell apart for colour-blind viewers too. Red is kept for "down" only.
const COLORS = {
  reading: { c: "#56B4E9", label: "Astronaut → spacecraft hub: wearable readings, every second" },
  cloud: { c: "#E69F00", label: "Spacecraft hub → Cloudflare: day-end batch and urgent alerts" },
  nasa: { c: "#009E73", label: "Cloudflare → NASA: records NASA receives" },
  check: { c: "#CC79A7", label: "Cloudflare checker: goes round and checks every part" },
  ask: { c: "#F0E442", label: "A question to the AI: astronaut → hub → onboard agent → back" },
  donki: { c: "#C9B8FF", label: "DONKI → Cloudflare: NASA space weather" },
};

// ------------------------------------------------------------------ fixed nodes (astronauts are added from the crew)
const NODES = {
  nasa: { x: 500, y: 58, w: 170, h: 56, title: "NASA", sub: "flight surgeon", cls: "earth" },
  cloudflare: { x: 500, y: 200, w: 240, h: 66, title: "Cloudflare Worker + D1", sub: "link to NASA", cls: "cfnode big" },
  donki: { x: 170, y: 200, w: 180, h: 56, title: "DONKI", sub: "NASA space weather", cls: "cfnode" },
  checker: { x: 820, y: 200, w: 210, h: 66, title: "Cloudflare checker", sub: "Worker + Workers AI", cls: "cfnode checker" },
  net: { x: 500, y: 330, w: 240, h: 56, title: "Private network", sub: "device keys only", cls: "pnode" },
  hub: { x: 500, y: 440, w: 240, h: 66, title: "Spacecraft hub", sub: "rules · database · outbox", cls: "pnode big" },
  agent: { x: 810, y: 440, w: 200, h: 56, title: "Onboard AI agent", sub: "answers questions", cls: "pnode agent" },
  ghost: { x: 180, y: 440, w: 170, h: 44, title: "Unknown devices", sub: "", cls: "ghost" },
};
const EDGES = [["nasa", "cloudflare"], ["donki", "cloudflare"], ["cloudflare", "checker"], ["cloudflare", "net"],
  ["net", "hub"], ["hub", "agent"], ["ghost", "net"]];
const ALIAS = { worker: "hub", d1: "hub", outbox: "hub", tunnel: "net", link: "cloudflare", ai: "checker" };
const nodeEls = {}, edgeEls = {}, routes = {};
let devices = [], selected = "net", status = null, linkUp = null;

function svg(tag, attrs, parent) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  if (parent) parent.append(n);
  return n;
}

function drawNode(id, n) {
  const g = svg("g", { class: `node ${n.cls}`, transform: `translate(${n.x - n.w / 2} ${n.y - n.h / 2})`, tabindex: 0, role: "button",
    "aria-label": n.title }, $("nodes"));
  svg("rect", { width: n.w, height: n.h, rx: 7 }, g);
  const t = svg("text", { x: n.w / 2, y: n.h > 50 ? 25 : 18, class: "t" }, g); t.textContent = n.title;
  const s = svg("text", { x: n.w / 2, y: n.h > 50 ? (n.h > 60 ? 46 : 42) : 33, class: "s" }, g); s.textContent = n.sub;
  const c = svg("text", { x: n.w - 6, y: -8, class: "c", "text-anchor": "end" }, g);   // right-aligned: clear of the lines above
  let led = null;
  if (n.device) led = svg("circle", { cx: 14, cy: 14, r: 6, class: "led offl" }, g);
  g.onclick = g.onkeydown = (e) => { if (e.type === "keydown" && e.key !== "Enter") return; select(id); };
  nodeEls[id] = { g, s, c, led };
}

// Tree routes: vertical drops with elbows, straight lines between boxes on the same row.
function route(a, b) {
  const A = NODES[a], B = NODES[b];
  if (Math.abs(A.y - B.y) < 4) {
    const dir = Math.sign(B.x - A.x);
    return [[A.x + dir * A.w / 2, A.y], [B.x - dir * B.w / 2, B.y]];
  }
  const down = B.y > A.y;
  const ay = A.y + (down ? A.h / 2 : -A.h / 2), by = B.y + (down ? -B.h / 2 : B.h / 2);
  if (Math.abs(A.x - B.x) < 4) return [[A.x, ay], [B.x, by]];
  if (a === "ghost") return [[A.x, A.y - A.h / 2], [A.x, B.y], [B.x - B.w / 2, B.y]];
  const mid = down ? by - 22 : ay - 22;
  return [[A.x, ay], [A.x, mid], [B.x, mid], [B.x, by]];
}
function edge(a, b) {
  const pts = route(a, b);
  routes[a + ">" + b] = pts;
  routes[b + ">" + a] = pts.slice().reverse();
  const l = svg("polyline", { points: pts.map((p) => p.join(",")).join(" "), class: "edge" }, $("edges"));
  edgeEls[a + ">" + b] = l;
  return l;
}
const neighbours = (id) => Object.keys(routes).filter((k) => k.startsWith(id + ">")).map((k) => k.split(">")[1]);
function hops(a, b) {   // shortest path between two boxes over the drawn lines
  if (a === b) return [a];
  const prev = { [a]: null }, q = [a];
  while (q.length) { const x = q.shift(); for (const y of neighbours(x)) if (!(y in prev)) { prev[y] = x; if (y === b) { const out = [b]; let z = b; while (prev[z]) { z = prev[z]; out.unshift(z); } return out; } q.push(y); } }
  return [a, b];
}

function layoutDevices(list) {
  const ids = list.map((d) => d.astronautId).join(",");
  if (ids === layoutDevices.last) return;
  layoutDevices.last = ids;
  for (const id of Object.keys(nodeEls)) if (NODES[id]?.device) { nodeEls[id].g.remove(); delete nodeEls[id]; delete NODES[id]; edgeEls[id + ">hub"]?.remove(); delete edgeEls[id + ">hub"]; delete routes[id + ">hub"]; delete routes["hub>" + id]; }
  const n = list.length, left = 110, right = 890;
  const w = Math.min(160, (right - left) / Math.max(1, n) - 14);
  list.forEach((d, i) => {
    const x = n > 1 ? left + w / 2 + i * ((right - left - w) / (n - 1)) : 500;
    NODES[d.astronautId] = { x, y: 566, w, h: 58, title: d.name.split(" ")[0], sub: "wearable", cls: "astro", device: true };
    edge("hub", d.astronautId);
    drawNode(d.astronautId, NODES[d.astronautId]);
  });
  if (!NODES[selected]) selected = "net";
  markSelected();
}

function setNode(id, { sub, count, cls } = {}) {
  const n = nodeEls[id]; if (!n) return;
  if (sub !== undefined) n.s.textContent = sub;
  if (count !== undefined) n.c.textContent = count;
  if (cls !== undefined) n.g.setAttribute("class", `node ${NODES[id].cls} ${cls}` + (selected === id ? " sel" : ""));
}
function markSelected() { for (const [id, n] of Object.entries(nodeEls)) n.g.classList.toggle("sel", id === selected); }

// ------------------------------------------------------------------ packets
function segColor(a, b, kind) {
  if (kind === "ask") return COLORS.ask.c;
  if (kind === "check") return COLORS.check.c;
  if (kind === "donki") return COLORS.donki.c;
  const pair = [a, b].sort().join("+");
  if (NODES[a]?.device || NODES[b]?.device) return COLORS.reading.c;
  if (pair === "cloudflare+nasa") return COLORS.nasa.c;
  if (pair === "checker+cloudflare") return COLORS.check.c;
  if (pair === "agent+hub") return COLORS.ask.c;
  if (pair === "cloudflare+donki") return COLORS.donki.c;
  return COLORS.cloud.c;
}
function normalise(path) {
  const ids = [];
  for (let p of path) { p = ALIAS[p] || p; if (!NODES[p]) continue; if (ids[ids.length - 1] !== p) ids.push(p); }
  // the wearables attach to the hub; the private network is the zone they sit in
  const out = ids.filter((p, i) => !(p === "net" && (NODES[ids[i - 1]]?.device || NODES[ids[i + 1]]?.device)));
  const full = [];
  for (let i = 0; i < out.length; i++) {
    if (i === 0) { full.push(out[0]); continue; }
    full.push(...hops(out[i - 1], out[i]).slice(1));
  }
  return full;
}
const live = new Set();
function travel(stops, { kind = "", r = 5, cls = "", label = "", speed = 520, onArrive = null, done = null } = {}) {
  if (stops.length < 2) { if (stops[0]) flash(stops[0]); done?.(); return; }
  const g = svg("g", {}, $("packets"));
  const dot = svg("circle", { r, class: "packet " + cls }, g);
  let text = null; if (label) { text = svg("text", { class: "pkt-label", dy: -16 }, g); text.textContent = label; }
  live.add(g);
  let i = 0, seg = routes[stops[0] + ">" + stops[1]] || [[NODES[stops[0]].x, NODES[stops[0]].y], [NODES[stops[1]].x, NODES[stops[1]].y]];
  let j = 0, t0 = null;
  const color = () => segColor(stops[i], stops[i + 1], kind);
  dot.setAttribute("fill", color());
  function step(t) {
    if (t0 === null) t0 = t;
    const [x1, y1] = seg[j], [x2, y2] = seg[j + 1];
    const len = Math.hypot(x2 - x1, y2 - y1) || 1;
    const k = Math.min(1, ((t - t0) / 1000) * speed / len);
    const x = x1 + (x2 - x1) * k, y = y1 + (y2 - y1) * k;
    dot.setAttribute("cx", x); dot.setAttribute("cy", y);
    if (text) { text.setAttribute("x", x); text.setAttribute("y", y); }
    if (k < 1) return requestAnimationFrame(step);
    t0 = null; j += 1;
    if (j < seg.length - 1) return requestAnimationFrame(step);
    onArrive?.(stops[i + 1]);
    i += 1; j = 0;
    if (i < stops.length - 1) { seg = routes[stops[i] + ">" + stops[i + 1]] || [[NODES[stops[i]].x, NODES[stops[i]].y], [NODES[stops[i + 1]].x, NODES[stops[i + 1]].y]]; dot.setAttribute("fill", color()); return requestAnimationFrame(step); }
    flash(stops[stops.length - 1]);
    setTimeout(() => { g.remove(); live.delete(g); done?.(); }, 60);
  }
  requestAnimationFrame(step);
}

function animate(ev) {
  if (ev.kind === "check") return;   // the checker's round is drawn by sweep()
  const path = normalise(ev.path || []);
  if (ev.kind === "burst" && NODES[path[0]]?.device) pulse(path[0]);
  if (live.size > 80 && ev.kind === "burst") return;
  if (ev.status === "blocked") { travel(["ghost", "net"], { cls: "blocked", done: () => cross(NODES.net) }); return; }
  const failed = ev.status === "failed";
  const stops = failed ? path.slice(0, Math.max(2, path.length - 1)) : path;
  const big = ev.kind === "dayend" || ev.kind === "ack";
  travel(stops, { kind: ev.kind, r: big ? 12 : ev.status === "alert" ? 8 : 5, cls: (big ? "batch " : "") + (ev.status === "alert" ? "alert" : ""),
    label: big && ev.count ? `${ev.count} records` : "", speed: big ? 260 : ev.kind === "burst" ? 700 : 480,
    done: failed ? () => cross(NODES[stops[stops.length - 1]]) : null });
}

function pulse(id) {
  const n = NODES[id]; if (!n || !nodeEls[id]) return;
  const ring = svg("circle", { cx: n.x - n.w / 2 + 14, cy: n.y - n.h / 2 + 14, r: 6, class: "pulse" }, $("packets"));
  ring.animate([{ r: 6, opacity: 1 }, { r: 22, opacity: 0 }], { duration: 700, easing: "ease-out" }).onfinish = () => ring.remove();
}
function cross(n) {
  if (!n) return;
  const g = svg("g", {}, $("packets"));
  svg("line", { x1: n.x - 12, y1: n.y - n.h / 2 - 30, x2: n.x + 12, y2: n.y - n.h / 2 - 6, class: "burst-x" }, g);
  svg("line", { x1: n.x + 12, y1: n.y - n.h / 2 - 30, x2: n.x - 12, y2: n.y - n.h / 2 - 6, class: "burst-x" }, g);
  setTimeout(() => g.remove(), 1000);
}
function flash(id) { const n = nodeEls[id]; if (!n) return; n.g.classList.add("hot"); setTimeout(() => n.g.classList.remove("hot"), 200); }
function ring(id, ok) {   // the checker's verdict on one box: green or red ring for a moment
  const n = NODES[id]; if (!n) return;
  const r = svg("rect", { x: n.x - n.w / 2 - 5, y: n.y - n.h / 2 - 5, width: n.w + 10, height: n.h + 10, rx: 10, class: "check-ring " + (ok ? "ok" : "bad") }, $("rings"));
  r.animate([{ opacity: 1 }, { opacity: 0 }], { duration: 1600, easing: "ease-in" }).onfinish = () => r.remove();
}

// The checker goes round every part, using its real latest results.
function partOk(id) {
  const ch = status?.checker, p = ch?.parts; if (!p) return null;
  if (NODES[id]?.device) { const d = (p.devices || []).find((x) => x.id === id); return d ? d.up : null; }
  if (id === "cloudflare") return status.via === "cloudflare" ? ch.ok !== false : null;
  if (id === "nasa") return p.nasa?.up ?? null;
  if (id === "hub") return p.hub?.up ?? null;
  if (id === "agent") return p.agent?.up ?? null;
  if (id === "donki") return p.donki?.up ?? null;
  if (id === "net") return (p.devices || []).some((d) => d.up);
  if (id === "checker") return ch.db?.ok !== false;
  return null;
}
let sweeping = false;
function sweep() {
  if (sweeping || !status?.checker?.parts || document.hidden) return;
  sweeping = true;
  const stops = ["checker", "cloudflare", "nasa", "cloudflare", "donki", "cloudflare", "net", "hub"];
  for (const d of devices) stops.push(d.astronautId, "hub");
  stops.push("agent", "hub", "net", "cloudflare", "checker");
  travel(stops, { kind: "check", r: 6, cls: "checkdot", speed: 1100, onArrive: (id) => { const ok = partOk(id); if (ok !== null) ring(id, ok); },
    done: () => { sweeping = false; ring("checker", status?.checker?.db?.ok !== false); } });
}

// Records that waited in Cloudflare rush to NASA back to back once the link is back.
let nasaSeen = null;
function nasaFlow() {
  const n = status?.checker?.db?.nasa;
  if (typeof n !== "number") return;
  if (nasaSeen === null) { nasaSeen = n; return; }
  const delta = n - nasaSeen; nasaSeen = n;
  if (delta <= 0 || status.via !== "cloudflare") return;
  const dots = Math.min(delta, 30);
  for (let i = 0; i < dots; i++) setTimeout(() => travel(["cloudflare", "nasa"], { r: 5, speed: 300 }), i * 70);
  if (delta > 30) setTimeout(() => travel(["cloudflare", "nasa"], { r: 11, cls: "batch", label: `${delta} records`, speed: 160 }), dots * 70);
}

let since = 0;
const recent = [];
async function pollNetwork() {
  try {
    const events = await api(`/hub/network?since=${since}`);
    for (const ev of events) {
      since = Math.max(since, ev.seq);
      animate(ev);
      recent.unshift(ev); if (recent.length > 400) recent.pop();
    }
  } catch { /* hub restarting */ }
}
function banner(text, ack) {
  const b = $("dayend"); b.textContent = text; b.className = "dayend" + (ack ? " ack" : ""); b.hidden = false;
  clearTimeout(banner.t); banner.t = setTimeout(() => { b.hidden = true; }, 4500);
}

// ------------------------------------------------------------------ retry countdown next to Cloudflare
const cd = (() => {
  const n = NODES.cloudflare;
  const g = svg("g", { class: "countdown", transform: `translate(${n.x + n.w / 2 + 34} ${n.y})` }, $("packets").parentNode);
  svg("circle", { r: 24 }, g);
  const t = svg("text", { class: "cdn", dy: 7 }, g);
  const l = svg("text", { class: "cdl", dy: 42 }, g); l.textContent = "retry";
  g.style.display = "none";
  return { g, t };
})();
let downSince = null;
function drawCountdown() {
  const ch = status?.checker;
  const down = linkUp === false || (ch && ch.link && ch.link.up === false);
  if (!down) { cd.g.style.display = "none"; downSince = null; return; }
  downSince = downSince || Date.now();
  const every = (ch?.link?.retryEveryS) || 3;
  // the last real retry (NASA's pull, or the spacecraft's resend); before the first one, from when the link went down
  const last = ch?.link?.lastNasaTry ? Date.parse(ch.link.lastNasaTry) : downSince;
  const left = every - (((Date.now() - last) / 1000) % every);
  cd.g.style.display = "";
  cd.t.textContent = String(Math.max(1, Math.ceil(left)));
}

// ------------------------------------------------------------------ status: clock, devices, link, checker
let lastReport = null;
async function pollStatus() {
  try {
    const [s, devs, link] = await Promise.all([api("/hub/status"), api("/hub/devices"), api("/hub/link")]);
    status = s; devices = devs;
    const c = s.clock;
    $("clockDay").textContent = `Day ${c.day}`; $("clockTime").textContent = c.time;
    $("clockPhase").textContent = c.phaseLabel + (c.sepActive ? " · solar particle event" : "") + (c.blackout ? " · link blackout" : "");
    $("dayFill").style.width = `${(c.dayFraction * 100).toFixed(1)}%`;
    $("nextSend").textContent = c.blackout ? "Blackout: Earth not in view. Records wait in the outbox."
      : `Next send: end of day ${c.day}, in ${Math.max(0, Math.round(c.secondsToDayEnd))} s. Urgent alerts go right away.`;
    layoutDevices(devs);
    for (const d of devs) {
      const n = nodeEls[d.astronautId]; if (!n) continue;
      n.led.setAttribute("class", "led " + (d.connected ? "on" : "offl"));
      const outside = s.evas && s.evas[d.astronautId];
      const ACT = { asleep: "Sleeping", awake: "Resting", exercise: "Exercising", spacewalk: "Spacewalk" };
      setNode(d.astronautId, { sub: d.connected ? (outside ? "Spacewalk · outside" : ACT[d.state] || d.state || "connected") : d.worn ? "no signal" : "taken off",
        count: "", cls: d.connected ? (outside ? "outside" : "") : "off" });
      edgeEls["hub>" + d.astronautId]?.classList.toggle("off", !d.connected);
    }
    const on = devs.filter((d) => d.connected).length;
    setNode("net", { sub: `${on} of ${devs.length} wearables connected`, count: s.tables.rejected ? `${s.tables.rejected} blocked` : "" });
    setNode("hub", { sub: `database · outbox ${s.outbox}${s.outboxUrgent ? ` (${s.outboxUrgent} urgent)` : ""}` });
    setNode("agent", { sub: s.ai.onboardAgent === "rules" && !s.ai.workersAi ? "rules (no model set)" : (s.ai.onboardAgent !== "rules" ? `Ollama ${s.ai.onboardAgent}` : "via Workers AI") });
    setNode("donki", { sub: s.donki.error ? "unreachable: replay" : s.donki.source === "Cloudflare" ? "fed by Cloudflare" : "NASA CCMC" });
    setNode("ghost", { sub: s.tables.rejected ? `${s.tables.rejected} blocked` : "none yet" });
    drawLink(link, s);
    drawChecker(s);
    nasaFlow();
    const r = s.dayReport;
    if (r && lastReport !== null && r.day !== lastReport) {
      banner(r.delivered ? `Day ${r.day} report sent: ${r.sent} records, ${s.via === "cloudflare" ? "Cloudflare" : "NASA"} confirmed ${r.confirmed}`
        : `Day ${r.day} report waiting on board: link not available`, r.delivered);
    }
    if (r) lastReport = r.day; else if (lastReport === null) lastReport = 0;
  } catch {
    $("linkState").textContent = "Hub unreachable"; $("linkState").className = "link-state down";
  }
}

function drawLink(link, s) {
  const st = $("linkState"), btn = $("linkBtn"), bar = $("alertbar");
  const cf = s.via === "cloudflare";
  const what = cf ? "Link Cloudflare → NASA" : "Link to NASA";
  if (!link.reachable) {
    linkUp = null; st.textContent = cf ? "Cloudflare unreachable" : link.nasaUrl ? "NASA receiver unreachable" : "No NASA receiver configured";
    st.className = "link-state down"; btn.disabled = true; btn.textContent = "…";
    setNode("cloudflare", { cls: "bad", count: "unreachable" }); edgeEls["nasa>cloudflare"].classList.add("down");
    bar.hidden = false; bar.textContent = cf ? "Cloudflare does not answer. Everything stays on board in the outbox and goes when it answers again." : "NASA does not answer. Everything stays on board in the outbox.";
    return;
  }
  linkUp = link.up;
  const down = !link.up;
  st.textContent = link.blackout ? `${what}: up · spacecraft in blackout` : `${what}: ${link.up ? "UP" : "DOWN"}`;
  st.className = "link-state " + (down || link.blackout ? "down" : "up");
  btn.disabled = false; btn.textContent = link.up ? "Cut the link" : "Restore the link"; btn.className = "link-btn " + (link.up ? "cut" : "restore");
  const db = s.checker?.db || {};
  setNode("cloudflare", { sub: cf ? `D1 holds ${db.cloudflare ?? "–"} records` : "not configured: direct link", cls: down ? "bad" : (cf ? "" : "dim"),
    count: down ? "link to NASA down" : "" });
  setNode("nasa", { sub: down ? `waiting · ${cf ? db.waitingAtCloudflare ?? 0 : s.outbox} records held` : `has ${db.nasa ?? "–"} records`, cls: down ? "bad" : "" });
  edgeEls["nasa>cloudflare"].classList.toggle("down", down);
  if (down) {
    bar.hidden = false;
    bar.textContent = cf ? `Link from Cloudflare to NASA is down. ${db.waitingAtCloudflare ?? 0} record(s) waiting safely in Cloudflare. NASA retries every ${s.checker?.link?.retryEveryS ?? 3} s.`
      : `Link to NASA is down. ${s.outbox} record(s) waiting safely in the spacecraft's outbox.`;
  } else bar.hidden = true;
}
$("linkBtn").onclick = async () => { if (linkUp === null) return; $("linkBtn").disabled = true; try { await api("/hub/link", { up: !linkUp }); } catch { /* next poll */ } pollStatus(); };

function drawChecker(s) {
  const ch = s.checker || {};
  if (!ch.via) { setNode("checker", { sub: "starting…" }); return; }
  const ok = ch.ok !== false && ch.db?.ok !== false;
  setNode("checker", { sub: ch.via === "cloudflare" ? (ok ? "all parts checked" : ch.error || "databases differ") : "local check (no Worker)", cls: ok ? "" : "bad",
    count: ch.sentence?.source === "Workers AI" ? "worded by Workers AI" : "" });
}

// ------------------------------------------------------------------ legend
function legend() {
  const ul = $("legend");
  for (const v of Object.values(COLORS)) { const li = el("li"); const i = el("i"); i.style.background = v.c; li.append(i, document.createTextNode(v.label)); ul.append(li); }
  const li = el("li", "down"); li.append(el("i"), document.createTextNode("Red dashed line: link down; records wait and are retried every 3 s")); ul.append(li);
}

// ------------------------------------------------------------------ side panel
function select(id) { selected = id; markSelected(); renderPanel(); }
const kv = (pairs) => { const d = el("div", "kv"); for (const [k, v] of pairs) d.append(el("span", "", k), el("b", "", String(v))); return d; };
function rows(list, fmt) { const ul = el("ul", "rows"); if (!list.length) ul.append(el("li", "", "Nothing yet.")); for (const x of list) ul.append(fmt(x)); return ul; }
function trafficRow(ev) { const li = el("li", ev.status); li.append(el("time", "", clock(ev.t)), document.createTextNode(ev.label)); return li; }
function table(rowsData, cols) {
  const t = el("table", "t"); const h = el("tr"); cols.forEach((c) => h.append(el("th", "", c))); t.append(h);
  for (const r of rowsData) { const tr = el("tr"); cols.forEach((c) => tr.append(el("td", "", r[c] === null || r[c] === undefined ? "" : String(r[c])))); t.append(tr); }
  return t;
}
function tabs(names, current, onPick) {
  const d = el("div", "chips"); for (const n of names) { const b = el("button", "", n); b.setAttribute("aria-pressed", String(n === current)); b.onclick = () => onPick(n); d.append(b); } return d;
}
const yes = (v) => (v === null || v === undefined ? "–" : v ? "answers" : "silent");

let dbTable = "bursts", hubTab = "Rules";
async function renderPanel() {
  const p = $("panel"), id = selected, n = NODES[id];
  const head = [el("h2", "", n ? n.title : id)];
  try {
    if (n?.device) {
      const d = devices.find((x) => x.astronautId === id) || {};
      const b = await api(`/hub/body/${encodeURIComponent(id)}`);
      const v = b.values;
      const open = el("a", "open", "Open this astronaut's screen"); open.href = `/body/?astronaut=${encodeURIComponent(id)}`; open.target = "_blank";
      p.replaceChildren(...head, el("p", "sub", `${d.name} · ${d.role} · device WEARABLE-${id}`),
        kv([["Connection", d.connected ? `connected (${d.lastSeenSeconds} s ago)` : d.worn ? "no signal" : "taken off"], ["State", b.eva ? `outside since ${b.eva.since}` : b.state ?? "–"],
          ["Heart rate", `${v["hr.rest"] ?? "–"} bpm`], ["Blood oxygen", `${v["spo2.pct"] ?? "–"} %`], ["Radiation now", `${b.doseRate?.toFixed(1) ?? "–"} µSv/h`],
          ["Career dose", `${v["radiation.careerMsv"]} mSv`], ["Readings sent", d.bursts], ["Alerts sent back", d.alertsDown]]),
        el("h3", "", "Traffic from this wearable"), rows(recent.filter((e) => e.astronaut === id).slice(0, 14), trafficRow), open);
      return;
    }
    if (id === "net") {
      const blocked = recent.filter((e) => e.status === "blocked").slice(0, 6);
      p.replaceChildren(...head, el("p", "sub", "Every wearable connects through this private network. A device only gets in with the secret key it received when it was paired at its dock. One reading per wearable per second goes up; alert codes come back down in the reply."),
        el("h3", "", "Crew overview"),
        ...devices.map((d) => { const r = el("div", "dev"); const i = el("i", d.connected ? "on" : ""); const right = el("span", "r", `${d.bursts} up · ${d.alertsDown} down`);
          r.append(i, el("b", "", d.name), right, el("small", "", `WEARABLE-${d.astronautId} · ${d.connected ? `connected · ${d.state}` : d.worn ? "no signal" : "taken off"}${d.blocked ? ` · ${d.blocked} fake attempts blocked` : ""}`)); return r; }),
        el("h3", "", "Blocked"), rows(blocked, trafficRow));
      return;
    }
    if (id === "hub") {
      const t = tabs(["Rules", "Database", "Outbox"], hubTab, (x) => { hubTab = x; renderPanel(); });
      if (hubTab === "Rules") {
        p.replaceChildren(...head, el("p", "sub", "Checks every reading (physically possible? a sensor glitch?), stores it, and runs the alert rules against each astronaut's own pre-flight baseline. Rules fire first; AI only explains."),
          t, el("h3", "", "Rules that fired"), rows(recent.filter((e) => e.kind === "rule" || e.status === "flagged" || e.kind === "eva").slice(0, 16), trafficRow));
      } else if (hubTab === "Database") {
        const chips = el("div", "chips");
        for (const [tb, c] of Object.entries(status.tables)) { const b = el("button", "", `${tb} ${c}`); b.setAttribute("aria-pressed", String(tb === dbTable)); b.onclick = () => { dbTable = tb; renderPanel(); }; chips.append(b); }
        const d = await api(`/hub/db/${dbTable}?limit=12`);
        const cols = d.rows.length ? Object.keys(d.rows[0]).slice(0, 6) : [];
        p.replaceChildren(...head, el("p", "sub", "The spacecraft's own database, on board. Device keys are masked."), t, chips, el("h3", "", `${dbTable} (${d.count})`), table(d.rows, cols));
      } else {
        p.replaceChildren(...head, el("p", "sub", "Everything for Earth waits here. At the end of each mission day it goes out in one batch; RETURN_NOW and CHECK_VITALS go right away. Nothing leaves the outbox until it is confirmed."),
          t, kv([["Waiting", status.outbox], ["Urgent", status.outboxUrgent], ["Next day-end send", `in ${Math.round(status.clock.secondsToDayEnd)} s`], ["Confirmed so far", status.tables.synced]]),
          el("h3", "", "Sends"), rows(status.sync.history || [], (h) => { const li = el("li", "ok"); li.append(el("time", "", clock(h.at)), document.createTextNode(`${h.reason}: ${h.sent} sent, ${h.confirmed} confirmed`)); return li; }));
      }
      return;
    }
    if (id === "cloudflare" || id === "nasa") {
      const v = await api("/hub/verify");
      const ch = status.checker || {};
      p.replaceChildren(...head, el("p", "sub", status.via === "cloudflare"
          ? "The Worker keeps every record the spacecraft sends in its D1 database. NASA pulls from it. While the link to NASA is cut, records wait in D1 and NASA retries every 3 s; nothing is lost."
          : "No Cloudflare Worker configured: the spacecraft sends straight to NASA. While the link is cut, records wait in the outbox."),
        kv([["Runs on", status.via === "cloudflare" ? status.cloudflareUrl : "direct to the NASA receiver"], ["Link to NASA", linkUp === null ? "unreachable" : linkUp ? "up" : "down"],
          ["Spacecraft confirmed", ch.db?.spacecraftConfirmed ?? "–"], ["Cloudflare D1 holds", ch.db?.cloudflare ?? "–"], ["NASA holds", ch.db?.nasa ?? v.nasaTotal ?? "–"], ["Waiting in Cloudflare", ch.db?.waitingAtCloudflare ?? "–"]]),
        el("h3", "", "Nothing lost? (per astronaut)"),
        table(v.rows.map((r) => ({ Astronaut: r.name, Sent: r.wearableSent, Stored: r.hubBursts, "For Earth": r.recordsCreated, Waiting: r.outboxPending, Confirmed: r.confirmedByNasa, Check: r.ok ? "Nothing lost" : "Waiting" })),
          ["Astronaut", "Sent", "Stored", "For Earth", "Waiting", "Confirmed", "Check"]),
        el("h3", "", "Link log (saved in the database)"), rows(ch.log || [], (x) => { const li = el("li", x.event === "restored" ? "ok" : "failed"); li.append(el("time", "", clock(x.at)), document.createTextNode(x.detail)); return li; }));
      return;
    }
    if (id === "checker") {
      const ch = status.checker || {}, parts = ch.parts || {}, db = ch.db || {};
      const partRows = [["Cloudflare Worker + D1", status.via === "cloudflare" ? "answers" : "not configured"], ["Spacecraft hub", yes(parts.hub?.up)], ["NASA", yes(parts.nasa?.up)],
        ["Onboard AI agent", parts.agent ? `${parts.agent.model || ""}` : "–"], ["DONKI space weather", yes(parts.donki?.up)],
        ...(parts.devices || []).map((d) => [`Wearable ${d.id}`, d.up ? `answers (${d.seenS ?? "?"} s)` : "silent"])];
      p.replaceChildren(...head,
        el("p", "sub", ch.via === "cloudflare" ? "Runs in the Cloudflare Worker. Cloudflare cannot call into the spacecraft's private network, so the hub and NASA report in every 3 s. The Worker marks anything quiet as down, compares the three databases, and Workers AI words the result (numbers checked)." : "No Worker configured: the hub runs the same check itself."),
        el("p", "said", ch.sentence?.text || ch.error || "Waiting for the first check…"),
        el("p", "sub", `${ch.sentence?.source === "Workers AI" ? "Worded by Workers AI" : "Rule text"} · checked ${ch.at ? clock(ch.at) : "–"}`),
        el("h3", "", "Every part"), table(partRows.map(([a, b]) => ({ Part: a, Status: b })), ["Part", "Status"]),
        el("h3", "", "Three databases"), table([{ Where: "Spacecraft (confirmed sent)", Records: db.spacecraftConfirmed }, { Where: "Cloudflare D1", Records: db.cloudflare },
          { Where: "NASA", Records: db.nasa }, { Where: "Waiting in Cloudflare", Records: db.waitingAtCloudflare }], ["Where", "Records"]),
        el("p", db.ok === false ? "fail" : "pass", db.ok === false ? "The databases do not agree." : "They agree: nothing lost."));
      return;
    }
    if (id === "donki") {
      const ev = await api("/hub/events?kind=space_weather&limit=10");
      const live = (await api("/hub/space-weather")).live || [];
      const replay = el("button", "act storm", "Replay a solar event"); replay.onclick = () => api("/hub/space-weather/replay", {}).then(renderPanel);
      p.replaceChildren(...head, el("p", "sub", `Live: Cloudflare fetches NASA DONKI on a schedule and feeds it to the spacecraft. Mission calendar: real DONKI events from May–June 2024, replayed. Radiation comes from real Curiosity RAD measurements (${status.rad.cruise.days} cruise days, ${status.rad.surface.days} surface sols).`),
        replay, el("h3", "", "Coming up on the mission calendar"),
        rows(ev, (e) => { const li = el("li", e.sw_type === "SEP" ? "alert" : "ok"); li.append(el("time", "", e.when), document.createTextNode(`${e.title} · ${e.utc || ""} · ${e.durationMin ? `lasted ${e.durationMin} min` : e.durationNote || ""} `));
          if (e.link) { const a = el("a", "", "record"); a.href = e.link; a.target = "_blank"; a.rel = "noopener"; li.append(a); } return li; }),
        el("h3", "", "Live now (DONKI)"),
        rows(live.slice(0, 8), (e) => { const li = el("li", "ok"); li.append(el("time", "", (e.event_time || "").slice(0, 16).replace("T", " ")), document.createTextNode(` ${e.summary}`)); return li; }));
      return;
    }
    if (id === "agent") {
      const log = await api("/hub/db/agent_log?limit=8");
      p.replaceChildren(...head, el("p", "sub", "Answers the astronauts' questions from their own data: a local model (Ollama) when one is set, otherwise Workers AI through Cloudflare, otherwise rules. Any AI wording that changes a number is rejected."),
        kv([["Uses now", status.ai.onboardAgent !== "rules" ? `Ollama ${status.ai.onboardAgent}` : status.ai.workersAi ? "Workers AI (through Cloudflare)" : "rules"]]),
        el("h3", "", "Recent questions"), rows(log.rows, (r) => { const li = el("li", "ok"); li.append(el("b", "", r.astronaut_id + ": "), document.createTextNode(`${r.question} → ${r.answer} (${r.source})`)); return li; }));
      return;
    }
    if (id === "ghost") {
      p.replaceChildren(...head, el("p", "sub", "Devices that tried to send without a valid key. They never get past the private network."),
        rows(recent.filter((e) => e.status === "blocked").slice(0, 15), trafficRow));
    }
  } catch (e) { p.replaceChildren(...head, el("p", "sub", `Could not load: ${e.message}`)); }
}

// ------------------------------------------------------------------ start
for (const [a, b] of EDGES) edge(a, b);
for (const [id, n] of Object.entries(NODES)) drawNode(id, n);
legend();
markSelected();
pollStatus().then(renderPanel); pollNetwork();
setInterval(pollNetwork, 400);
setInterval(pollStatus, 1000);
setInterval(drawCountdown, 250);
setInterval(renderPanel, 2000);
setInterval(sweep, 6000); setTimeout(sweep, 1500);
