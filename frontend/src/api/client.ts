import {
  TransportError,
  type SyncPullResponse,
  type SyncPushRequest,
  type SyncPushResponse,
  type SyncTransport,
} from '../domain/sync'

type FetchLike = (input: string, init?: RequestInit) => Promise<Response>

/** fetch-based transport for the FastAPI backend (see docs/api/openapi.json). */
export class HttpTransport implements SyncTransport {
  private readonly baseUrl: string
  private readonly fetchImpl: FetchLike

  constructor(baseUrl = '/api/v1', fetchImpl: FetchLike = (input, init) => fetch(input, init)) {
    this.baseUrl = baseUrl
    this.fetchImpl = fetchImpl
  }

  push(request: SyncPushRequest): Promise<SyncPushResponse> {
    return this.request<SyncPushResponse>('/sync/push', {
      method: 'POST',
      headers: { 'Content-Type': 'application/json' },
      body: JSON.stringify(request),
    })
  }

  pull(cursor: number, limit: number): Promise<SyncPullResponse> {
    return this.request<SyncPullResponse>(`/sync/pull?cursor=${cursor}&limit=${limit}`)
  }

  private async request<T>(path: string, init?: RequestInit): Promise<T> {
    let response: Response
    try {
      response = await this.fetchImpl(`${this.baseUrl}${path}`, init)
    } catch (err) {
      throw new TransportError('network', err instanceof Error ? err.message : 'network error')
    }
    if (!response.ok) {
      throw new TransportError('http', `HTTP ${response.status} ${response.statusText}`.trim(), response.status)
    }
    return (await response.json()) as T
  }
}
