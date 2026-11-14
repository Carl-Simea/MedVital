import { describe, expect, it, vi } from "vitest";
import type { ApiClient } from "../src/api/client";
import type { SyncPullResponse, SyncPushResponse } from "../src/domain/types";
import { ObservationStore } from "../src/offline/store";
import { syncOnce } from "../src/offline/sync";
import { freshDbName, makeObservation } from "./helpers";

function fakeApi(overrides: Partial<ApiClient> = {}): ApiClient {
  return {
    health: vi.fn(),
    syncPush: vi.fn(
      async (): Promise<SyncPushResponse> => ({ accepted: [], duplicates: [], rejected: [] }),
    ),
    syncPull: vi.fn(
      async (): Promise<SyncPullResponse> => ({ observations: [], next_cursor: 0, has_more: false }),
    ),
    ...overrides,
  };
}

describe("syncOnce", () => {
  it("pushes the outbox and clears accepted and duplicate items", async () => {
    const store = await ObservationStore.open(freshDbName());
    const [a, b] = [makeObservation(), makeObservation()] as const;
    await store.record([a, b]);
    const api = fakeApi({
      syncPush: vi.fn(async () => ({ accepted: [a.id], duplicates: [b.id], rejected: [] })),
    });

    const result = await syncOnce(store, api);
    expect(result.pushed).toBe(2);
    expect(await store.outbox("pending")).toHaveLength(0);
  });

  it("keeps rejected items locally, flagged, and does not resend them", async () => {
    const store = await ObservationStore.open(freshDbName());
    const a = makeObservation();
    await store.record([a]);
    const push = vi.fn(async () => ({
      accepted: [],
      duplicates: [],
      rejected: [{ id: a.id, reason: "unit mismatch" }],
    }));
    const api = fakeApi({ syncPush: push });

    expect((await syncOnce(store, api)).rejected).toBe(1);
    await syncOnce(store, api);
    expect(push).toHaveBeenCalledTimes(1); // second run had nothing pending
    expect((await store.outbox("rejected"))[0]?.reason).toBe("unit mismatch");
  });

  it("splits large outboxes into batches", async () => {
    const store = await ObservationStore.open(freshDbName());
    await store.record([1, 2, 3, 4, 5].map(() => makeObservation()));
    const push = vi.fn(async (_device: string, obs: { id: string }[]) => ({
      accepted: obs.map((o) => o.id),
      duplicates: [],
      rejected: [],
    }));
    await syncOnce(store, fakeApi({ syncPush: push }), { batchSize: 2 });
    expect(push).toHaveBeenCalledTimes(3);
  });

  it("pulls every page, advances the cursor and ignores malformed server data", async () => {
    const store = await ObservationStore.open(freshDbName());
    const [x, y] = [makeObservation(), makeObservation()] as const;
    const pages: SyncPullResponse[] = [
      { observations: [x], next_cursor: 1, has_more: true },
      {
        observations: [y, { nonsense: true } as never],
        next_cursor: 2,
        has_more: false,
      },
    ];
    const pull = vi.fn(async (cursor: number) => pages[cursor] as SyncPullResponse);

    const result = await syncOnce(store, fakeApi({ syncPull: pull }));
    expect(result.pulled).toBe(2);
    expect(result.invalid).toBe(1);
    expect(await store.getCursor()).toBe(2);
    expect((await store.list()).map((o) => o.id).sort()).toEqual([x.id, y.id].sort());
  });

  it("leaves the outbox intact when the network fails, so a later retry succeeds", async () => {
    const store = await ObservationStore.open(freshDbName());
    const a = makeObservation();
    await store.record([a]);

    const offline = fakeApi({
      syncPush: vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    });
    await expect(syncOnce(store, offline)).rejects.toThrow("Failed to fetch");
    expect(await store.outbox("pending")).toHaveLength(1);

    const online = fakeApi({
      syncPush: vi.fn(async () => ({ accepted: [a.id], duplicates: [], rejected: [] })),
    });
    expect((await syncOnce(store, online)).pushed).toBe(1);
    expect(await store.outbox("pending")).toHaveLength(0);
  });
});
