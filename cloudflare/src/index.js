// MedVital on Cloudflare: the link between the spacecraft and NASA, and the checker that watches it.
//
//   spacecraft hub --POST /outbox--> [ Worker + D1 ] --GET /pull--> NASA receiver
//                  --POST /heartbeat (every 3 s)-->   <--POST /heartbeat (every 3 s)--
//   DONKI (NASA space weather) --scheduled fetch--> D1 --GET /donki--> spacecraft
//
// * Nothing is lost: D1 keeps every record (INSERT OR IGNORE on the record id, so retries are harmless).
//   The hub deletes a record from its outbox only after this Worker confirms the id.
// * The link to NASA can be cut and restored (POST /link). While it is down, /pull answers 503, every
//   refused attempt is written to the link log, and the records wait in D1 until NASA gets through.
// * The checker: the hub and NASA report in every few seconds with their database counts. The Worker marks
//   anything that goes quiet as down, checks that the three databases agree (spacecraft confirmed = D1 =
//   NASA + waiting), and Workers AI writes the result in one plain sentence (numbers checked, at most once
//   a minute). Cloudflare cannot call into a private laptop or Codespace, so the parts report in to it.
// * Workers AI also words alerts and summaries for the spacecraft (POST /ai) through the AI binding.
// * POST /reset {"confirm": "new mission"} empties the mission (start.py --fresh).
// * Every route except /health needs the header  x-medvital-key: <MEDVITAL_KEY>.  MEDVITAL_KEY is a
//   Cloudflare secret; it is never in the repository.

const MAX_BATCH = 500;
const MAX_BODY_BYTES = 5_000_000;
const AI_MODEL = "@cf/meta/llama-3.1-8b-instruct";
const AI_CALLS_PER_MINUTE = 30;
const QUIET_AFTER_S = 10;        // a part that has not reported for this long is shown as down
const RETRY_S = 3;               // NASA retries every 3 s while the link is down (demo value)
const AI_LINE_EVERY_S = 60;      // Workers AI rewrites the checker sentence at most once a minute
const DONKI_STALE_S = 1800;      // fetch DONKI again after 30 minutes
// the address tools/fetch_nasa_data.py downloads from, then the older one
const DONKI_BASES = ["https://ccmc.gsfc.nasa.gov/DONKI-API/get", "https://kauai.ccmc.gsfc.nasa.gov/DONKI/WS/get"];
const SYSTEM = "You are MedVital, the health system on a crewed spacecraft. Write for an astronaut: short, calm, " +
  "plain language, no diagnosis. Keep every number exactly as given.";

