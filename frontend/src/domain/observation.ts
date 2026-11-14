/**
 * Shared health observation schema (v1) — TypeScript mirror of
 * backend/medvital/core/schema.py. The backend is authoritative; the OpenAPI contract
 * lives in docs/api/openapi.json. Pure types + validation, no React, no storage.
 */

export const SCHEMA_VERSION = 1

export const MODULE_IDS = ['radiation', 'bone', 'cardiovascular', 'behavioral'] as const
export type ModuleId = (typeof MODULE_IDS)[number]

export const DATA_ORIGINS = ['simulated', 'measured', 'modeled'] as const
export type DataOrigin = (typeof DATA_ORIGINS)[number]

export interface Provenance {
  data_origin: DataOrigin
  source: string
  source_ref?: string | null
  method?: string | null
  generator_version?: string | null
  seed?: number | null
  derived_from?: string[]
  license?: string | null
  retrieved_at?: string | null
  notes?: string | null
}

export interface HealthObservation {
  schema_version: typeof SCHEMA_VERSION
  id: string
  subject_id: string
  module: ModuleId
  metric: string
  value: number
  unit: string
  observed_at: string
  recorded_at: string
  context: Record<string, string>
  device_id?: string | null
  quality?: 'valid' | 'suspect' | 'invalid'
  /** Standard uncertainty in `unit`. null/absent = unknown (never treated as 0). */
  uncertainty?: number | null
  provenance: Provenance
  supersedes?: string | null
}

export type ValidationResult =
  | { ok: true; value: HealthObservation }
  | { ok: false; errors: string[] }

const SUBJECT_ID = /^[A-Za-z0-9][A-Za-z0-9_.:-]{0,63}$/
const METRIC_ID = /^[a-z][a-z0-9_]*\.[a-z][a-z0-9_]*$/
const UUID = /^[0-9a-f]{8}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{4}-[0-9a-f]{12}$/i
// ISO-8601 with an explicit offset (Z or ±hh:mm): naive times are rejected like the server does.
const AWARE_DATETIME = /^\d{4}-\d{2}-\d{2}T\d{2}:\d{2}(:\d{2}(\.\d+)?)?(Z|[+-]\d{2}:\d{2})$/

const isRecord = (v: unknown): v is Record<string, unknown> =>
  typeof v === 'object' && v !== null && !Array.isArray(v)

const nonEmpty = (v: unknown): v is string => typeof v === 'string' && v.length > 0

/** Client-side structural validation so a malformed record never enters the outbox. */
export function validateObservation(input: unknown): ValidationResult {
  const errors: string[] = []
  if (!isRecord(input)) return { ok: false, errors: ['observation must be an object'] }
  const o = input

  if (o.schema_version !== SCHEMA_VERSION) errors.push(`schema_version must be ${SCHEMA_VERSION}`)
  if (typeof o.id !== 'string' || !UUID.test(o.id)) errors.push('id must be a UUID')
  if (typeof o.subject_id !== 'string' || !SUBJECT_ID.test(o.subject_id)) errors.push('subject_id is invalid')
  if (!MODULE_IDS.includes(o.module as ModuleId)) errors.push('module is not one of the four modules')
  if (typeof o.metric !== 'string' || !METRIC_ID.test(o.metric)) errors.push('metric must look like "module.name"')
  else if (o.metric.split('.')[0] !== o.module) errors.push('metric does not belong to module')
  if (typeof o.value !== 'number' || !Number.isFinite(o.value)) errors.push('value must be a finite number')
  if (!nonEmpty(o.unit)) errors.push('unit is required')
  if (o.uncertainty != null && (typeof o.uncertainty !== 'number' || !Number.isFinite(o.uncertainty) || o.uncertainty < 0)) {
    errors.push('uncertainty must be a finite number >= 0, or null when unknown')
  }
  for (const key of ['observed_at', 'recorded_at'] as const) {
    const v = o[key]
    if (typeof v !== 'string' || !AWARE_DATETIME.test(v) || Number.isNaN(Date.parse(v))) {
      errors.push(`${key} must be an ISO-8601 timestamp with a UTC offset`)
    }
  }
  if (!isRecord(o.context)) errors.push('context must be an object')
  else if (!Object.values(o.context).every((v) => typeof v === 'string')) errors.push('context values must be strings')
  if (o.supersedes != null && (typeof o.supersedes !== 'string' || !UUID.test(o.supersedes) || o.supersedes === o.id)) {
    errors.push('supersedes must be a different observation UUID')
  }

  const p = o.provenance
  if (!isRecord(p)) errors.push('provenance is required')
  else {
    if (!DATA_ORIGINS.includes(p.data_origin as DataOrigin)) errors.push('provenance.data_origin is invalid')
    if (!nonEmpty(p.source)) errors.push('provenance.source is required')
    if (p.data_origin === 'simulated' && (!nonEmpty(p.generator_version) || typeof p.seed !== 'number')) {
      errors.push('simulated provenance requires generator_version and seed')
    }
    if (p.data_origin === 'measured') {
      if (!nonEmpty(p.source_ref)) errors.push('measured provenance requires source_ref')
      if (p.generator_version != null || p.seed != null) errors.push('measured provenance must not carry generator fields')
    }
    if (p.data_origin === 'modeled') {
      if (!nonEmpty(p.method)) errors.push('modeled provenance requires method')
      if (p.generator_version != null) errors.push('modeled provenance must not carry generator_version')
    }
  }

  return errors.length ? { ok: false, errors } : { ok: true, value: o as unknown as HealthObservation }
}

export function newObservationId(): string {
  return crypto.randomUUID()
}
