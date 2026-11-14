import { describe, expect, it, vi } from "vitest";
import { ApiError, createApiClient } from "../src/api/client";
import { makeObservation } from "./helpers";

function jsonResponse(body: unknown, status = 200): Response {
  return new Response(JSON.stringify(body), {
    status,
    headers: { "Content-Type": "application/json" },
  });
}

describe("createApiClient", () => {
  it("posts sync pushes to the v1 endpoint with device id and observations", async () => {
    const fetchImpl = vi.fn(async () => jsonResponse({ accepted: [], duplicates: [], rejected: [] }));
    const api = createApiClient({ baseUrl: "http://api.test", fetchImpl });
    const obs = makeObservation();

    await api.syncPush("dev-1", [obs]);

    const [url, init] = fetchImpl.mock.calls[0] as unknown as [string, RequestInit];
    expect(url).toBe("http://api.test/api/v1/sync/push");
    expect(init.method).toBe("POST");
    expect(JSON.parse(init.body as string)).toEqual({ device_id: "dev-1", observations: [obs] });
  });

  it("requests pulls with cursor and limit", async () => {
    const fetchImpl = vi.fn(async () =>
      jsonResponse({ observations: [], next_cursor: 7, has_more: false }),
    );
    const api = createApiClient({ fetchImpl });
    await api.syncPull(7, 50);
    expect((fetchImpl.mock.calls[0] as unknown as [string])[0]).toBe(
      "/api/v1/sync/pull?cursor=7&limit=50",
    );
  });

  it("throws ApiError on non-2xx responses and propagates network failures", async () => {
    const failing = createApiClient({ fetchImpl: vi.fn(async () => jsonResponse({}, 500)) });
    await expect(failing.health()).rejects.toBeInstanceOf(ApiError);

    const offline = createApiClient({
      fetchImpl: vi.fn(async () => {
        throw new TypeError("Failed to fetch");
      }),
    });
    await expect(offline.health()).rejects.toThrow("Failed to fetch");
  });
});
