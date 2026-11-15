// Spacecraft hub screen: the private network with every connected wearable, live traffic every second,
// the mission clock, and the end-of-day send to NASA. Click a box to open it in the side panel.
import { api, el, clock } from "/apps/shared/hub.js";

const $ = (id) => document.getElementById(id);
const SVG = "http://www.w3.org/2000/svg";

// ------------------------------------------------------------------ fixed nodes (devices are added from the crew)
const NODES = {
  tunnel: { x: 335, y: 260, w: 196, h: 84, title: "Private network", sub: "device keys only", cls: "cfnode big" },
  worker: { x: 515, y: 260, w: 120, h: 56, title: "Worker", sub: "checks · rules", cls: "cfnode" },
  d1: { x: 625, y: 110, w: 130, h: 56, title: "D1 database", sub: "spacecraft data", cls: "cfnode" },
  outbox: { x: 690, y: 260, w: 120, h: 56, title: "Outbox", sub: "for Earth", cls: "cfnode" },
  ai: { x: 625, y: 420, w: 130, h: 56, title: "Workers AI", sub: "explains", cls: "cfnode" },
  agent: { x: 420, y: 440, w: 140, h: 56, title: "Onboard agent", sub: "on board", cls: "cfnode" },
  link: { x: 852, y: 260, w: 104, h: 56, title: "Link", sub: "to Earth", cls: "earth" },
  nasa: { x: 948, y: 150, w: 92, h: 56, title: "NASA", sub: "record", cls: "earth" },
  donki: { x: 948, y: 390, w: 92, h: 56, title: "DONKI", sub: "NASA CCMC", cls: "earth" },
  ghost: { x: 100, y: 485, w: 150, h: 40, title: "Unknown devices", sub: "", cls: "ghost" },
};
const EDGES = [["tunnel", "worker"], ["worker", "d1"], ["worker", "outbox"], ["d1", "outbox"], ["worker", "ai"], ["ai", "agent"],
  ["agent", "tunnel"], ["ai", "d1"], ["outbox", "link"], ["link", "nasa"], ["link", "donki"], ["link", "d1"], ["ghost", "tunnel"]];
const nodeEls = {}, edgeEls = {};
let devices = [], selected = "tunnel";

function svg(tag, attrs, parent) {
  const n = document.createElementNS(SVG, tag);
  for (const [k, v] of Object.entries(attrs || {})) n.setAttribute(k, v);
  if (parent) parent.append(n);
  return n;
}

function drawNode(id, n) {
  const g = svg("g", { class: `node ${n.cls}`, transform: `translate(${n.x - n.w / 2} ${n.y - n.h / 2})`, tabindex: 0, role: "button",
    "aria-label": n.title }, $("nodes"));
  svg("rect", { width: n.w, height: n.h, rx: 6 }, g);
  const t = svg("text", { x: n.w / 2, y: n.h > 50 ? 23 : 17, class: "t" }, g); t.textContent = n.title;
  const s = svg("text", { x: n.w / 2, y: n.h > 50 ? 41 : 32, class: "s" }, g); s.textContent = n.sub;
  const c = svg("text", { x: n.w / 2, y: -8, class: "c" }, g);
  let led = null;
  if (n.cls.includes("astro")) led = svg("circle", { cx: 14, cy: 14, r: 6, class: "led offl" }, g);
  g.onclick = g.onkeydown = (e) => { if (e.type === "keydown" && e.key !== "Enter") return; select(id); };
  nodeEls[id] = { g, s, c, led };
}

function edge(a, b) {
  const A = NODES[a], B = NODES[b];
  const l = svg("line", { x1: A.x, y1: A.y, x2: B.x, y2: B.y, class: "edge" }, $("edges"));
  edgeEls[a + ">" + b] = l;
  return l;
}

