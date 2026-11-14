// Spacecraft hub screen: live schematic of the Cloudflare private network, crew overview, database, verification.
import { api, el, clock, spark } from "/apps/shared/hub.js";

const $ = (id) => document.getElementById(id);
const SVG = "http://www.w3.org/2000/svg";

// ------------------------------------------------------------------ schematic
const NODES = {
  "astro-1": { x: 85, y: 110, title: "Astronaut 1", sub: "wearable", cls: "astro" },
  "astro-2": { x: 85, y: 330, title: "Astronaut 2", sub: "wearable", cls: "astro" },
  tunnel: { x: 280, y: 220, title: "Private network", sub: "device keys only", cls: "cfnode" },
  worker: { x: 450, y: 220, title: "Worker", sub: "checks · rules", cls: "cfnode" },
  d1: { x: 590, y: 95, title: "D1 database", sub: "spacecraft data", cls: "cfnode" },
  ai: { x: 590, y: 345, title: "Workers AI", sub: "explains", cls: "cfnode" },
  agent: { x: 300, y: 372, title: "Onboard agent", sub: "on board", cls: "cfnode" },
  outbox: { x: 720, y: 220, title: "Outbox", sub: "records for Earth", cls: "cfnode" },
  link: { x: 880, y: 220, title: "Link to Earth", sub: "", cls: "" },
  nasa: { x: 1025, y: 220, title: "NASA", sub: "mission record", cls: "nasa" },
  donki: { x: 1025, y: 375, title: "DONKI", sub: "space weather", cls: "nasa", below: true },
};
const EDGES = [["astro-1", "tunnel"], ["astro-2", "tunnel"], ["tunnel", "worker"], ["worker", "d1"], ["d1", "outbox"],
  ["worker", "outbox"], ["worker", "ai"], ["ai", "agent"], ["agent", "tunnel"], ["ai", "d1"], ["outbox", "link"],
  ["link", "nasa"], ["donki", "link"], ["link", "d1"]];
const W = 130, H = 54;
const nodeEls = {}, edgeEls = {};

function svg(tag, attrs, parent) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  if (parent) parent.append(n);
  return n;
}

function drawSchematic() {
  for (const [a, b] of EDGES) {
    edgeEls[a + ">" + b] = svg("line", { x1: NODES[a].x, y1: NODES[a].y, x2: NODES[b].x, y2: NODES[b].y, class: "edge" }, $("edges"));
  }
  for (const [id, n] of Object.entries(NODES)) {
    const g = svg("g", { class: "node " + n.cls, transform: `translate(${n.x - W / 2} ${n.y - H / 2})` }, $("nodes"));
    svg("rect", { width: W, height: H, rx: 5 }, g);
    const t = svg("text", { x: W / 2, y: 22, class: "n-title" }, g); t.textContent = n.title;
    const s = svg("text", { x: W / 2, y: 39, class: "n-sub" }, g); s.textContent = n.sub;
    const c = svg("text", { x: W / 2, y: n.below ? H + 16 : -8, class: "n-count" }, g);
    nodeEls[id] = { g, sub: s, count: c };
  }
}

function setNode(id, { sub, count, cls } = {}) {
  const n = nodeEls[id]; if (!n) return;
  if (sub !== undefined) n.sub.textContent = sub;
  if (count !== undefined) n.count.textContent = count;
  if (cls !== undefined) n.g.setAttribute("class", `node ${NODES[id].cls} ${cls}`);
}

const live = new Set();
function animate(ev) {
  const path = ev.path.filter((p) => NODES[p]);
  if (path.length === 1) { flash(path[0]); return; }
  if (path.length < 2 || live.size > 60) return;
  const blocked = ev.status === "blocked", failed = ev.status === "failed";
  const stops = blocked || failed ? path.slice(0, Math.max(2, path.length - 1)) : path;
  const dot = svg("circle", { r: ev.status === "alert" ? 8 : 6, class: "packet " + ev.status }, $("packets"));
  live.add(dot);
  const seg = 260; let i = 0, t0 = null;
  function step(t) {
    if (t0 === null) t0 = t;
    const k = Math.min(1, (t - t0) / seg);
    const a = NODES[stops[i]], b = NODES[stops[i + 1]];
    dot.setAttribute("cx", a.x + (b.x - a.x) * k);
    dot.setAttribute("cy", a.y + (b.y - a.y) * k);
    if (k < 1) return requestAnimationFrame(step);
    i += 1; t0 = null;
    if (i < stops.length - 1) return requestAnimationFrame(step);
    if (blocked || failed) cross(b);
    flash(stops[stops.length - 1]);
    setTimeout(() => { dot.remove(); live.delete(dot); }, blocked || failed ? 500 : 120);
  }
  requestAnimationFrame(step);
}

