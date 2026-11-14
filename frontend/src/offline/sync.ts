import type { ApiClient } from "../api/client";
import { isHealthObservation } from "../domain/guards";
import type { ObservationStore } from "./store";

export interface SyncResult {
  pushed: number; // accepted or already-known observations removed from the outbox
  rejected: number; // refused by the server; kept locally with a reason
  pulled: number; // new observations stored from the server
  invalid: number; // server payloads that failed the structural guard and were ignored
}

/**
 * One push-then-pull cycle. Safe to repeat at any time: observations are immutable and keyed
 * by id, so retries after a dropped connection never duplicate data. Rejects on network errors,
 * leaving the outbox and cursor untouched so the next attempt resumes cleanly.
 */
export async function syncOnce(
  store: ObservationStore,
  api: ApiClient,
  options: { batchSize?: number } = {},
): Promise<SyncResult> {
  const batchSize = options.batchSize ?? 200;
  const deviceId = await store.getDeviceId();
  const result: SyncResult = { pushed: 0, rejected: 0, pulled: 0, invalid: 0 };

  const pending = await store.outbox("pending");
  for (let i = 0; i < pending.length; i += batchSize) {
    const batch = pending.slice(i, i + batchSize);
    const response = await api.syncPush(
      deviceId,
      batch.map((entry) => entry.observation),
    );
    const synced = [...response.accepted, ...response.duplicates];
    await store.markSynced(synced);
    result.pushed += synced.length;

    const rejected = response.rejected.flatMap((r) =>
      r.id ? [{ id: r.id, reason: r.reason }] : [],
    );
    await store.markRejected(rejected);
    result.rejected += response.rejected.length;
  }

  let cursor = await store.getCursor();
  for (;;) {
    const page = await api.syncPull(cursor);
    const valid = page.observations.filter(isHealthObservation);
    result.invalid += page.observations.length - valid.length;
    await store.saveFromServer(valid);
    result.pulled += valid.length;
    cursor = page.next_cursor;
    await store.setCursor(cursor);
    if (!page.has_more) break;
  }
  return result;
}
