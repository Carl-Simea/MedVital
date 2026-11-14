import type { HealthObservation } from "../src/domain/types";

let counter = 0;

export function makeObservation(overrides: Partial<HealthObservation> = {}): HealthObservation {
  counter += 1;
  return {
    schema_version: 1,
    id: `00000000-0000-4000-8000-${String(counter).padStart(12, "0")}`,
    astronaut_id: "SIM-001",
    module: "cardiovascular",
    metric: "heart_rate",
    value: 60,
    unit: "bpm",
    observed_at: "2030-01-01T00:00:00Z",
    provenance: {
      origin: "simulated",
      source: "test",
      source_ref: null,
      method: "test_v1",
      seed: 1,
      derived_from: [],
    },
    context: {},
    device_id: null,
    ...overrides,
  };
}

let dbCounter = 0;
/** A unique database name per test so tests never share state. */
export function freshDbName(): string {
  dbCounter += 1;
  return `medvital-test-${dbCounter}`;
}