function layoutDevices(list) {
  const ids = list.map((d) => d.astronautId).join(",");
  if (ids === layoutDevices.last) return;
  layoutDevices.last = ids;
  for (const id of Object.keys(nodeEls)) if (NODES[id]?.device) { nodeEls[id].g.remove(); delete nodeEls[id]; delete NODES[id]; edgeEls[id + ">tunnel"]?.remove(); }
  const top = 66, bottom = 400, step = list.length > 1 ? (bottom - top) / (list.length - 1) : 0;
  list.forEach((d, i) => {
    NODES[d.astronautId] = { x: 100, y: list.length > 1 ? top + i * step : 260, w: 150, h: 56, title: d.name.split(" ")[0],
      sub: "wearable", cls: "astro", device: true };
    edge(d.astronautId, "tunnel");
    drawNode(d.astronautId, NODES[d.astronautId]);
  });
  if (!NODES[selected]) selected = "tunnel";
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
const live = new Set();
function animate(ev) {
  const path = ev.path.filter((p) => NODES[p]);
  if (ev.kind === "burst" && path[0] && NODES[path[0]]?.device) pulse(path[0]);
  if (path.length < 2) { if (path[0]) flash(path[0]); return; }
  if (live.size > 70 && ev.kind === "burst") return;
  const blocked = ev.status === "blocked", failed = ev.status === "failed";
  const from = blocked && !NODES[ev.astronaut]?.device ? ["ghost", "tunnel"] : path;
  const stops = failed ? from.slice(0, Math.max(2, from.length - 1)) : from;
  const big = ev.kind === "dayend" || ev.kind === "ack";
  const seg = big ? 650 : ev.kind === "burst" ? 150 : 260;
  const g = svg("g", {}, $("packets"));
  const dot = svg("circle", { r: big ? 13 : ev.status === "alert" ? 8 : 5, class: "packet " + (ev.kind === "dayend" ? "batch" : ev.kind === "ack" ? "ack" : ev.status) }, g);
  let label = null;
  if (big && ev.count) { label = svg("text", { class: "pkt-label", dy: -18 }, g); label.textContent = `${ev.count} records`; }
  live.add(g);
  let i = 0, t0 = null;
  function step(t) {
    if (t0 === null) t0 = t;
    const k = Math.min(1, (t - t0) / seg);
    const a = NODES[stops[i]], b = NODES[stops[i + 1]];
    const x = a.x + (b.x - a.x) * k, y = a.y + (b.y - a.y) * k;
    dot.setAttribute("cx", x); dot.setAttribute("cy", y);
    if (label) { label.setAttribute("x", x); label.setAttribute("y", y); }
    if (k < 1) return requestAnimationFrame(step);
    i += 1; t0 = null;
    if (i < stops.length - 1) return requestAnimationFrame(step);
    if (blocked || failed) cross(b);
    flash(stops[stops.length - 1]);
    setTimeout(() => { g.remove(); live.delete(g); }, blocked || failed ? 600 : 80);
  }
  requestAnimationFrame(step);
}

function pulse(id) {
  const n = NODES[id], e = nodeEls[id]; if (!n || !e) return;
  const ring = svg("circle", { cx: n.x - n.w / 2 + 14, cy: n.y - n.h / 2 + 14, r: 6, class: "pulse" }, $("packets"));
  ring.animate([{ r: 6, opacity: 1 }, { r: 22, opacity: 0 }], { duration: 700, easing: "ease-out" }).onfinish = () => ring.remove();
}
function cross(n) {
  const g = svg("g", {}, $("packets"));
  svg("line", { x1: n.x - 12, y1: n.y - 52, x2: n.x + 12, y2: n.y - 28, class: "burst-x" }, g);
  svg("line", { x1: n.x + 12, y1: n.y - 52, x2: n.x - 12, y2: n.y - 28, class: "burst-x" }, g);
  setTimeout(() => g.remove(), 1000);
}
function flash(id) { const n = nodeEls[id]; if (!n) return; n.g.classList.add("hot"); setTimeout(() => n.g.classList.remove("hot"), 200); }

let since = 0;
const recent = [];
async function pollNetwork() {
  try {
    const events = await api(`/hub/network?since=${since}`);
    for (const ev of events) {
      since = Math.max(since, ev.seq);
      animate(ev);
      recent.unshift(ev); if (recent.length > 300) recent.pop();
      if (ev.kind === "dayend") banner(`End of day: sending ${ev.count} records to NASA…`, false);
      if (ev.kind === "ack") banner(`NASA confirmed ${ev.count} records`, true);
    }
  } catch { /* hub restarting */ }
}
function banner(text, ack) {
  const b = $("dayend"); b.textContent = text; b.className = "dayend" + (ack ? " ack" : ""); b.hidden = false;
  clearTimeout(banner.t); banner.t = setTimeout(() => { b.hidden = true; }, 3500);
}

// ------------------------------------------------------------------ status: clock, devices, link
let status = null, linkUp = null;
async function pollStatus() {
  try {
    const [s, devs, link] = await Promise.all([api("/hub/status"), api("/hub/devices"), api("/hub/link")]);
    status = s; devices = devs;
    const c = s.clock;
    $("clockDay").textContent = `Day ${c.day}`; $("clockTime").textContent = c.time;
    $("clockPhase").textContent = c.phaseLabel + (c.sepActive ? " · solar particle event" : "") + (c.blackout ? " · link blackout" : "");
    $("dayFill").style.width = `${(c.dayFraction * 100).toFixed(1)}%`;
    $("nextSend").textContent = c.blackout ? `Blackout: Earth not in view. Records wait in the outbox.`
      : `Next send to NASA: end of day ${c.day}, in ${Math.max(0, Math.round(c.secondsToDayEnd))} s. Urgent alerts go right away.`;
    layoutDevices(devs);
    for (const d of devs) {
      const n = nodeEls[d.astronautId]; if (!n) continue;
      n.led.setAttribute("class", "led " + (d.connected ? "on" : "offl"));
      setNode(d.astronautId, { sub: d.connected ? `${d.state} · connected` : d.worn ? "no signal" : "taken off", count: `${d.bursts} bursts`, cls: d.connected ? "" : "off" });
      edgeEls[d.astronautId + ">tunnel"]?.classList.toggle("off", !d.connected);
    }
    const on = devs.filter((d) => d.connected).length;
    setNode("tunnel", { sub: `${on} of ${devs.length} wearables connected`, count: s.tables.rejected ? `${s.tables.rejected} blocked` : "" });
    setNode("d1", { count: `${s.tables.bursts} bursts · ${s.tables.tests} tests` });
    setNode("outbox", { sub: s.outbox ? `${s.outbox} waiting` : "empty", count: s.outboxUrgent ? `${s.outboxUrgent} urgent` : "" });
    setNode("ai", { sub: s.ai.workersAi ? "on" : "off: templates" });
    setNode("agent", { sub: s.ai.onboardAgent === "rules" ? "rules" : s.ai.onboardAgent.slice(0, 16) });
    setNode("donki", { sub: s.donki.error ? "offline: replay" : "NASA CCMC" });
    setNode("ghost", { sub: s.tables.rejected ? `${s.tables.rejected} blocked` : "none yet" });
    drawLink(link, s);
  } catch {
    $("linkState").textContent = "Hub unreachable"; $("linkState").className = "link-state down";
  }
}

function drawLink(link, s) {
  const st = $("linkState"), btn = $("linkBtn");
  if (!link.reachable) {
    linkUp = null; st.textContent = link.nasaUrl ? "NASA receiver unreachable" : "No NASA receiver configured";
    st.className = "link-state down"; btn.disabled = true; btn.textContent = "…";
    setNode("link", { sub: "no answer", cls: "bad" }); setNode("nasa", { cls: "bad" }); edgeEls["link>nasa"].classList.add("down");
    return;
  }
  linkUp = link.up;
  const down = !link.up || !!link.blackout;
  st.textContent = link.blackout ? "Link to Earth: blackout" : `Link to Earth: ${link.up ? "UP" : "DOWN"}`;
  st.className = "link-state " + (down ? "down" : "up");
  btn.disabled = false; btn.textContent = link.up ? "Cut the link" : "Restore the link"; btn.className = "link-btn " + (link.up ? "cut" : "restore");
  setNode("link", { sub: down ? (link.blackout ? "blackout" : "DOWN") : "up", cls: down ? "bad" : "" });
  setNode("nasa", { cls: "", count: `${s.tables.synced} confirmed` });
  edgeEls["link>nasa"].classList.toggle("down", down);
}
$("linkBtn").onclick = async () => { if (linkUp === null) return; $("linkBtn").disabled = true; try { await api("/hub/link", { up: !linkUp }); } catch { /* next poll */ } pollStatus(); };

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

let dbTable = "bursts";
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
        kv([["Connection", d.connected ? `connected (${d.lastSeenSeconds} s ago)` : d.worn ? "no signal" : "taken off"], ["State", b.state ?? "–"],
          ["Heart rate", `${v["hr.rest"] ?? "–"} bpm`], ["Blood oxygen", `${v["spo2.pct"] ?? "–"} %`], ["Radiation now", `${b.doseRate?.toFixed(1) ?? "–"} µSv/h`],
          ["Career dose", `${v["radiation.careerMsv"]} mSv`], ["Bursts sent", d.bursts], ["Alerts sent back", d.alertsDown]]),
        el("h3", "", "Traffic from this wearable"), rows(recent.filter((e) => e.astronaut === id).slice(0, 14), trafficRow), open);
      return;
    }
    if (id === "tunnel") {
      const blocked = recent.filter((e) => e.status === "blocked").slice(0, 6);
      const up = recent.filter((e) => e.kind === "burst" && e.status !== "blocked").slice(0, 40);
      const bytes = up.reduce((s, e) => s + (e.bytes || 0), 0);
      p.replaceChildren(...head, el("p", "sub", "Every wearable connects through this private network. A device only gets in with the secret key it received when it was paired at its dock. One burst per wearable per second goes up; alert codes come back down in the reply."),
        el("h3", "", "Devices"),
        ...devices.map((d) => { const r = el("div", "dev"); const i = el("i", d.connected ? "on" : ""); const right = el("span", "r", `${d.bursts} up · ${d.alertsDown} down`);
          r.append(i, el("b", "", d.name), right, el("small", "", `WEARABLE-${d.astronautId} · ${d.connected ? `connected · ${d.state}` : d.worn ? "no signal" : "taken off"}${d.blocked ? ` · ${d.blocked} fake attempts blocked` : ""}`)); return r; }),
        el("h3", "", "Right now"), kv([["Data going up", `${(bytes / Math.max(1, up.length / Math.max(1, devices.length))).toFixed(0)} bytes/s`], ["Connected", `${devices.filter((d) => d.connected).length} of ${devices.length}`], ["Blocked attempts", status?.tables.rejected ?? 0]]),
        el("h3", "", "Blocked"), rows(blocked, trafficRow),
        el("h3", "", "Latest traffic"), rows(recent.filter((e) => ["burst", "alert", "test", "pair"].includes(e.kind)).slice(0, 12), trafficRow));
      return;
    }
    if (id === "worker") {
      p.replaceChildren(...head, el("p", "sub", "Checks every burst (is it physically possible? a sensor glitch?), stores it, and runs the alert rules against that astronaut's own pre-flight baseline. Rules fire first; AI only explains."),
        el("h3", "", "Rules that fired"), rows(recent.filter((e) => e.kind === "rule" || e.status === "flagged").slice(0, 14), trafficRow));
      return;
    }
    if (id === "d1") {
      const s = await api("/hub/status");
      const chips = el("div", "chips");
      for (const [t, c] of Object.entries(s.tables)) { const b = el("button", "", `${t} ${c}`); b.setAttribute("aria-pressed", String(t === dbTable)); b.onclick = () => { dbTable = t; renderPanel(); }; chips.append(b); }
      const d = await api(`/hub/db/${dbTable}?limit=12`);
      const cols = d.rows.length ? Object.keys(d.rows[0]).slice(0, 6) : [];
      p.replaceChildren(...head, el("p", "sub", "The spacecraft's database. Device keys are masked."), chips, el("h3", "", `${dbTable} (${d.count})`), table(d.rows, cols));
      return;
    }
    if (id === "outbox") {
      p.replaceChildren(...head, el("p", "sub", "Everything for Earth waits here. At the end of each mission day it goes to NASA in one batch; RETURN_NOW and CHECK_VITALS alerts go right away. Nothing leaves the outbox until NASA confirms it saved it."),
        kv([["Waiting", status.outbox], ["Urgent", status.outboxUrgent], ["Next day-end send", `in ${Math.round(status.clock.secondsToDayEnd)} s`], ["Confirmed by NASA so far", status.tables.synced]]),
        el("h3", "", "Sends to NASA"), rows(status.sync.history || [], (h) => { const li = el("li", "ok"); li.append(el("time", "", clock(h.at)), document.createTextNode(`${h.reason}: ${h.sent} sent, ${h.confirmed} confirmed`)); return li; }));
      return;
    }
    if (id === "link" || id === "nasa") {
      const v = await api("/hub/verify");
      p.replaceChildren(...head, el("p", "sub", "The link to Earth. During a blackout or while the link is cut, nothing is lost: records wait in the outbox and go out when the link is back."),
        kv([["NASA receiver", status.nasaUrl || "not set"], ["Link", linkUp === null ? "unreachable" : linkUp ? "up" : "down"], ["Blackout now", status.clock.blackout || "no"], ["NASA has", v.nasaTotal ?? "–"]]),
        el("h3", "", "Nothing lost? (per astronaut)"),
        table(v.rows.map((r) => ({ Astronaut: r.name, Sent: r.wearableSent, Stored: r.hubBursts, "For Earth": r.recordsCreated, Waiting: r.outboxPending, "NASA has": r.atNasa ?? "–", Check: r.ok ? "Nothing lost" : r.atNasa === null || r.atNasa === undefined ? "NASA unreachable" : "Waiting" })),
          ["Astronaut", "Sent", "Stored", "For Earth", "Waiting", "NASA has", "Check"]),
        el("h3", "", "Link events"), rows(recent.filter((e) => ["sync", "ack", "dayend", "link"].includes(e.kind)).slice(0, 10), trafficRow));
      return;
    }
    if (id === "donki") {
      const ev = await api("/hub/events?kind=space_weather&limit=12");
      const replay = el("button", "act storm", "Replay a solar event"); replay.onclick = () => api("/hub/space-weather/replay", {}).then(renderPanel);
      p.replaceChildren(...head, el("p", "sub", `Real space weather from NASA DONKI (May–June 2024), placed on the mission calendar. Radiation comes from real Curiosity RAD measurements: ${status.rad.cruise.days} cruise days and ${status.rad.surface.days} surface sols.`),
        replay, el("h3", "", "Coming up"),
        rows(ev, (e) => { const li = el("li", e.sw_type === "SEP" ? "alert" : "ok"); li.append(el("time", "", e.when), document.createTextNode(`${e.title} · ${e.source} `));
          if (e.link) { const a = el("a", "", "record"); a.href = e.link; a.target = "_blank"; a.rel = "noopener"; li.append(a); } return li; }));
      return;
    }
    if (id === "ai" || id === "agent") {
      const log = await api("/hub/db/agent_log?limit=8");
      p.replaceChildren(...head, el("p", "sub", id === "ai" ? "Workers AI rewrites alerts and daily summaries in plain language when a Cloudflare account is configured. The onboard agent rejects any wording that changes a number." : "The onboard agent answers the astronauts' questions from their own data and double-checks the daily summaries."),
        kv([["Workers AI", status.ai.workersAi ? status.ai.workersAiModel : "off (template text)"], ["Onboard agent", status.ai.onboardAgent]]),
        el("h3", "", "Recent questions"), rows(log.rows, (r) => { const li = el("li", "ok"); li.append(el("b", "", r.astronaut_id + ": "), document.createTextNode(`${r.question} → ${r.answer}`)); return li; }),
        el("h3", "", "AI notes"), rows(recent.filter((e) => ["ai", "summary", "agent"].includes(e.kind)).slice(0, 8), trafficRow));
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
markSelected();
pollStatus().then(renderPanel); pollNetwork();
setInterval(pollNetwork, 400);
setInterval(pollStatus, 1000);
setInterval(renderPanel, 1500);
