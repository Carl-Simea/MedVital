// MedVital astronaut tab = the wearable (simulated in software) + the astronaut's MedVital station.
// The wearable fakes the numbers from the spacecraft's ready-made scenarios and sends a burst every 5 s.
// The station shows what the SPACECRAFT stored and double-checked, not what the wearable thinks it sent.
import { api, el, spark } from "/apps/shared/hub.js";

const $ = (id) => document.getElementById(id);
const id = new URLSearchParams(location.search).get("id");

const PATTERNS = {             // vibration patterns (ms on/off) from the team plan
  RETURN_NOW: { vib: [800, 250, 800, 250, 800], text: "3 long buzzes, repeating until you are back inside" },
  CHECK_VITALS: { vib: [180, 120, 180], text: "2 short buzzes" },
  INFO: { vib: [160], text: "1 short buzz" },
};
const CHIPS = ["Why did it buzz?", "Can I go outside?", "How is my radiation?", "How did I sleep?", "How is my heart?"];

let cfg, me, key, view = null;
let scenario = "normal", running = false, timer = null;
let seq = 0, totalDose = 0, solarActive = false, glitchNext = false;
const queue = [];                      // bursts waiting to be delivered (link to the spacecraft down)
let shownAlert = null;

// ------------------------------------------------------------------ start
if (!id) showPicker(); else start();

async function showPicker() {
  $("picker").hidden = false;
  try {
    const crew = await api("/hub/crew");
    $("pickList").replaceChildren(...crew.map((a) => {
      const link = el("a"); link.href = `?id=${encodeURIComponent(a.id)}`;
      link.append(el("b", "", a.name), el("span", "", `${a.role} · resting heart rate ${a.profile.resting_hr} bpm`));
      return link;
    }));
  } catch { $("pickList").textContent = "Cannot reach the spacecraft hub. Is python start.py running?"; }
}

async function start() {
  $("station").hidden = false;
  try {
    cfg = await api("/hub/config");
    me = await api("/hub/pair", { astronautId: id });           // docking hands the wearable its key
    key = me.deviceKey;
  } catch (e) { $("name").textContent = "Cannot reach the spacecraft hub"; $("role").textContent = String(e.message); return; }
  document.title = `${me.name} · MedVital`;
  $("name").textContent = me.name;
  $("role").textContent = `${me.profile.role} · pre-flight baseline: resting heart rate ${me.profile.resting_hr} bpm, blood oxygen ${me.profile.spo2}%`;
  $("body3d").href = `/body/?astronaut=${encodeURIComponent(id)}`;
  $("chips").replaceChildren(...CHIPS.map((q) => { const b = el("button", "", q); b.type = "button"; b.onclick = () => ask(q); return b; }));
  await refresh();
  const last = view && view.latest;          // continue where this wearable left off
  if (last) { seq = last.seq || view.burstCount; totalDose = last.total_dose || 0; }
  bindControls();
  setInterval(refresh, 2500);
}

// ------------------------------------------------------------------ the wearable
function gauss(mean, sd) {
  const u = 1 - Math.random(), v = Math.random();
  return mean + sd * Math.sqrt(-2 * Math.log(u)) * Math.cos(2 * Math.PI * v);
}

function makeBurst() {
  const s = cfg.scenarios[scenario];
  const p = me.profile;
  let hr = p.resting_hr + gauss(...s.hrOffset);
  const spo2 = Math.min(100, p.spo2 + gauss(...s.spo2Offset));
  let dose = Math.max(0, gauss(...s.doseRate));
  if (solarActive) {             // outside the habitat the full spike hits; inside, the shielding takes most of it
    const f = cfg.scenarios.solar_event;
    dose *= s.state === "spacewalk" ? f.doseFactor : f.doseFactor * f.shieldedFraction;
  }
  if (glitchNext) { hr = 240; glitchNext = false; }          // a sensor glitch: physically impossible value
  totalDose += (dose * cfg.missionMinutesPerBurst) / 60 / 1000;   // µSv/h × h → mSv
  seq += 1;
  return {
    astronautId: id, deviceKey: key, seq, scenario, time: new Date().toISOString(),
    heartRate: Math.round(hr), spo2: Math.round(spo2 * 10) / 10, state: s.state,
    doseRate: Math.round(dose * 10) / 10, totalDose: Math.round(totalDose * 10000) / 10000,
  };
}

