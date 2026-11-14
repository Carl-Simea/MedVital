import type { HealthObservation, ModuleId } from "../domain/types";

export const DB_NAME = "medvital";
const DB_VERSION = 1;

const OBSERVATIONS = "observations";
const OUTBOX = "outbox";
const META = "meta";

export interface OutboxEntry {
  id: string;
  observation: HealthObservation;
  queued_at: string;
  status: "pending" | "rejected";
  reason?: string;
}

interface MetaRecord {
  key: string;
  value: unknown;
}

function request<T>(req: IDBRequest<T>): Promise<T> {
  return new Promise((resolve, reject) => {
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

function done(tx: IDBTransaction): Promise<void> {
  return new Promise((resolve, reject) => {
    tx.oncomplete = () => resolve();
    tx.onerror = () => reject(tx.error);
    tx.onabort = () => reject(tx.error ?? new Error("transaction aborted"));
  });
}

function openDatabase(name: string): Promise<IDBDatabase> {
  return new Promise((resolve, reject) => {
    const req = indexedDB.open(name, DB_VERSION);
    req.onupgradeneeded = () => {
      const db = req.result;
      const observations = db.createObjectStore(OBSERVATIONS, { keyPath: "id" });
      observations.createIndex("astronaut_id", "astronaut_id");
      observations.createIndex("module", "module");
      db.createObjectStore(OUTBOX, { keyPath: "id" });
      db.createObjectStore(META, { keyPath: "key" });
    };
    req.onsuccess = () => resolve(req.result);
    req.onerror = () => reject(req.error);
  });
}

/**
 * Local-first store. Observations are immutable, so every write is an idempotent `put` keyed
 * by observation id, and the outbox is the queue of observations not yet confirmed by the server.
 */
export class ObservationStore {
  private constructor(private readonly db: IDBDatabase) {}

  static async open(name: string = DB_NAME): Promise<ObservationStore> {
    return new ObservationStore(await openDatabase(name));
  }

  close(): void {
    this.db.close();
  }

  /** Record locally-created observations and queue them for upload, atomically. */
  async record(observations: HealthObservation[]): Promise<void> {
    const tx = this.db.transaction([OBSERVATIONS, OUTBOX], "readwrite");
    const now = new Date().toISOString();
    for (const observation of observations) {
      tx.objectStore(OBSERVATIONS).put(observation);
      const entry: OutboxEntry = {
        id: observation.id,
        observation,
        queued_at: now,
        status: "pending",
      };
      tx.objectStore(OUTBOX).put(entry);
    }
    await done(tx);
  }

  /** Store observations received from the server. Does not queue them for upload. */
  async saveFromServer(observations: HealthObservation[]): Promise<void> {
    const tx = this.db.transaction(OBSERVATIONS, "readwrite");
    for (const observation of observations) tx.objectStore(OBSERVATIONS).put(observation);
    await done(tx);
  }

  async list(module?: ModuleId): Promise<HealthObservation[]> {
    const store = this.db.transaction(OBSERVATIONS).objectStore(OBSERVATIONS);
    const all = module
      ? await request(store.index("module").getAll(module))
      : await request(store.getAll());
    return all as HealthObservation[];
  }

  async outbox(status: OutboxEntry["status"] = "pending"): Promise<OutboxEntry[]> {
    const all = (await request(
      this.db.transaction(OUTBOX).objectStore(OUTBOX).getAll(),
    )) as OutboxEntry[];
    return all.filter((entry) => entry.status === status);
  }

  async markSynced(ids: string[]): Promise<void> {
    const tx = this.db.transaction(OUTBOX, "readwrite");
    for (const id of ids) tx.objectStore(OUTBOX).delete(id);
    await done(tx);
  }

  /** Keep rejected items (never silently drop data) but stop retrying them. */
  async markRejected(items: { id: string; reason: string }[]): Promise<void> {
    const tx = this.db.transaction(OUTBOX, "readwrite");
    const store = tx.objectStore(OUTBOX);
    for (const { id, reason } of items) {
      const existing = (await request(store.get(id))) as OutboxEntry | undefined;
      if (existing) store.put({ ...existing, status: "rejected", reason });
    }
    await done(tx);
  }

  private async getMeta<T>(key: string): Promise<T | undefined> {
    const record = (await request(
      this.db.transaction(META).objectStore(META).get(key),
    )) as MetaRecord | undefined;
    return record?.value as T | undefined;
  }

  private async setMeta(key: string, value: unknown): Promise<void> {
    const tx = this.db.transaction(META, "readwrite");
    tx.objectStore(META).put({ key, value } satisfies MetaRecord);
    await done(tx);
  }

  async getCursor(): Promise<number> {
    return (await this.getMeta<number>("sync_cursor")) ?? 0;
  }

  async setCursor(cursor: number): Promise<void> {
    await this.setMeta("sync_cursor", cursor);
  }

  async getDeviceId(): Promise<string> {
    const existing = await this.getMeta<string>("device_id");
    if (existing) return existing;
    const created = `browser-${crypto.randomUUID().slice(0, 8)}`;
    await this.setMeta("device_id", created);
    return created;
  }
}
