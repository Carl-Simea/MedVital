import { TransportError, type SyncTransport } from '../domain/sync'
import type { LocalStore, OutboxEntry } from './store'

export interface SyncOptions {
  pushBatchSize?: number
  pullLimit?: number
}

export interface SyncReport {
  /** ok: completed · offline: no network, nothing lost · server_error: server failed, retry later */
  outcome: 'ok' | 'offline' | 'server_error'
  pushed: number
  rejected: number
  pulled: number
  error?: string
}

/**
 * One full sync pass: push the outbox, then pull server changes.
 *
 * Safe to run at any time, repeatedly and concurrently-ish: pushes are idempotent (the
 * server dedupes by observation id) and pulls upsert by id. Network or 5xx failures leave
 * everything exactly where it was, so the caller can simply retry later.
 */
export async function syncOnce(
  store: LocalStore,
  transport: SyncTransport,
  options: SyncOptions = {},
): Promise<SyncReport> {
  const pushBatchSize = options.pushBatchSize ?? 100
  const pullLimit = options.pullLimit ?? 500
  const report: SyncReport = { outcome: 'ok', pushed: 0, rejected: 0, pulled: 0 }

  try {
    const clientId = await store.getClientId()

    // 1. Push
    for (;;) {
      const batch = await store.pendingMutations(pushBatchSize)
      if (batch.length === 0) break
      const progress = await pushBatch(store, transport, clientId, batch, report)
      if (progress === 0) break // server answered without resolving anything; avoid a hot loop
    }

    // 2. Pull
    for (;;) {
      const cursor = await store.getCursor()
      const page = await transport.pull(cursor, pullLimit)
      await store.applyServerChanges(page.changes, page.next_cursor)
      report.pulled += page.changes.length
      if (!page.has_more) break
    }
  } catch (err) {
    if (err instanceof TransportError) {
      report.outcome = err.kind === 'network' ? 'offline' : 'server_error'
      report.error = err.message
      return report
    }
    throw err
  }
  return report
}

/** Returns how many mutations reached a final state (synced or quarantined). */
async function pushBatch(
  store: LocalStore,
  transport: SyncTransport,
  clientId: string,
  batch: OutboxEntry[],
  report: SyncReport,
): Promise<number> {
  try {
    const response = await transport.push({
      client_id: clientId,
      mutations: batch.map((e) => ({ mutation_id: e.mutation_id, observation: e.observation })),
    })
    const { synced, rejected } = await store.applyPushResults(response.results)
    report.pushed += synced
    report.rejected += rejected
    return synced + rejected
  } catch (err) {
    if (err instanceof TransportError && err.kind === 'http' && err.status === 422) {
      // One malformed mutation makes the server reject the whole batch. Isolate it so a
      // single poison record can never block everything queued behind it.
      if (batch.length > 1) {
        let progress = 0
        for (const entry of batch) progress += await pushBatch(store, transport, clientId, [entry], report)
        return progress
      }
      const only = batch[0]
      if (only) {
        await store.markMutationFailed(only.mutation_id, `server could not parse observation: ${err.message}`)
        report.rejected += 1
        return 1
      }
      return 0
    }
    if (err instanceof TransportError) {
      await store.recordAttemptFailure(
        batch.map((e) => e.mutation_id),
        err.message,
      )
    }
    throw err
  }
}