async function tick() {
  queue.push(makeBurst());
  await flush();
}

async function flush() {
  while (queue.length) {
    const b = queue[0];
    let reply;
    try {
      reply = await api("/hub/burst", b);
    } catch (e) {
      if (e.status === 401 || e.status === 400) { queue.shift(); showSending(`Burst #${b.seq} refused: ${e.message}`); continue; }
      setWear("buffer", `Spacecraft unreachable: ${queue.length} burst(s) held`);
      return;                                   // keep them; try again next tick, in order
    }
    queue.shift();
    solarActive = !!(reply.spaceWeather && reply.spaceWeather.solarEventActive);
    setWear("on", "Sending");
    showSending(`#${b.seq}  ${b.heartRate} bpm · ${b.spo2}% · ${b.doseRate} µSv/h · ${b.state}` +
      (reply.quality !== "valid" ? `  →  flagged by the spacecraft: ${reply.checkNote}` : "  →  stored"));
    $("wearCount").textContent = `${b.seq} bursts sent`;
    if (reply.alert) onAlert(reply.alert, reply.message, reply.alertId);
  }
}

function setWear(cls, text) { const s = $("wearState"); s.className = "wear-state " + cls; s.textContent = text; }
function showSending(text) { $("sending").textContent = text; }

function power(on) {
  running = on;
  clearInterval(timer);
  $("power").textContent = on ? "Take off wearable" : "Put on wearable";
  $("power").classList.toggle("on", on);
  if (on) { unlockAudio(); tick(); timer = setInterval(tick, cfg.burstSeconds * 1000); setWear("on", "Sending"); }
  else setWear("", "Off");
}

function setScenario(name) {
  scenario = name;
  document.querySelectorAll("[data-scenario]").forEach((b) => b.setAttribute("aria-pressed", String(b.dataset.scenario === name)));
}

async function solarEvent() {
  try {
    const r = await api("/hub/space-weather/replay", {});
    solarActive = true;
    showSending(`Solar event replayed from NASA DONKI: ${r.event}`);
  } catch (e) { showSending(`Could not replay the solar event: ${e.message}`); }
}

async function fakeDevice() {
  const b = { ...makeBurst(), deviceKey: "stolen-" + Math.random().toString(36).slice(2, 8) };
  seq -= 1;                                          // a fake device's burst is not one of ours
  try { await api("/hub/burst", b); showSending("The fake burst got through?!"); }
  catch (e) { showSending(`Fake device blocked by the private network (${e.message}).`); }
}

function bindControls() {
  $("power").onclick = () => power(!running);
  document.querySelectorAll("[data-scenario]").forEach((b) => (b.onclick = () => setScenario(b.dataset.scenario)));
  $("solarKey").onclick = solarEvent;
  $("glitchKey").onclick = () => { glitchNext = true; showSending("Next burst carries a sensor glitch."); };
  $("tamperKey").onclick = fakeDevice;
  document.addEventListener("keydown", (e) => {
    if (e.target.closest("input, textarea")) return;
    const map = { 1: "normal", 2: "sleep", 3: "exercise", 4: "spacewalk", 5: "hr_spike" };
    if (map[e.key]) setScenario(map[e.key]);
    else if (e.key === "6") solarEvent();
    else if (e.key.toLowerCase() === "g") $("glitchKey").click();
    else if (e.key.toLowerCase() === "t") fakeDevice();
  });
  $("alertAck").onclick = ackAlert;
  $("writeSummary").onclick = async () => {
    try { await api(`/hub/summary/${id}`, {}); refresh(); } catch (e) { $("summary").textContent = e.message; }
  };
  $("labs").onsubmit = sendLabs;
  $("ask").onsubmit = (e) => { e.preventDefault(); const q = $("q").value.trim(); if (q) ask(q); $("q").value = ""; };
}

// ------------------------------------------------------------------ alerts: vibration, sound, colour
let audio = null;
function unlockAudio() { try { audio = audio || new AudioContext(); audio.resume(); } catch { audio = null; } }
function beep(pattern) {
  if (!audio) return;
  let t = audio.currentTime;
  pattern.forEach((ms, i) => {
    if (i % 2 === 0) {
      const o = audio.createOscillator(), g = audio.createGain();
      o.frequency.value = pattern.length > 3 ? 660 : 880;
      g.gain.setValueAtTime(0.15, t); g.gain.setValueAtTime(0, t + ms / 1000);
      o.connect(g).connect(audio.destination); o.start(t); o.stop(t + ms / 1000);
    }
    t += ms / 1000;
  });
}

