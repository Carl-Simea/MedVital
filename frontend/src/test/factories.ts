import type { HealthObservation } from '../domain/observation'

export function makeObservation(overrides: Partial<HealthObservation> = {}): HealthObservation {
  return {
    schema_version: 1,
    id: crypto.randomUUID(),
    subject_id: 'SIM-T01',
    module: 'radiation',
    metric: 'radiation.absorbed_dose_daily',
    value: 1,
    unit: 'mGy',
    observed_at: '2030-01-01T00:00:00Z',
    recorded_at: '2030-01-01T00:00:00Z',
    context: {},
    provenance: { data_origin: 'simulated', source: 'vitest', generator_version: 'test', seed: 1 },
    ...overrides,
  }
}
