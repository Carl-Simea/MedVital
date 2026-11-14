/** Wire types for POST /sync/push and GET /sync/pull (backend/medvital/core/sync.py). */
import type { HealthObservation } from './observation'

export interface SyncMutation {
  mutation_id: string
  observation: HealthObservation
}

export interface SyncPushRequest {
  client_id: string
  mutations: SyncMutation[]
}

export type MutationStatus = 'accepted' | 'duplicate' | 'rejected'

export interface MutationResult {
  mutation_id: string | null
  observation_id: string
  status: MutationStatus
  server_seq: number | null
  error: string | null
}

export interface SyncPushResponse {
  results: MutationResult[]
  server_cursor: number
}

export interface ServerChange {
  server_seq: number
  observation: HealthObservation
}

export interface SyncPullResponse {
  changes: ServerChange[]
  next_cursor: number
  has_more: boolean
}

/** Everything the sync engine needs from the network; swap for a fake in tests. */
export interface SyncTransport {
  push(request: SyncPushRequest): Promise<SyncPushResponse>
  pull(cursor: number, limit: number): Promise<SyncPullResponse>
}

/** `network`: no response at all (offline, DNS, refused). `http`: server answered with an error. */
export class TransportError extends Error {
  readonly kind: 'network' | 'http'
  readonly status: number | undefined

  constructor(kind: 'network' | 'http', message: string, status?: number) {
    super(message)
    this.name = 'TransportError'
    this.kind = kind
    this.status = status
  }
}