function cross(n) {
  const g = svg("g", {}, $("packets"));
  svg("line", { x1: n.x - 12, y1: n.y - 40, x2: n.x + 12, y2: n.y - 16, class: "burst-x" }, g);
  svg("line", { x1: n.x + 12, y1: n.y - 40, x2: n.x - 12, y2: n.y - 16, class: "burst-x" }, g);
  setTimeout(() => g.remove(), 900);
}

function flash(id) {
  const n = nodeEls[id]; if (!n) return;
  n.g.classList.add("hot"); setTimeout(() => n.g.classList.remove("hot"), 250);
}

// ------------------------------------------------------------------ traffic log
let since = 0;
async function pollNetwork() {
  try {
    const events = await api(`/hub/network?since=${since}`);
    for (const ev of events) {
      since = Math.max(since, ev.seq);
      animate(ev);
      const li = el("li", ev.status);
      li.append(el("time", "", clock(ev.t)), document.createTextNode(ev.label + (ev.ms ? ` (${ev.ms} ms)` : "")));
      $("log").prepend(li);
    }
    while ($("log").children.length > 150) $("log").lastChild.remove();
  } catch { /* hub restarting */ }
}

// ------------------------------------------------------------------ top bar + link
let linkUp = null;
async function pollStatus() {
  try {
    const [s, link] = await Promise.all([api("/hub/status"), api("/hub/link")]);
    $("sBursts").textContent = s.tables.bursts;
    $("sOutbox").textContent = s.outbox;
    $("sNasa").textContent = s.tables.synced;
    $("sBlocked").textContent = s.tables.rejected;
    setNode("d1", { count: `${s.tables.bursts} bursts, ${s.tables.alerts} alert${s.tables.alerts === 1 ? "" : "s"}` });
    setNode("outbox", { count: s.outbox ? `${s.outbox} waiting` : "empty", cls: s.outbox > 50 ? "bad" : "" });
    setNode("tunnel", { count: s.tables.rejected ? `${s.tables.rejected} blocked` : "" });
    setNode("ai", { sub: s.ai.workersAi ? "on" : "off: templates" });
    setNode("agent", { sub: s.ai.onboardAgent === "rules" ? "rules" : s.ai.onboardAgent.slice(0, 18) });
    setNode("donki", { count: s.donki.error ? "offline: replay only" : s.donki.lastFetch ? "pulled" : "" });
    $("aiState").textContent = `Workers AI: ${s.ai.workersAi ? s.ai.workersAiModel : "off (template text)"} · Onboard agent: ${s.ai.onboardAgent}`;
    drawLink(link, s);
  } catch {
    $("linkState").textContent = "Hub unreachable"; $("linkState").className = "link-state down";
  }
}

function drawLink(link, s) {
  const st = $("linkState"), btn = $("linkBtn");
  if (!link.reachable) {
    linkUp = null;
    st.textContent = link.nasaUrl ? "NASA receiver unreachable" : "No NASA receiver configured";
    st.className = "link-state down"; btn.disabled = true; btn.textContent = "…";
    setNode("link", { sub: "no answer", cls: "bad" }); setNode("nasa", { cls: "bad" });
    edgeEls["link>nasa"].classList.add("down");
    return;
  }
  linkUp = link.up;
  st.textContent = `Link to Earth: ${link.up ? "UP" : "DOWN"}`;
  st.className = "link-state " + (link.up ? "up" : "down");
  btn.disabled = false;
  btn.textContent = link.up ? "Cut the link" : "Restore the link";
  btn.className = "link-btn " + (link.up ? "cut" : "restore");
  setNode("link", { sub: link.up ? "up" : "DOWN · outbox holds", cls: link.up ? "" : "bad" });
  setNode("nasa", { cls: "", count: `${s.tables.synced} confirmed` });
  edgeEls["link>nasa"].classList.toggle("down", !link.up);
}