function onAlert(code, message, alertId) {
  const p = PATTERNS[code] || PATTERNS.INFO;
  if (navigator.vibrate) navigator.vibrate(p.vib);       // a real phone actually vibrates
  beep(p.vib);
  document.body.classList.remove("flash"); void document.body.offsetWidth; document.body.classList.add("flash");
  if (shownAlert && shownAlert.id === alertId) return;   // RETURN_NOW repeats every burst: buzz, don't redraw
  shownAlert = { id: alertId, code };
  const box = $("alert");
  box.className = "alert " + code;
  $("alertCode").textContent = code.replace("_", " ");
  $("alertMsg").textContent = message || "";
  $("alertPattern").textContent = `Wearable: ${p.text}`;
  $("alertAck").textContent = code === "RETURN_NOW" ? "Heading back inside" : "OK";
  box.hidden = false;
  if (code === "INFO") setTimeout(() => { if (shownAlert && shownAlert.id === alertId) closeAlert(); }, 5000);
}

function closeAlert() { $("alert").hidden = true; shownAlert = null; }

async function ackAlert() {
  const a = shownAlert;
  if (a && a.code === "RETURN_NOW") setScenario("normal");      // back inside: the next burst ends RETURN_NOW
  closeAlert();
  if (a && a.id) api(`/hub/alerts/${encodeURIComponent(a.id)}/ack`, {}).catch(() => {});
}

// ------------------------------------------------------------------ station (reads the spacecraft)
async function refresh() {
  try {
    view = await api(`/hub/astronauts/${encodeURIComponent(id)}`);
    $("link").className = "pill ok"; $("link").textContent = "Spacecraft connected";
  } catch {
    $("link").className = "pill bad"; $("link").textContent = "Spacecraft unreachable";
    return;
  }
  drawVitals(); drawRadiation(); drawBody(); drawSummary();
  const wx = view.spaceWeather.active;
  solarActive = !!wx;
  $("wx").className = "pill " + (wx ? "storm" : "quiet");
  $("wx").textContent = wx ? "Solar event active" : "Space weather: quiet";
  $("wx").title = wx ? wx.summary : "";
}

function allowance(state) { return cfg.hrAllowanceBpm[state] ?? 40; }

function drawVitals() {
  const p = view.profile, b = view.bursts.slice(-60), last = view.latest;
  const valid = (r, k) => (r.quality === "valid" ? r[k] : null);
  $("hr").textContent = last ? Math.round(last.heart_rate) : "–";
  $("spo2").textContent = last ? Math.round(last.spo2) : "–";
  document.querySelector(".vital.heart").classList.toggle("flagged", !!last && last.quality !== "valid");
  document.querySelector(".vital.oxygen").classList.toggle("flagged", !!last && last.quality !== "valid");
  const state = last ? last.state : "awake";
  $("hrBase").textContent = last && last.quality !== "valid" ? `Flagged: ${last.check_note}`
    : `Baseline ${p.resting_hr} bpm · your range while ${state}: up to ${p.resting_hr + allowance(state)} bpm`;
  $("spo2Base").textContent = `Baseline ${p.spo2}% · check below ${p.spo2 - cfg.spo2DropPct}%`;
  spark($("hrChart"), b.map((r) => valid(r, "heart_rate")), { color: "#d6336c", band: [p.resting_hr - 8, p.resting_hr + allowance(state)], baseline: p.resting_hr });
  spark($("spo2Chart"), b.map((r) => valid(r, "spo2")), { color: "#12917f", band: [p.spo2 - cfg.spo2DropPct, 100], baseline: p.spo2, max: 100 });
}

function setGauge(gid, pct, label) {
  const g = $(gid), fill = g.querySelector(".fill");
  fill.style.strokeDashoffset = String(314.16 * (1 - Math.min(100, pct) / 100));
  g.classList.toggle("warn", pct >= 50 && pct < 80);
  g.classList.toggle("over", pct >= 80);
  g.querySelector("b").textContent = label;
}

