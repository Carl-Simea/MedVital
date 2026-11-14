import type { HealthObservation, ModuleId } from '../domain/observation'
import { validateObservation } from '../domain/observation'
import type { MutationResult, ServerChange } from '../domain/sync'
import { promisify, STORES, transactionDone } from './db'

/** pending: only on this device · synced: server has it · rejected: server refused it permanently */
export type SyncState = 'pending' | 'synced' | 'rejected'

export interface ObservationRecord {
  id: string
  subject_id: string
  module: ModuleId
  observed_at: string
  observation: HealthObservation
  sync_state: SyncState
  server_seq: number | null
}

export interface OutboxEntry {
  mutation_id: string
  observation_id: string
  observation: HealthObservation
  status: 'pending' | 'failed'
  attempts: number
  last_error: string | null
  queued_at: number
}

const CURSOR_KEY = 'sync_cursor'
const CLIENT_ID_KEY = 'client_id'

export class DuplicateObservationError extends Error {
  constructor(id: string) {
    super(`observation ${id} already exists; observations are immutable — record a correction with supersedes`)
    this.name = 'DuplicateObservationError'
  }
}

export class InvalidObservationError extends Error {
  readonly errors: string[]
  constructor(errors: string[]) {
    super(`invalid observation: ${errors.join('; ')}`)
    this.name = 'InvalidObservationError'
    this.errors = errors
  }
}

/** All local persistence. Every multi-store change happens in ONE transaction. */
export class LocalStore {
  private readonly db: IDBDatabase
  private seq = 0

  constructor(db: IDBDatabase) {
    this.db = db
  }

  close(): void {
    this.db.close()
  }

  /** Save a new observation locally and queue it for upload, atomically. Works fully offline. */
  async addLocalObservation(observation: HealthObservation): Promise<{ mutation_id: string }> {
    const checked = validateObservation(observation)
    if (!checked.ok) throw new InvalidObservationError(checked.errors)

    const tx = this.db.transaction([STORES.observations, STORES.outbox], 'readwrite')
    const done = transactionDone(tx)
    const observations = tx.objectStore(STORES.observations)
    const existing = await promisify(observations.get(observation.id))
    if (existing) {
      tx.abort()
      await done.catch(() => undefined)
      throw new DuplicateObservationError(observation.id)
    }
    const mutation_id = crypto.randomUUID()
    const record: ObservationRecord = {
      id: observation.id,
      subject_id: observation.subject_id,
      module: observation.module,
      observed_at: observation.observed_at,
      observation,
      sync_state: 'pending',
      server_seq: null,
    }
    const entry: OutboxEntry = {
      mutation_id,
      observation_id: observation.id,
      observation,
      status: 'pending',
      attempts: 0,
      last_error: null,
      queued_at: Date.now() * 1000 + (this.seq++ % 1000), // monotonic within this store instance
    }
    observations.put(record)
    tx.objectStore(STORES.outbox).put(entry)
    await done
    return { mutation_id }
  }

  async getRecord(id: string): Promise<ObservationRecord | undefined> {
    const tx = this.db.transaction(STORES.observations)
    return promisify<ObservationRecord | undefined>(tx.objectStore(STORES.observations).get(id))
  }

  async listObservations(filter: { subject_id?: string; module?: ModuleId } = {}): Promise<ObservationRecord[]> {
    const tx = this.db.transaction(STORES.observations)
    const all = await promisify<ObservationRecord[]>(tx.objectStore(STORES.observations).getAll())
    return all
      .filter((r) => (filter.subject_id ? r.subject_id === filter.subject_id : true))
      .filter((r) => (filter.module ? r.module === filter.module : true))
      .sort((a, b) => Date.parse(a.observed_at) - Date.parse(b.observed_at) || a.id.localeCompare(b.id))
  }

  async listOutbox(): Promise<OutboxEntry[]> {
    const tx = this.db.transaction(STORES.outbox)
    const all = await promisify<OutboxEntry[]>(tx.objectStore(STORES.outbox).getAll())
    return all.sort((a, b) => a.queued_at - b.queued_at)
  }

  /** Oldest-first mutations that are still eligible for upload (failed ones are quarantined). */
  async pendingMutations(limit: number): Promise<OutboxEntry[]> {
    return (await this.listOutbox()).filter((e) => e.status === 'pending').slice(0, limit)
  }

