/**
 * IndexedDB schema and migrations. Three object stores:
 *
 *  - observations : every observation this device knows about (local + pulled), keyed by id
 *  - outbox       : mutations awaiting upload (FIFO by queued_at), keyed by mutation_id
 *  - meta         : small key/value (sync cursor, client id)
 *
 * Bump DB_VERSION and add a `if (oldVersion < N)` block to migrate(); never edit an old block.
 */
export const DB_NAME = 'medvital'
export const DB_VERSION = 1

export const STORES = { observations: 'observations', outbox: 'outbox', meta: 'meta' } as const

export function openDb(name: string = DB_NAME): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.open(name, DB_VERSION)
    request.onupgradeneeded = (event) => migrate(request.result, event.oldVersion)
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error ?? new Error('IndexedDB open failed'))
    request.onblocked = () => reject(new Error('IndexedDB open blocked by another tab'))
  })
}

function migrate(db: IDBDatabase, oldVersion: number): void {
  if (oldVersion < 1) {
    const observations = db.createObjectStore(STORES.observations, { keyPath: 'id' })
    observations.createIndex('by_subject_module', ['subject_id', 'module'])
    observations.createIndex('by_sync_state', 'sync_state')

    const outbox = db.createObjectStore(STORES.outbox, { keyPath: 'mutation_id' })
    outbox.createIndex('by_status', 'status')

    db.createObjectStore(STORES.meta)
  }
}

export function deleteDb(name: string = DB_NAME): Promise<void> {
  return new Promise((resolve, reject) => {
    const request = indexedDB.deleteDatabase(name)
    request.onsuccess = () => resolve()
    request.onerror = () => reject(request.error ?? new Error('IndexedDB delete failed'))
  })
}

export function promisify<T>(request: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    request.onsuccess = () => resolve(request.result)
    request.onerror = () => reject(request.error)
  })
}

export function transactionDone(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve()
    tx.onerror = () => reject(tx.error)
    tx.onabort = () => reject(tx.error ?? new Error('IndexedDB transaction aborted'))
  })
}
