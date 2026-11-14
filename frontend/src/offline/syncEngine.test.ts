import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import {
  TransportError,
  type MutationResult,
  type ServerChange,
  type SyncPullResponse,
  type SyncPushRequest,
  type SyncPushResponse,
  type SyncTransport,
} from '../domain/sync'
import { makeObservation } from '../test/factories'
import { deleteDb, openDb } from './db'
import { LocalStore } from './store'
import { syncOnce } from './syncEngine'

/** In-memory stand-in for the server, mirroring its contract (dedupe by id, per-item results). */
class FakeServer implements SyncTransport {
  rows: ServerChange[] = []
  online = true
  failWith: TransportError | null = null
  poisonIds = new Set<string>() // observations that make the whole batch a 422
  rejectIds = new Set<string>() // observations the server semantically rejects
  pushCalls: SyncPushRequest[] = []

  async push(req: SyncPushRequest): Promise<SyncPushResponse> {
    this.pushCalls.push(req)
    if (!this.online) throw new TransportError('network', 'offline')
    if (this.failWith) throw this.failWith
    if (req.mutations.some((m) => this.poisonIds.has(m.observation.id))) {
      throw new TransportError('http', 'HTTP 422', 422)
    }
    const results: MutationResult[] = req.mutations.map((m) => {
      const id = m.observation.id
      if (this.rejectIds.has(id)) {
        return { mutation_id: m.mutation_id, observation_id: id, status: 'rejected', server_seq: null, error: 'nope' }
      }
      const existing = this.rows.find((r) => r.observation.id === id)
      if (existing) {
        return { mutation_id: m.mutation_id, observation_id: id, status: 'duplicate', server_seq: existing.server_seq, error: null }
      }
      const row = { server_seq: this.rows.length + 1, observation: m.observation }
      this.rows.push(row)
      return { mutation_id: m.mutation_id, observation_id: id, status: 'accepted', server_seq: row.server_seq, error: null }
    })
    return { results, server_cursor: this.rows.length }
  }

  async pull(cursor: number, limit: number): Promise<SyncPullResponse> {
    if (!this.online) throw new TransportError('network', 'offline')
    const rest = this.rows.filter((r) => r.server_seq > cursor)
    const changes = rest.slice(0, limit)
    return {
      changes,
      next_cursor: rest.length > limit ? (changes[changes.length - 1]?.server_seq ?? cursor) : Math.max(cursor, this.rows.length),
      has_more: rest.length > limit,
    }
  }
}

let name: string
let store: LocalStore
let server: FakeServer

beforeEach(async () => {
  name = `medvital-test-${crypto.randomUUID()}`
  store = new LocalStore(await openDb(name))
  server = new FakeServer()
})

afterEach(async () => {
  store.close()
  await deleteDb(name)
})

describe('syncOnce', () => {
  it('offline: nothing is lost and nothing is marked synced', async () => {
    await store.addLocalObservation(makeObservation())
    server.online = false
    const report = await syncOnce(store, server)
    expect(report.outcome).toBe('offline')
    expect(await store.pendingCount()).toBe(1)
    const [entry] = await store.listOutbox()
    expect(entry?.attempts).toBe(1)
    expect(entry?.status).toBe('pending')
  })

  it('reconnect: queued observations upload and the outbox drains', async () => {
    const o = makeObservation()
    await store.addLocalObservation(o)
    server.online = false
    await syncOnce(store, server)
    server.online = true
    const report = await syncOnce(store, server)
    expect(report).toMatchObject({ outcome: 'ok', pushed: 1, rejected: 0 })
    expect(await store.pendingCount()).toBe(0)
    expect((await store.getRecord(o.id))?.sync_state).toBe('synced')
    expect(server.rows).toHaveLength(1)
  })

  it('retrying after a lost response does not duplicate on the server', async () => {
    const o = makeObservation()
    await store.addLocalObservation(o)
    server.rows.push({ server_seq: 1, observation: o }) // server stored it, but the client never heard back
    const report = await syncOnce(store, server)
    expect(report.outcome).toBe('ok')
    expect(server.rows).toHaveLength(1)
    expect((await store.getRecord(o.id))?.server_seq).toBe(1)
  })

  it('server rejection quarantines the mutation and it is not retried', async () => {
    const o = makeObservation()
    server.rejectIds.add(o.id)
    await store.addLocalObservation(o)
    const first = await syncOnce(store, server)
    expect(first).toMatchObject({ rejected: 1, pushed: 0 })
    expect((await store.getRecord(o.id))?.sync_state).toBe('rejected')
    const calls = server.pushCalls.length
    await syncOnce(store, server)
    expect(server.pushCalls.length).toBe(calls) // failed entries are skipped
    const [entry] = await store.listOutbox()
    expect(entry).toMatchObject({ status: 'failed', last_error: 'nope' })
  })

  it('a poison record (HTTP 422) is isolated and does not block the rest of the batch', async () => {
    const good1 = makeObservation()
    const bad = makeObservation()
    const good2 = makeObservation()
    server.poisonIds.add(bad.id)
    for (const o of [good1, bad, good2]) await store.addLocalObservation(o)
    const report = await syncOnce(store, server)
    expect(report).toMatchObject({ outcome: 'ok', pushed: 2, rejected: 1 })
    expect(server.rows.map((r) => r.observation.id).sort()).toEqual([good1.id, good2.id].sort())
    expect((await store.getRecord(bad.id))?.sync_state).toBe('rejected')
  })

  it('5xx keeps everything pending and reports server_error', async () => {
    await store.addLocalObservation(makeObservation())
    server.failWith = new TransportError('http', 'HTTP 503', 503)
    const report = await syncOnce(store, server)
    expect(report.outcome).toBe('server_error')
    expect(await store.pendingCount()).toBe(1)
  })

  it('pushes in batches', async () => {
    for (let i = 0; i < 5; i++) await store.addLocalObservation(makeObservation())
    await syncOnce(store, server, { pushBatchSize: 2 })
    expect(server.pushCalls.map((c) => c.mutations.length)).toEqual([2, 2, 1])
  })

  it('pulls paginated server changes and advances the cursor', async () => {
    for (let i = 1; i <= 5; i++) server.rows.push({ server_seq: i, observation: makeObservation() })
    const report = await syncOnce(store, server, { pullLimit: 2 })
    expect(report.pulled).toBe(5)
    expect(await store.getCursor()).toBe(5)
    expect(await store.listObservations()).toHaveLength(5)
    expect((await syncOnce(store, server)).pulled).toBe(0)
  })

  it('a device pulls observations another device uploaded (and keeps its own)', async () => {
    const remote = makeObservation()
    server.rows.push({ server_seq: 1, observation: remote })
    const local = makeObservation()
    await store.addLocalObservation(local)
    await syncOnce(store, server)
    const ids = (await store.listObservations()).map((r) => r.id).sort()
    expect(ids).toEqual([local.id, remote.id].sort())
  })

  it('offline pull failure leaves the cursor unchanged', async () => {
    server.online = false
    await syncOnce(store, server)
    expect(await store.getCursor()).toBe(0)
  })
})