  async pendingCount(): Promise<number> {
    return (await this.pendingMutations(Number.MAX_SAFE_INTEGER)).length
  }

  /** Count an upload attempt that did not reach a verdict (offline, 5xx). Entries stay pending. */
  async recordAttemptFailure(mutationIds: string[], error: string): Promise<void> {
    const tx = this.db.transaction(STORES.outbox, 'readwrite')
    const store = tx.objectStore(STORES.outbox)
    for (const id of mutationIds) {
      const entry = await promisify<OutboxEntry | undefined>(store.get(id))
      if (entry) store.put({ ...entry, attempts: entry.attempts + 1, last_error: error })
    }
    await transactionDone(tx)
  }

  /** Apply the server's per-mutation verdicts: synced entries leave the outbox, rejected ones are quarantined. */
  async applyPushResults(results: MutationResult[]): Promise<{ synced: number; rejected: number }> {
    const tx = this.db.transaction([STORES.observations, STORES.outbox], 'readwrite')
    const observations = tx.objectStore(STORES.observations)
    const outbox = tx.objectStore(STORES.outbox)
    let synced = 0
    let rejected = 0
    for (const r of results) {
      const entry = r.mutation_id ? await promisify<OutboxEntry | undefined>(outbox.get(r.mutation_id)) : undefined
      if (!entry) continue
      const record = await promisify<ObservationRecord | undefined>(observations.get(entry.observation_id))
      if (r.status === 'rejected') {
        outbox.put({ ...entry, status: 'failed', attempts: entry.attempts + 1, last_error: r.error ?? 'rejected' })
        if (record) observations.put({ ...record, sync_state: 'rejected' })
        rejected++
      } else {
        outbox.delete(entry.mutation_id)
        if (record) observations.put({ ...record, sync_state: 'synced', server_seq: r.server_seq })
        synced++
      }
    }
    await transactionDone(tx)
    return { synced, rejected }
  }

  /** Quarantine a mutation the server could not even parse (HTTP 422). */
  async markMutationFailed(mutationId: string, error: string): Promise<void> {
    const tx = this.db.transaction([STORES.observations, STORES.outbox], 'readwrite')
    const outbox = tx.objectStore(STORES.outbox)
    const entry = await promisify<OutboxEntry | undefined>(outbox.get(mutationId))
    if (entry) {
      outbox.put({ ...entry, status: 'failed', attempts: entry.attempts + 1, last_error: error })
      const observations = tx.objectStore(STORES.observations)
      const record = await promisify<ObservationRecord | undefined>(observations.get(entry.observation_id))
      if (record) observations.put({ ...record, sync_state: 'rejected' })
    }
    await transactionDone(tx)
  }

  /** Store a page of server changes and advance the cursor in the SAME transaction. */
  async applyServerChanges(changes: ServerChange[], nextCursor: number): Promise<void> {
    const tx = this.db.transaction([STORES.observations, STORES.meta], 'readwrite')
    const observations = tx.objectStore(STORES.observations)
    for (const c of changes) {
      const o = c.observation
      const record: ObservationRecord = {
        id: o.id,
        subject_id: o.subject_id,
        module: o.module,
        observed_at: o.observed_at,
        observation: o,
        sync_state: 'synced',
        server_seq: c.server_seq,
      }
      observations.put(record) // idempotent: keyed by immutable id
    }
    tx.objectStore(STORES.meta).put(nextCursor, CURSOR_KEY)
    await transactionDone(tx)
  }

  async getCursor(): Promise<number> {
    const tx = this.db.transaction(STORES.meta)
    return (await promisify<number | undefined>(tx.objectStore(STORES.meta).get(CURSOR_KEY))) ?? 0
  }

  /** Stable per-install id sent with pushes (diagnostics only; not an identity or credential). */
  async getClientId(): Promise<string> {
    const tx = this.db.transaction(STORES.meta, 'readwrite')
    const meta = tx.objectStore(STORES.meta)
    let id = await promisify<string | undefined>(meta.get(CLIENT_ID_KEY))
    if (!id) {
      id = `web-${crypto.randomUUID()}`
      meta.put(id, CLIENT_ID_KEY)
    }
    await transactionDone(tx)
    return id
  }
}
