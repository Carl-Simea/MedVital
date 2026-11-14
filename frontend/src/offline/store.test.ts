import { afterEach, beforeEach, describe, expect, it } from 'vitest'
import { makeObservation } from '../test/factories'
import { deleteDb, openDb } from './db'
import { DuplicateObservationError, InvalidObservationError, LocalStore } from './store'

let name: string
let store: LocalStore

beforeEach(async () => {
  name = `medvital-test-${crypto.randomUUID()}`
  store = new LocalStore(await openDb(name))
})

afterEach(async () => {
  store.close()
  await deleteDb(name)
})

describe('LocalStore (IndexedDB, offline)', () => {
  it('saves an observation and queues it in the outbox atomically', async () => {
    const o = makeObservation()
    const { mutation_id } = await store.addLocalObservation(o)
    expect((await store.getRecord(o.id))?.sync_state).toBe('pending')
    const outbox = await store.listOutbox()
    expect(outbox).toHaveLength(1)
    expect(outbox[0]).toMatchObject({ mutation_id, observation_id: o.id, status: 'pending' })
  })

  it('persists across closing and reopening the database', async () => {
    const o = makeObservation()
    await store.addLocalObservation(o)
    store.close()
    store = new LocalStore(await openDb(name))
    expect((await store.listObservations()).map((r) => r.id)).toEqual([o.id])
    expect(await store.pendingCount()).toBe(1)
  })

  it('refuses to overwrite an existing observation and leaves no extra outbox entry', async () => {
    const o = makeObservation()
    await store.addLocalObservation(o)
    await expect(store.addLocalObservation({ ...o, value: 2 })).rejects.toBeInstanceOf(DuplicateObservationError)
    expect(await store.listOutbox()).toHaveLength(1)
    expect((await store.getRecord(o.id))?.observation.value).toBe(1)
  })

  it('rejects invalid observations before they reach the outbox', async () => {
    await expect(store.addLocalObservation(makeObservation({ value: Number.NaN }))).rejects.toBeInstanceOf(
      InvalidObservationError,
    )
    expect(await store.listOutbox()).toHaveLength(0)
  })

  it('lists observations filtered and time-ordered', async () => {
    await store.addLocalObservation(makeObservation({ observed_at: '2030-01-03T00:00:00Z', subject_id: 'A' }))
    await store.addLocalObservation(makeObservation({ observed_at: '2030-01-01T00:00:00Z', subject_id: 'A' }))
    await store.addLocalObservation(makeObservation({ observed_at: '2030-01-02T00:00:00Z', subject_id: 'B' }))
    const a = await store.listObservations({ subject_id: 'A' })
    expect(a.map((r) => r.observed_at)).toEqual(['2030-01-01T00:00:00Z', '2030-01-03T00:00:00Z'])
    expect(await store.listObservations({ module: 'bone' })).toEqual([])
  })

  it('keeps outbox in FIFO order', async () => {
    const ids: string[] = []
    for (let i = 0; i < 5; i++) {
      const o = makeObservation()
      ids.push(o.id)
      await store.addLocalObservation(o)
    }
    expect((await store.pendingMutations(10)).map((e) => e.observation_id)).toEqual(ids)
    expect(await store.pendingMutations(2)).toHaveLength(2)
  })

  it('stores the cursor with server changes in one step and has a stable client id', async () => {
    expect(await store.getCursor()).toBe(0)
    await store.applyServerChanges([{ server_seq: 7, observation: makeObservation() }], 7)
    expect(await store.getCursor()).toBe(7)
    const id = await store.getClientId()
    expect(id).toMatch(/^web-/)
    expect(await store.getClientId()).toBe(id)
  })

  it('applying the same server change twice is idempotent', async () => {
    const change = { server_seq: 1, observation: makeObservation() }
    await store.applyServerChanges([change], 1)
    await store.applyServerChanges([change], 1)
    expect(await store.listObservations()).toHaveLength(1)
  })
})