// Created on first use, so a deploy needs no migration step (migrations/ documents the same schema).
const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS records (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
     type TEXT NOT NULL, astronaut_id TEXT NOT NULL, body TEXT NOT NULL, received_at TEXT NOT NULL)`,
  "CREATE INDEX IF NOT EXISTS records_by_astronaut ON records (astronaut_id, type)",
  "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
  "CREATE TABLE IF NOT EXISTS ai_calls (minute TEXT PRIMARY KEY, n INTEGER NOT NULL)",
  "CREATE TABLE IF NOT EXISTS nodes (node TEXT PRIMARY KEY, seen_at TEXT NOT NULL, report TEXT NOT NULL)",
  `CREATE TABLE IF NOT EXISTS link_log (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
     event TEXT NOT NULL, detail TEXT NOT NULL)`,
  `CREATE TABLE IF NOT EXISTS donki (id TEXT PRIMARY KEY, type TEXT NOT NULL, start TEXT NOT NULL,
     end_time TEXT, summary TEXT NOT NULL, link TEXT, fetched_at TEXT NOT NULL)`,
];
let schemaReady = false;
async function ensureSchema(env) {
  if (schemaReady) return;
  await env.DB.batch(SCHEMA.map((sql) => env.DB.prepare(sql)));
  schemaReady = true;
}

const json = (data, status = 200) => new Response(JSON.stringify(data), {
  status, headers: { "content-type": "application/json", "cache-control": "no-store" },
});
const nowIso = () => new Date().toISOString();
const secondsSince = (iso) => (iso ? (Date.now() - Date.parse(iso)) / 1000 : Infinity);

async function authorized(request, env) {
  const expected = env.MEDVITAL_KEY;
  if (!expected) return false; // no secret set: refuse everything rather than run open
  const given = request.headers.get("x-medvital-key") || "";
  const a = new TextEncoder().encode(given), b = new TextEncoder().encode(expected);
  if (a.byteLength !== b.byteLength) return false;
  return crypto.subtle.timingSafeEqual(a, b);
}

async function setting(env, key, value) {
  if (value !== undefined) {
    await env.DB.prepare("INSERT INTO settings (key, value) VALUES (?1, ?2) ON CONFLICT(key) DO UPDATE SET value = ?2")
      .bind(key, String(value)).run();
    return value;
  }
  const row = await env.DB.prepare("SELECT value FROM settings WHERE key = ?1").bind(key).first();
  return row ? row.value : null;
}

const linkUp = async (env) => (await setting(env, "link_up")) !== "0";
const logLink = (env, event, detail) =>
  env.DB.prepare("INSERT INTO link_log (at, event, detail) VALUES (?1, ?2, ?3)").bind(nowIso(), event, detail).run();

// ------------------------------------------------------------------------------------------- spacecraft side
async function outbox(request, env) {
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return json({ error: "batch too large" }, 413);
  let payload;
  try { payload = JSON.parse(text); } catch { return json({ error: "not JSON" }, 400); }
  if (!payload || !Array.isArray(payload.records)) return json({ error: 'expected {"records": [...]}' }, 400);
  if (payload.records.length > MAX_BATCH) return json({ error: `at most ${MAX_BATCH} records per batch` }, 413);

  const now = nowIso();
  const saved = [], stmts = [];
  const insert = env.DB.prepare(
    "INSERT OR IGNORE INTO records (id, type, astronaut_id, body, received_at) VALUES (?1, ?2, ?3, ?4, ?5)");
  for (const r of payload.records) {
    const id = r && (typeof r.id === "string" || Number.isInteger(r.id)) ? String(r.id) : "";
    if (!id) continue; // without an id a record cannot be confirmed, so the spacecraft keeps it
    stmts.push(insert.bind(id, String(r.type || "unknown"), String(r.astronautId || "unknown"), JSON.stringify(r), now));
    saved.push(id);
  }
  for (let i = 0; i < stmts.length; i += 50) await env.DB.batch(stmts.slice(i, i + 50));
  // only reached after D1 committed every batch: each confirmed id really is stored
  return json({ saved });
}

// ------------------------------------------------------------------------------------------- NASA side
async function pull(url, env) {
  if (!(await linkUp(env))) {
    const waiting = await waitingForNasa(env);
    await logLink(env, "refused", `NASA tried to pull; link to NASA is down; ${waiting} record(s) wait in D1; retry in ${RETRY_S} s`);
    return json({ error: "link to NASA down", retryInS: RETRY_S, waiting }, 503);
  }
  const after = Math.max(0, parseInt(url.searchParams.get("after") || "0", 10) || 0);
  const limit = Math.min(MAX_BATCH, Math.max(1, parseInt(url.searchParams.get("limit") || "500", 10) || 500));
  const { results } = await env.DB.prepare("SELECT seq, body FROM records WHERE seq > ?1 ORDER BY seq LIMIT ?2")
    .bind(after, limit).all();
  return json({ records: results.map((r) => ({ seq: r.seq, record: JSON.parse(r.body) })),
                next: results.length ? results[results.length - 1].seq : after, more: results.length === limit });
}

async function waitingForNasa(env) {
  const nasa = await nodeReport(env, "nasa");
  const cursor = nasa ? Number(nasa.report.cursor || 0) : 0;
  const row = await env.DB.prepare("SELECT COUNT(*) AS n FROM records WHERE seq > ?1").bind(cursor).first();
  return row ? row.n : 0;
}

async function stats(env) {
  const { results } = await env.DB.prepare(
    "SELECT astronaut_id, type, COUNT(*) AS n FROM records GROUP BY astronaut_id, type").all();
  const out = { total: 0, by_astronaut: {}, by_type: {}, by_astronaut_and_type: {} };
  for (const r of results) {
    out.total += r.n;
    out.by_astronaut[r.astronaut_id] = (out.by_astronaut[r.astronaut_id] || 0) + r.n;
    out.by_type[r.type] = (out.by_type[r.type] || 0) + r.n;
    (out.by_astronaut_and_type[r.astronaut_id] ||= {})[r.type] = r.n;
  }
  return out;
}

// ------------------------------------------------------------------------------------------- the checker
async function heartbeat(request, env, ctx) {
  const body = await request.json().catch(() => null);
  const node = body && String(body.node || "");
  if (!["hub", "nasa"].includes(node)) return json({ error: 'expected {"node": "hub" | "nasa", ...}' }, 400);
  const report = JSON.stringify(body.report || {}).slice(0, 20000);
  await env.DB.prepare(
    "INSERT INTO nodes (node, seen_at, report) VALUES (?1, ?2, ?3) ON CONFLICT(node) DO UPDATE SET seen_at = ?2, report = ?3")
    .bind(node, nowIso(), report).run();
  return json(await check(env, ctx));
}

async function nodeReport(env, node) {
  const row = await env.DB.prepare("SELECT seen_at, report FROM nodes WHERE node = ?1").bind(node).first();
  return row ? { seenAt: row.seen_at, report: JSON.parse(row.report) } : null;
}

/** One full check: every part's status, the three databases compared, the link log, a plain sentence. */
async function check(env, ctx) {
  const [hub, nasa, up, d1, donkiRow, logRows] = await Promise.all([
    nodeReport(env, "hub"), nodeReport(env, "nasa"), linkUp(env),
    env.DB.prepare("SELECT COUNT(*) AS n, COALESCE(MAX(seq), 0) AS maxSeq FROM records").first(),
    env.DB.prepare("SELECT MAX(fetched_at) AS at, COUNT(*) AS n FROM donki").first(),
    env.DB.prepare("SELECT at, event, detail FROM link_log ORDER BY id DESC LIMIT 12").all(),
  ]);
  const part = (r) => (r ? { up: secondsSince(r.seenAt) <= QUIET_AFTER_S, seenS: Math.round(secondsSince(r.seenAt)) }
                         : { up: false, seenS: null });
  const hubR = hub ? hub.report : {}, nasaR = nasa ? nasa.report : {};
  const d1Total = d1 ? d1.n : 0;
  const nasaCursor = Number(nasaR.cursor || 0);
  const pending = d1 ? Math.max(0, d1.maxSeq - nasaCursor) : 0;
  const hubConfirmed = Number(hubR.confirmed ?? NaN), nasaTotal = Number(nasaR.total ?? NaN);
  const db = {
    spacecraftConfirmed: Number.isFinite(hubConfirmed) ? hubConfirmed : null,
    spacecraftWaiting: hubR.outbox ?? null,
    cloudflare: d1Total,
    nasa: Number.isFinite(nasaTotal) ? nasaTotal : null,
    waitingAtCloudflare: pending,
  };
  // the spacecraft may have confirmed more than D1 holds only if D1 lost something; NASA + waiting = D1
  db.spacecraftMatches = db.spacecraftConfirmed === null ? null : db.spacecraftConfirmed <= d1Total;
  db.nasaMatches = db.nasa === null ? null : db.nasa + pending === d1Total;
  db.ok = db.spacecraftMatches !== false && db.nasaMatches !== false;
  const devices = Array.isArray(hubR.devices) ? hubR.devices : [];
  const facts = {
    at: nowIso(),
    parts: {
      cloudflare: { up: true },
      d1: { up: Boolean(d1) },
      hub: part(hub),
      nasa: part(nasa),
      agent: hubR.agent ? { up: Boolean(hubR.agent.up), model: hubR.agent.model || null } : { up: false },
      donki: { up: Boolean(donkiRow && donkiRow.at) && secondsSince(donkiRow.at) < 3 * DONKI_STALE_S,
               fetchedAt: donkiRow ? donkiRow.at : null, events: donkiRow ? donkiRow.n : 0 },
      devices: devices.map((d) => ({ id: d.id, up: Boolean(d.up), seenS: d.seenS ?? null })),
    },
    link: { up, retryEveryS: RETRY_S, lastNasaTry: nasaR.lastTry || null, nasaError: nasaR.lastError || null },
    db,
    log: logRows.results,
  };
  facts.sentence = await aiSentence(env, ctx, facts);
  return facts;
}

function ruleSentence(f) {
  const devs = f.parts.devices, upDevs = devs.filter((d) => d.up).length;
  const bits = [`${upDevs} of ${devs.length} wearables reporting`,
    f.parts.hub.up ? "spacecraft hub reporting" : "spacecraft hub silent",
    f.parts.nasa.up ? "NASA reporting" : "NASA silent",
    f.link.up ? "link to NASA up" : `link to NASA down (${f.db.waitingAtCloudflare} records waiting in Cloudflare)`];
  const dbText = f.db.ok
    ? `databases agree: Cloudflare holds ${f.db.cloudflare}, NASA ${f.db.nasa ?? "?"} plus ${f.db.waitingAtCloudflare} waiting`
    : `databases do not agree: spacecraft confirmed ${f.db.spacecraftConfirmed}, Cloudflare ${f.db.cloudflare}, NASA ${f.db.nasa}`;
  return `${bits.join(", ")}; ${dbText}.`;
}

/** Workers AI words the check at most once a minute; any changed number keeps the rule sentence. */
async function aiSentence(env, ctx, facts) {
  const rule = ruleSentence(facts);
  const cached = await setting(env, "ai_line");
  const prev = cached ? JSON.parse(cached) : null;
  const sameFacts = prev && prev.rule === rule;
  if (prev && sameFacts) return { text: prev.text, source: prev.source, at: prev.at };
  if (env.AI && (!prev || secondsSince(prev.at) > AI_LINE_EVERY_S)) {
    const job = (async () => {
      let text = rule, source = "rules";
      try {
        const out = await env.AI.run(AI_MODEL, { messages: [
          { role: "system", content: "You monitor the network of a crewed Mars mission. One short sentence for the flight " +
            "surgeon. Keep every number exactly as given. No diagnosis." },
          { role: "user", content: `Rewrite as one sentence: ${rule}` }] });
        const t = (out && out.response || "").trim();
        const nums = rule.match(/\d+(?:\.\d+)?/g) || [];
        if (t && nums.every((n) => t.includes(n))) { text = t; source = "Workers AI"; }
      } catch { /* no Workers AI (e.g. wrangler dev --local): keep the rule sentence */ }
      await setting(env, "ai_line", JSON.stringify({ rule, text, source, at: nowIso() }));
    })();
    if (ctx && ctx.waitUntil) ctx.waitUntil(job); else await job;
  }
  return { text: rule, source: "rules", at: nowIso() };
}

// ------------------------------------------------------------------------------------------- DONKI
const DONKI_TYPES = ["FLR", "CME", "SEP", "GST", "IPS"];

function donkiRow(type, r) {
  const id = r.flrID || r.activityID || r.sepID || r.gstID || r.activityID;
  const start = r.beginTime || r.startTime || r.eventTime;
  if (!id || !start) return null;
  let summary;
  if (type === "FLR") summary = `Class ${r.classType || "?"} solar flare`;
  else if (type === "CME") {
    const speed = Math.max(0, ...((r.cmeAnalyses || []).map((a) => a.speed || 0)));
    summary = speed ? `Coronal mass ejection, ${Math.round(speed)} km/s` : "Coronal mass ejection";
  } else if (type === "SEP") summary = "Solar energetic particle event";
  else if (type === "GST") {
    const kp = Math.max(0, ...((r.allKpIndex || []).map((k) => k.kpIndex || 0)));
    summary = `Geomagnetic storm at Earth (Kp ${kp})`;
  } else summary = `Interplanetary shock at ${r.location || "?"}`;
  // only flares report an end time; nothing else gets a made-up duration
  return { id, type, start, end: type === "FLR" ? (r.endTime || null) : null, summary, link: r.link || null };
}

async function fetchDonki(env) {
  const end = new Date(), start = new Date(Date.now() - 30 * 86400_000);
  const d = (x) => x.toISOString().slice(0, 10);
  const rows = [];
  for (const type of DONKI_TYPES) {
    let list = null, lastError = "";
    for (const base of DONKI_BASES) {
      try {
        const res = await fetch(`${base}/${type}?startDate=${d(start)}&endDate=${d(end)}`,
          { headers: { accept: "application/json" }, cf: { cacheTtl: 600 } });
        if (!res.ok) { lastError = `HTTP ${res.status}`; continue; }
        list = await res.json();
        break;
      } catch (e) { lastError = String(e.message || e); }
    }
    if (list === null) throw new Error(`DONKI ${type}: ${lastError}`);
    for (const r of Array.isArray(list) ? list : []) {
      const row = donkiRow(type, r);
      if (row) rows.push(row);
    }
  }
  const at = nowIso();
  const stmt = env.DB.prepare(`INSERT INTO donki (id, type, start, end_time, summary, link, fetched_at)
    VALUES (?1, ?2, ?3, ?4, ?5, ?6, ?7) ON CONFLICT(id) DO UPDATE SET fetched_at = ?7, end_time = ?4`);
  for (let i = 0; i < rows.length; i += 50) {
    await env.DB.batch(rows.slice(i, i + 50).map((r) => stmt.bind(r.id, r.type, r.start, r.end, r.summary, r.link, at)));
  }
  await setting(env, "donki_fetched", at);
  return rows.length;
}

async function donki(env, ctx) {
  const last = await setting(env, "donki_fetched");
  let error = null;
  if (secondsSince(last) > DONKI_STALE_S) {
    const job = fetchDonki(env).then(() => setting(env, "donki_error", "")).catch((e) => setting(env, "donki_error", String(e.message || e)));
    if (last && ctx && ctx.waitUntil) ctx.waitUntil(job); else await job;
  }
  error = (await setting(env, "donki_error")) || null;
  const { results } = await env.DB.prepare(
    "SELECT id, type, start, end_time AS end, summary, link FROM donki ORDER BY start DESC LIMIT 60").all();
  return json({ source: "NASA DONKI (CCMC), fetched by Cloudflare", fetchedAt: await setting(env, "donki_fetched"), error, events: results });
}

// ------------------------------------------------------------------------------------------- Workers AI
async function ai(request, env) {
  if (!env.AI) return json({ error: "Workers AI binding not available" }, 503);
  const minute = new Date().toISOString().slice(0, 16);
  const row = await env.DB.prepare(
    "INSERT INTO ai_calls (minute, n) VALUES (?1, 1) ON CONFLICT(minute) DO UPDATE SET n = n + 1 RETURNING n")
    .bind(minute).first();
  if (row && row.n > AI_CALLS_PER_MINUTE) return json({ error: "AI rate limit (demo)" }, 429);
  let body;
  try { body = await request.json(); } catch { return json({ error: "not JSON" }, 400); }
  const prompt = String(body.prompt || "").slice(0, 6000);
  if (!prompt) return json({ error: "prompt is empty" }, 400);
  let out;
  try {
    out = await env.AI.run(AI_MODEL, { messages: [{ role: "system", content: SYSTEM }, { role: "user", content: prompt }] });
  } catch (err) {
    // e.g. `wrangler dev --local` has no Workers AI: the spacecraft then keeps its own rule-based wording
    return json({ error: `Workers AI unavailable: ${String(err && err.message || err)}` }, 503);
  }
  return json({ text: (out && out.response) || "", model: AI_MODEL });
}

// ------------------------------------------------------------------------------------------- router
export default {
  async fetch(request, env, ctx) {
    const url = new URL(request.url);
    const route = `${request.method} ${url.pathname.replace(/\/+$/, "") || "/"}`;
    if (route === "GET /" || route === "GET /health") {
      return json({ service: "medvital-link", ok: true, keySet: Boolean(env.MEDVITAL_KEY), ai: Boolean(env.AI) });
    }
    if (!(await authorized(request, env))) return json({ error: "missing or wrong x-medvital-key" }, 401);
    try {
      await ensureSchema(env);
      switch (route) {
        case "POST /outbox": return await outbox(request, env);
        case "GET /pull": return await pull(url, env);
        case "GET /stats": return json(await stats(env));
        case "POST /heartbeat": return await heartbeat(request, env, ctx);
        case "GET /checker": return json(await check(env, ctx));
        case "GET /donki": return await donki(env, ctx);
        case "GET /link": return json({ up: await linkUp(env) });
        case "POST /link": {
          const body = await request.json().catch(() => ({}));
          if (typeof body.up !== "boolean") return json({ error: 'expected {"up": true|false}' }, 400);
          const was = await linkUp(env);
          await setting(env, "link_up", body.up ? "1" : "0");
          if (was !== body.up) {
            await logLink(env, body.up ? "restored" : "cut",
              body.up ? `Link to NASA restored; ${await waitingForNasa(env)} record(s) waiting go through now`
                      : "Link to NASA cut; records wait in D1, NASA retries every 3 s");
          }
          return json({ up: body.up });
        }
        case "POST /ai": return await ai(request, env);
        case "POST /reset": {  // start.py --fresh: a new mission starts with an empty record on Earth too
          const body = await request.json().catch(() => ({}));
          if (body.confirm !== "new mission") return json({ error: 'expected {"confirm": "new mission"}' }, 400);
          await env.DB.batch(["records", "nodes", "link_log", "ai_calls"].map((t) => env.DB.prepare(`DELETE FROM ${t}`))
            .concat([env.DB.prepare("DELETE FROM settings WHERE key IN ('link_up', 'ai_line')")]));
          return json({ reset: true });
        }
        default: return json({ error: "not found" }, 404);
      }
    } catch (err) {
      return json({ error: String(err && err.message || err) }, 500);
    }
  },

  // Cron trigger (wrangler.jsonc): keep the space weather fresh even when nobody is watching.
  async scheduled(controller, env, ctx) {
    await ensureSchema(env);
    ctx.waitUntil(fetchDonki(env).then(() => setting(env, "donki_error", ""))
      .catch((e) => setting(env, "donki_error", String(e.message || e))));
  },
};