$("linkBtn").onclick = async () => {
  if (linkUp === null) return;
  $("linkBtn").disabled = true;
  try { drawLink(await api("/hub/link", { up: !linkUp }), await api("/hub/status")); } catch { /* next poll fixes it */ }
};

async function action(btn, path, ok) {
  btn.disabled = true;
  try { $("actMsg").textContent = ok(await api(path, {})); }
  catch (e) { $("actMsg").textContent = e.message; }
  finally { btn.disabled = false; }
}
$("replay").onclick = (e) => action(e.target, "/hub/space-weather/replay", (r) => `Replayed ${r.event} from NASA DONKI. Spacewalkers get RETURN_NOW on their next burst.`);
$("refreshWx").onclick = (e) => action(e.target, "/hub/space-weather/refresh", (r) => (r.error ? `DONKI unreachable: ${r.error}` : `DONKI pulled from ${r.source}`));
$("syncNow").onclick = (e) => action(e.target, "/hub/sync", (r) => (r.sent ? `Sent ${r.sent}, NASA confirmed ${r.confirmed}${r.problem ? ` (${r.problem})` : ""}` : "Outbox is empty."));

// ------------------------------------------------------------------ tabs
let tab = "crew";
document.querySelectorAll("[data-tab]").forEach((b) => (b.onclick = () => {
  tab = b.dataset.tab;
  document.querySelectorAll("[data-tab]").forEach((x) => x.setAttribute("aria-selected", String(x === b)));
  document.querySelectorAll(".pane").forEach((p) => (p.hidden = p.id !== "pane-" + tab));
  pollTab();
}));

const COLORS = { RETURN_NOW: "#ff5c5c", CHECK_VITALS: "#ffa94d", INFO: "#9ad0ff" };
const cards = {};
function crewCard(a) {
  if (cards[a.id]) return cards[a.id];
  const box = el("article", "astro");
  const head = el("div", "astro-head"); const h = el("h3"); const role = el("span"); head.append(h, role);
  const read = el("div", "readout");
  const canvas = el("canvas");
  const last = el("p", "last-alert");
  const row = el("div", "row");
  const sumBtn = el("button", "", "Write daily summary"); sumBtn.onclick = () => api(`/hub/summary/${a.id}`, {}).catch(() => {});
  const open = el("button", "", "Open station"); open.onclick = () => window.open(`/astronaut/?id=${a.id}`, "_blank");
  row.append(sumBtn, open);
  box.append(head, read, canvas, last, row);
  $("crew").append(box);
  return (cards[a.id] = { box, h, role, read, canvas, last });
}

async function pollCrew() {
  const crew = await api("/hub/crew");
  for (const a of crew) {
    const c = crewCard(a), L = a.latest, p = a.profile;
    c.h.textContent = a.name;
    c.role.textContent = L ? `${L.state} · last burst ${clock(L.received_at)}` : "no bursts yet";
    c.read.replaceChildren(...[
      [L ? Math.round(L.heart_rate) : "–", `bpm (baseline ${p.resting_hr})`],
      [L ? Math.round(L.spo2) + "%" : "–", `oxygen (baseline ${p.spo2}%)`],
      [L ? L.dose_rate.toFixed(0) : "–", "µSv/h now"],
      [`${a.radiation.evaPct.toFixed(0)}%`, "spacewalk budget"],
    ].map(([v, l]) => { const d = el("div"); d.append(el("b", "", String(v)), el("span", "", l)); return d; }));
    spark(c.canvas, a.bursts.map((b) => (b.quality === "valid" ? b.heart_rate : null)), { color: "#ff9ab9", baseline: p.resting_hr });
    const al = a.activeAlert;
    c.box.classList.toggle("alerting", !!al && al.status === "active" && al.code !== "INFO");
    if (al) {
      c.last.style.setProperty("--a", COLORS[al.code] || "#9ad0ff");
      c.last.replaceChildren(el("b", "", al.code + (al.status === "active" ? "" : ` (${al.status})`)), document.createTextNode(`${clock(al.time)} · ${al.ai_message || al.message}`),
        el("span", "ai-note", al.ai_message ? `Explained by ${al.ai_source}` : "Rule text (the rule fires first; AI only explains)"));
    } else c.last.replaceChildren(document.createTextNode("No alerts."));
  }
}

