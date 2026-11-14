import { describe, expect, it } from "vitest";
import { ObservationStore } from "../src/offline/store";
import { freshDbName, makeObservation } from "./helpers";

describe("ObservationStore (IndexedDB)", () => {
  it("records observations locally and queues them in the outbox", async () => {
    const store = await ObservationStore.open(freshDbName());
    const a = makeObservation();
    const b = makeObservation({ module: "bone", metric: "bmd_areal", unit: "g/cm2" });
    await store.record([a, b]);

    expect((await store.list()).map((o) => o.id).sort()).toEqual([a.id, b.id].sort());
    expect((await store.list("bone")).map((o) => o.id)).toEqual([b.id]);
    expect((await store.outbox("pending")).length).toBe(2);
  });

  it("is idempotent when the same observation is recorded twice", async () => {
    const store = await ObservationStore.open(freshDbName());
    const a = makeObservation();
    await store.record([a]);
    await store.record([a]);
    expect(await store.list()).toHaveLength(1);
    expect(await store.outbox("pending")).toHaveLength(1);
  });

  it("does not queue observations that came from the server", async () => {
    const store = await ObservationStore.open(freshDbName());
    await store.saveFromServer([makeObservation()]);
    expect(await store.list()).toHaveLength(1);
    expect(await store.outbox("pending")).toHaveLength(0);
  });

  it("removes synced items and keeps rejected ones with a reason", async () => {
    const store = await ObservationStore.open(freshDbName());
    const [a, b] = [makeObservation(), makeObservation()] as const;
    await store.record([a, b]);
    await store.markSynced([a.id]);
    await store.markRejected([{ id: b.id, reason: "bad unit" }]);

    expect(await store.outbox("pending")).toHaveLength(0);
    const rejected = await store.outbox("rejected");
    expect(rejected).toHaveLength(1);
    expect(rejected[0]?.reason).toBe("bad unit");
    expect(await store.list()).toHaveLength(2); // local data is never deleted
  });

  it("persists the sync cursor and a stable device id", async () => {
    const name = freshDbName();
    const first = await ObservationStore.open(name);
    expect(await first.getCursor()).toBe(0);
    await first.setCursor(42);
    const device = await first.getDeviceId();
    first.close();

    const second = await ObservationStore.open(name);
    expect(await second.getCursor()).toBe(42);
    expect(await second.getDeviceId()).toBe(device);
  });
});
