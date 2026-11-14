import type { HealthObservation, SyncPullResponse, SyncPushResponse } from "../domain/types";

export class ApiError extends Error {
  constructor(
    readonly status: number,
    message: string,
  ) {
    super(message);
    this.name = "ApiError";
  }
}

export interface ApiClient {
  health(): Promise<{ status: string; version: string; observation_schema_version: number }>;
  syncPush(deviceId: string, observations: HealthObservation[]): Promise<SyncPushResponse>;
  syncPull(cursor: number, limit?: number): Promise<SyncPullResponse>;
}

export interface ApiClientOptions {
  baseUrl?: string;
  fetchImpl?: typeof fetch;
}

/** Typed client for API v1. Network failures reject; callers treat that as "offline". */
export function createApiClient({ baseUrl = "", fetchImpl }: ApiClientOptions = {}): ApiClient {
  const doFetch: typeof fetch = fetchImpl ?? ((...args) => fetch(...args));

  async function request<T>(path: string, init?: RequestInit): Promise<T> {
    const response = await doFetch(`${baseUrl}/api/v1${path}`, init);
    if (!response.ok) throw new ApiError(response.status, `${response.status} ${path}`);
    return (await response.json()) as T;
  }

  return {
    health: () => request("/health"),
    syncPush: (deviceId, observations) =>
      request("/sync/push", {
        method: "POST",
        headers: { "Content-Type": "application/json" },
        body: JSON.stringify({ device_id: deviceId, observations }),
      }),
    syncPull: (cursor, limit = 200) => request(`/sync/pull?cursor=${cursor}&limit=${limit}`),
  };
}