function td(text, cls) { return el("td", cls, text); }
async function pollVerify() {
  const v = await api("/hub/verify");
  const head = el("tr");
  for (const h of ["Astronaut", "Wearable sent", "Hub stored", "Missing", "Flagged", "Observations", "Records for Earth", "Waiting in outbox", "Confirmed by NASA", "NASA has", "Check"]) head.append(el("th", "", h));
  const rows = v.rows.map((r) => {
    const tr = el("tr");
    const types = Object.entries(r.byType).map(([k, n]) => `${n} ${k}`).join(", ");
    tr.append(td(r.astronautId), td(r.wearableSent, "num"), td(r.hubBursts, "num"), td(r.missingBursts, "num"), td(r.flagged, "num"),
      td(r.observations, "num"), td(`${r.recordsCreated} (${types || "none"})`), td(r.outboxPending, "num"), td(r.confirmedByNasa, "num"),
      td(r.atNasa ?? "unreachable", "num"),
      td(r.ok ? "Nothing lost" : r.atNasa === null || r.atNasa === undefined ? "NASA unreachable" : "Mismatch", r.ok ? "pass" : "fail"));
    return tr;
  });
  $("verify").replaceChildren(head, ...rows);
  $("verifyNote").textContent = `Records for Earth = waiting in outbox + confirmed by NASA, for every astronaut. ` +
    `Outbox total ${v.outbox}. Bursts blocked by the private network: ${v.rejectedBursts}. ` +
    `Observations = 4 provenance-labelled values per burst in the MEDVITAL observation store.`;
}

let dbTable = "bursts";
async function pollDb() {
  const s = await api("/hub/status");
  $("dbTabs").replaceChildren(...Object.entries(s.tables).map(([t, n]) => {
    const b = el("button", "", `${t} ${n}`); b.setAttribute("aria-pressed", String(t === dbTable));
    b.onclick = () => { dbTable = t; pollDb(); }; return b;
  }));
  const d = await api(`/hub/db/${dbTable}?limit=25`);
  const cols = d.rows.length ? Object.keys(d.rows[0]) : [];
  const head = el("tr"); cols.forEach((c) => head.append(el("th", "", c)));
  $("dbTable").replaceChildren(head, ...d.rows.map((r) => { const tr = el("tr"); cols.forEach((c) => tr.append(td(r[c] === null ? "" : String(r[c])))); return tr; }));
}

async function pollWx() {
  const crew = await api("/hub/crew");
  const wx = crew.length ? crew[0].spaceWeather : { recent: [] };
  $("wxList").replaceChildren(...(wx.recent.length ? wx.recent.map((e) => {
    const li = el("li", e.active_until && new Date(e.active_until) > new Date() ? "active" : "");
    li.append(el("b", "", `${e.kind} · ${e.event_time}`), document.createTextNode(` · ${e.summary} (${e.source}) `));
    if (e.link) { const a = el("a", "", "DONKI record"); a.href = e.link; a.target = "_blank"; a.rel = "noopener"; li.append(a); }
    return li;
  }) : [el("li", "", "No space weather yet. Pull DONKI, or press Replay solar event.")]));
}

async function pollTab() {
  try {
    if (tab === "crew") await pollCrew();
    else if (tab === "verify") await pollVerify();
    else if (tab === "db") await pollDb();
    else await pollWx();
  } catch { /* hub restarting */ }
}

drawSchematic();
pollStatus(); pollNetwork(); pollTab();
setInterval(pollNetwork, 600);
setInterval(pollStatus, 2000);
setInterval(pollTab, 2500);