function drawRadiation() {
  const r = view.radiation, L = cfg.limits;
  setGauge("gEva", r.evaPct, `${Math.round(r.evaPct)}%`);
  setGauge("gEvent", r.eventPct, `${r.eventPct.toFixed(1)}%`);
  setGauge("gCareer", r.careerPct, `${r.careerPct.toFixed(1)}%`);
  const rate = view.latest ? `${view.latest.dose_rate.toFixed(1)} µSv/h now · ` : "";
  $("radLine").textContent = `${rate}spacewalk ${r.evaMsv.toFixed(2)} of ${r.evaBudgetMsv} mSv (demo budget) · ` +
    `career ${r.careerMsv.toFixed(1)} of ${L.career_msv.value} mSv (NASA limit) · solar event limit ${L.solar_event_msv.value} mSv`;
}

function zone(name, cls, text) {
  $("z" + name).setAttribute("class", "zone " + cls);
  const li = $("l" + name); li.className = cls; li.querySelector("b").textContent = text;
}

function drawBody() {
  const last = view.latest, p = view.profile, t = view.today, r = view.radiation;
  const recent = (a) => a && a.status === "active" && Date.now() - new Date(a.time) < 60000;
  const vit = view.alerts.find((a) => a.code === "CHECK_VITALS" && recent(a));
  if (!last) zone("Heart", "", "No data");
  else if (vit) zone("Heart", "bad", vit.reason === "spo2" ? "Low oxygen" : "Check vitals");
  else if (last.quality === "valid" && last.heart_rate > p.resting_hr + allowance(last.state)) zone("Heart", "warn", "High for you");
  else zone("Heart", "ok", "Within your range");

  if (!t) zone("Bone", "", "No data");
  else zone("Bone", t.exerciseMinutes >= t.exerciseTargetMinutes ? "ok" : "warn", `Exercise ${t.exerciseMinutes}/${t.exerciseTargetMinutes} min`);

  const rn = view.alerts.find((a) => a.code === "RETURN_NOW" && a.status === "active");
  if (rn) zone("Rad", "bad", "Go back inside");
  else if (view.spaceWeather.active || r.evaPct >= 50) zone("Rad", "warn", view.spaceWeather.active ? "Solar event" : `${Math.round(r.evaPct)}% of spacewalk budget`);
  else zone("Rad", last ? "ok" : "", last ? "Within budget" : "No data");

  if (!t || !t.sleepHours) zone("Sleep", "", "No sleep logged today");
  else zone("Sleep", t.sleepDebtHours > 1 ? "warn" : "ok", `${t.sleepHours} h slept`);
}

function drawSummary() {
  const s = view.lastSummary, box = $("summary");
  if (!s) return;
  const f = s.facts;
  const facts = el("div", "facts");
  for (const [v, l] of [[`${f.sleepHours} h`, "sleep"], [`${f.exerciseMinutes} min`, "exercise"], [`${f.doseMsv} mSv`, "radiation"], [f.avgAwakeHr ?? "–", "avg awake bpm"]]) {
    const d = el("div"); d.append(el("b", "", String(v)), el("span", "", l)); facts.append(d);
  }
  box.replaceChildren(el("p", "meta", `Mission day ${s.mission_day} · worded by ${s.ai_source} · ${s.check_note}`), facts, el("p", "", s.text));
}

// ------------------------------------------------------------------ lab results and the onboard agent
async function sendLabs(e) {
  e.preventDefault();
  const body = {};
  for (const input of e.target.querySelectorAll("input")) if (input.value !== "") body[input.name] = Number(input.value);
  if (!Object.keys(body).length) { $("labsMsg").textContent = "Enter at least one result."; return; }
  try { await api(`/hub/labs/${id}`, body); $("labsMsg").textContent = "Sent to the spacecraft. NASA gets a copy over the link."; e.target.reset(); }
  catch (err) { $("labsMsg").textContent = `Not sent: ${err.message}`; }
}

function say(cls, text, source) {
  const m = el("div", "msg " + cls, text);
  if (source) m.append(el("small", "", source));
  $("chat").append(m); $("chat").scrollTop = $("chat").scrollHeight;
}

async function ask(q) {
  say("me", q);
  try { const r = await api(`/hub/agent/${id}`, { question: q }); say("bot", r.answer, r.source); }
  catch (e) { say("bot", `The onboard agent did not answer: ${e.message}`); }
}
