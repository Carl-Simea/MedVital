// MedVital link to Earth, on Cloudflare: a Worker with a D1 database and Workers AI.
//
//   spacecraft hub --POST /outbox (daily batch, urgent alerts)--> [this Worker + D1] <--GET /pull-- NASA receiver
//
// * Nothing is lost: D1 keeps every record (INSERT OR IGNORE on the record id, so retries are harmless).
//   The hub deletes a record from its outbox only after this Worker confirms the id.
// * The link to Earth can be cut and restored (POST /link). While it is down, /outbox answers 503 and the
//   spacecraft keeps everything in its own outbox.
// * Workers AI words alerts and daily summaries (POST /ai) through the AI binding: no API token anywhere.
// * POST /reset {"confirm": "new mission"} empties the record (start.py --fresh).
// * Every route except /health needs the header  x-medvital-key: <MEDVITAL_KEY>.  MEDVITAL_KEY is a
//   Cloudflare secret (`wrangler secret put MEDVITAL_KEY`); it is never in the repository.

const MAX_BATCH = 500;
const MAX_BODY_BYTES = 5_000_000;
const AI_MODEL = "@cf/meta/llama-3.1-8b-instruct";
const AI_CALLS_PER_MINUTE = 30;
const SYSTEM = "You are MedVital, the health system on a crewed spacecraft. Write for an astronaut: short, calm, " +
  "plain language, no diagnosis. Keep every number exactly as given.";

// The same tables as migrations/0001_init.sql, created on first use. A deploy from the Cloudflare dashboard
// (GitHub connection) or `wrangler deploy` then needs no migration step: wrangler creates the D1 database.
const SCHEMA = [
  `CREATE TABLE IF NOT EXISTS records (seq INTEGER PRIMARY KEY AUTOINCREMENT, id TEXT NOT NULL UNIQUE,
     type TEXT NOT NULL, astronaut_id TEXT NOT NULL, body TEXT NOT NULL, received_at TEXT NOT NULL)`,
  "CREATE INDEX IF NOT EXISTS records_by_astronaut ON records (astronaut_id, type)",
  "CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL)",
  "CREATE TABLE IF NOT EXISTS ai_calls (minute TEXT PRIMARY KEY, n INTEGER NOT NULL)",
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
      .bind(key, value).run();
    return value;
  }
  const row = await env.DB.prepare("SELECT value FROM settings WHERE key = ?1").bind(key).first();
  return row ? row.value : null;
}

const linkUp = async (env) => (await setting(env, "link_up")) !== "0";

// ------------------------------------------------------------------------------------------- routes
async function outbox(request, env) {
  if (!(await linkUp(env))) return json({ error: "link down" }, 503);
  const text = await request.text();
  if (text.length > MAX_BODY_BYTES) return json({ error: "batch too large" }, 413);
  let payload;
  try { payload = JSON.parse(text); } catch { return json({ error: "not JSON" }, 400); }
  if (!payload || !Array.isArray(payload.records)) return json({ error: 'expected {"records": [...]}' }, 400);
  if (payload.records.length > MAX_BATCH) return json({ error: `at most ${MAX_BATCH} records per batch` }, 413);

  const now = new Date().toISOString();
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

async function pull(url, env) {
  const after = Math.max(0, parseInt(url.searchParams.get("after") || "0", 10) || 0);
  const limit = Math.min(MAX_BATCH, Math.max(1, parseInt(url.searchParams.get("limit") || "500", 10) || 500));
  const { results } = await env.DB.prepare("SELECT seq, body FROM records WHERE seq > ?1 ORDER BY seq LIMIT ?2")
    .bind(after, limit).all();
  return json({ records: results.map((r) => ({ seq: r.seq, record: JSON.parse(r.body) })),
                next: results.length ? results[results.length - 1].seq : after, more: results.length === limit });
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
  return json(out);
}

async function ai(request, env) {
  if (!env.AI) return json({ error: "Workers AI binding not available" }, 503);
  const minute = new Date().toISOString().slice(0, 16);
  const row = await env.DB.prepare(
    "INSERT INTO ai_calls (minute, n) VALUES (?1, 1) ON CONFLICT(minute) DO UPDATE SET n = n + 1 RETURNING n")
    .bind(minute).first();
  if (row && row.n > AI_CALLS_PER_MINUTE) return json({ error: "AI rate limit (demo)" }, 429);
  let body;
  try { body = await request.json(); } catch { return json({ error: "not JSON" }, 400); }
  const prompt = String(body.prompt || "").slice(0, 4000);
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

export default {
  async fetch(request, env) {
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
        case "GET /stats": return await stats(env);
        case "GET /link": return json({ up: await linkUp(env) });
        case "POST /link": {
          const body = await request.json().catch(() => ({}));
          if (typeof body.up !== "boolean") return json({ error: 'expected {"up": true|false}' }, 400);
          await setting(env, "link_up", body.up ? "1" : "0");
          return json({ up: body.up });
        }
        case "POST /ai": return await ai(request, env);
        case "POST /reset": {  // start.py --fresh: a new mission starts with an empty record on Earth too
          const body = await request.json().catch(() => ({}));
          if (body.confirm !== "new mission") return json({ error: 'expected {"confirm": "new mission"}' }, 400);
          await env.DB.batch([env.DB.prepare("DELETE FROM records"), env.DB.prepare("DELETE FROM settings")]);
          return json({ reset: true });
        }
        default: return json({ error: "not found" }, 404);
      }
    } catch (err) {
      return json({ error: String(err && err.message || err) }, 500);
    }
  },
};
