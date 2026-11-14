/**
 * Measurement schedules (M2) — TypeScript mirror of backend/medvital/core/schedule.py and
 * backend/medvital/schedules.py. The backend is authoritative (docs/api/openapi.json).
 * Types only: resolution and coverage are computed by the backend, never here.
 */

import type { DataOrigin } from './observation'

export const SCHEDULE_SCHEMA_VERSION = 1

export type Anchor = 'launch' | 'return'
export type MissionPhase = 'preflight' | 'inflight' | 'postflight'
export type ScheduleBasis = 'protocol' | 'simulated'

export interface SingleTimepoint {
  kind: 'single'
  anchor: Anchor
  offset_days: number
  window_days?: number
  label?: string | null
}

export interface RecurringTimepoints {
  kind: 'recurring'
  start_anchor: Anchor
  start_offset_days: number
  end_anchor: Anchor
  end_offset_days: number
  every_days: number
  window_days?: number
  label?: string | null
}

export type ScheduleEvent = SingleTimepoint | RecurringTimepoints

export interface MeasurementSchedule {
  schema_version: typeof SCHEDULE_SCHEMA_VERSION
  id: string
  subject_id: string
  metric: string
  method: string
  context: Record<string, string>
  events: ScheduleEvent[]
  basis: ScheduleBasis
  source: string
  source_ref?: string | null
  notes?: string | null
  created_at: string
  supersedes?: string | null
}

export interface ScheduleWriteResult {
  schedule_id: string
  status: 'accepted' | 'duplicate' | 'rejected'
  schedule_seq?: number | null
  error?: string | null
}

/** A planned time. `planned_at` is modeled (mission anchor + offset), never an observation. */
export interface ResolvedEvent {
  schedule_id: string
  label: string
  planned_at: string
  window_start: string
  /** Exclusive. */
  window_end: string
  phase: MissionPhase
  time_origin: Extract<DataOrigin, 'modeled'>
  time_method: string
}

export interface EventCoverage {
  event: ResolvedEvent
  /** Per data origin; origins are never pooled. */
  observed_counts: Partial<Record<DataOrigin, number>>
}

export interface ScheduleCoverage {
  schedule_id: string
  metric: string
  planned_events: number
  events_with_observations: Partial<Record<DataOrigin, number>>
  events: EventCoverage[]
  unscheduled_observations: Partial<Record<DataOrigin, number>>
  note: string
}
