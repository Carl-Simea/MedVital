// sync.js - MedVital, Spot 3 (NASA): sends the spacecraft's outbox to NASA.
//
// This file runs inside the Spacecraft spot's Cloudflare Worker.
// The Spacecraft spot calls syncOutbox(env) from their scheduled (cron) handler.
//
// What one call does:
//   1. Read up to 50 records from the D1 outbox, oldest first.
//   2. POST them to NASA_URL + "/batch".
//   3. NASA answers {"saved": [ids]}. Delete ONLY those ids from the outbox.
//
// Anything NASA did not confirm stays in the outbox and is sent again on the
// next run. If NASA answers 503 (link down) or the request fails, nothing is
// deleted, so during a blackout the outbox just grows.
//
// It is safe to call this often, or even twice at the same time: NASA ignores
// records it already has, and still confirms them.

// ---------------------------------------------------------------------------
// Match these with the Spacecraft spot
// ---------------------------------------------------------------------------
const D1_BINDING = "DB";              // name of the D1 binding in the Worker (env.DB)
const OUTBOX_TABLE = "outbox";        // outbox(id TEXT PRIMARY KEY, body TEXT, created_at TEXT)
const COL_ID = "id";                  // the record's id
const COL_BODY = "body";              // the whole record as JSON text
const COL_CREATED_AT = "created_at";  // when the row was written; decides "oldest first"

// Name of the id field inside each record. The full record shape lives in ONE
// place, nasa/record_format.py. This is the only part of it sync.js needs.
const RECORD_ID_FIELD = "id";

// ---------------------------------------------------------------------------
// Settings
// ---------------------------------------------------------------------------
const BATCH_SIZE = 50;                // records per run. Keep it at 100 or less (D1 allows 100 "?" per query).
const REQUEST_TIMEOUT_MS = 10000;     // stop waiting for NASA after 10 seconds

// ---------------------------------------------------------------------------
// The one function the Spacecraft spot calls
// ---------------------------------------------------------------------------
// It never throws. It returns a small summary you can log or show on the hub screen:
//   { linkUp: true,  sent: 50, confirmed: 50 }                  NASA saved the batch
//   { linkUp: false, sent: 50, confirmed: 0, problem: "..." }   blackout: nothing deleted
//   { linkUp: null,  sent: 0,  confirmed: 0 }                   outbox empty, NASA not contacted
//   { linkUp: null,  sent: 0,  confirmed: 0, problem: "..." }   set-up problem on the spacecraft side
export async function syncOutbox(env) {
  try {
    const db = env[D1_BINDING];
    const nasaUrl = String(env.NASA_URL || "").replace(/\/+$/, ""); // drop a trailing "/"
    if (!db) return report({ linkUp: null, sent: 0, confirmed: 0, problem: `no D1 binding called "${D1_BINDING}"` });
    if (!nasaUrl) return report({ linkUp: null, sent: 0, confirmed: 0, problem: "NASA_URL is not set" });

    // 1. Read up to BATCH_SIZE rows from the outbox, oldest first.
    const { results: rows } = await db
      .prepare(
        `SELECT ${COL_ID}, ${COL_BODY} FROM ${OUTBOX_TABLE}
         ORDER BY ${COL_CREATED_AT} ASC, ${COL_ID} ASC
         LIMIT ${BATCH_SIZE}`
      )
      .all();
    if (rows.length === 0) return { linkUp: null, sent: 0, confirmed: 0 }; // nothing to send

    // 2. Turn each row back into a record. Remember which outbox row every
    //    record id came from, so we can delete exactly the rows NASA confirms.
    const records = [];
    const outboxIdsByRecordId = new Map(); // record id -> outbox row id(s)
    for (const row of rows) {
      const record = readRecord(row);
      records.push(record);
      const recordId = String(record[RECORD_ID_FIELD]);
      if (!outboxIdsByRecordId.has(recordId)) outboxIdsByRecordId.set(recordId, []);
      outboxIdsByRecordId.get(recordId).push(row[COL_ID]);
    }

    // 3. POST the batch to NASA.
    let response;
    let answerText;
    try {
      response = await fetch(nasaUrl + "/batch", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ records }),
        signal: AbortSignal.timeout(REQUEST_TIMEOUT_MS),
      });
      answerText = await response.text();
    } catch (error) {
      // The request failed (no connection, timeout...). Delete nothing.
      return report({ linkUp: false, sent: records.length, confirmed: 0, problem: `could not reach NASA: ${error}` });
    }

    // 503 = link down. Any other error code is treated the same way: delete nothing.
    if (!response.ok) {
      return report({ linkUp: false, sent: records.length, confirmed: 0, problem: `NASA answered HTTP ${response.status}` });
    }

    // 4. Read NASA's answer: {"saved": [ids]}.
    let saved = null;
    try {
      saved = JSON.parse(answerText).saved;
    } catch (error) {
      // not JSON: handled just below
    }
    if (!Array.isArray(saved)) {
      return report({ linkUp: false, sent: records.length, confirmed: 0, problem: "NASA's answer had no saved list" });
    }

    // 5. Delete ONLY the rows whose record NASA confirmed.
    //    (An id NASA returns that was not in this batch is ignored.)
    const confirmedRowIds = new Set();
    for (const savedId of saved) {
      for (const rowId of outboxIdsByRecordId.get(String(savedId)) || []) {
        confirmedRowIds.add(rowId);
      }
    }
    if (confirmedRowIds.size > 0) {
      const placeholders = [...confirmedRowIds].map(() => "?").join(", ");
      await db
        .prepare(`DELETE FROM ${OUTBOX_TABLE} WHERE ${COL_ID} IN (${placeholders})`)
        .bind(...confirmedRowIds)
        .run();
    }

    // Anything not confirmed is still in the outbox and goes out again next run.
    return report({ linkUp: true, sent: records.length, confirmed: confirmedRowIds.size });
  } catch (error) {
    // A problem on the spacecraft side (for example the outbox table is missing).
    // Nothing that NASA did not confirm was deleted, so the next run just tries again.
    return report({ linkUp: null, sent: 0, confirmed: 0, problem: String(error) });
  }
}

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------

// Turn one outbox row back into the record to send.
function readRecord(row) {
  let record = null;
  try {
    record = JSON.parse(row[COL_BODY]);
  } catch (error) {
    // not JSON: handled just below
  }

  // A body that is not a JSON object can never be read as a record. Send it
  // wrapped instead of skipping it, so it is not lost and cannot clog the outbox.
  if (record === null || typeof record !== "object" || Array.isArray(record)) {
    return { [RECORD_ID_FIELD]: row[COL_ID], unreadableBody: row[COL_BODY] };
  }

  // The id inside the record should equal the outbox row id. If the record
  // has no usable id, use the row id, so NASA always has an id to confirm.
  const id = record[RECORD_ID_FIELD];
  const hasId = (typeof id === "string" && id !== "") || Number.isInteger(id);
  if (!hasId) record[RECORD_ID_FIELD] = row[COL_ID];
  return record;
}

// Log one line per sync (visible with `npx wrangler tail`) and pass the result on.
function report(result) {
  if (result.problem) console.warn("syncOutbox:", JSON.stringify(result));
  else console.log("syncOutbox:", JSON.stringify(result));
  return result;
}