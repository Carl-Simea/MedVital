// Mirrors the backend contract (contracts/observation.schema.json). No science lives here:
// all calculations are performed by the backend; the frontend stores and presents values.

export type ModuleId = "radiation" | "bone" | "cardiovascular" | "behavioral";
export const MODULE_IDS: readonly ModuleId[] = [
  "radiation",
  "bone",
  "cardiovascular",
  "behavioral",
];

export type DataOrigin = "simulated" | "measured" | "modeled";
export const DATA_ORIGINS: readonly DataOrigin[] = ["simulated", "measured", "modeled"];

export interface Provenance {
  origin: DataOrigin;
  source: string;
  source_ref: string | null;
  method: string | null;
  seed: number | null;
  derived_from: string[];
}

export interface HealthObservation {
  schema_version: 1;
  id: string;
  astronaut_id: string;
  module: ModuleId;
  metric: string;
  value: number;
  unit: string;
  observed_at: string; // ISO 8601, timezone-aware
  provenance: Provenance;
  context: Record<string, string>;
  device_id: string | null;
}

export interface RejectedItem {
  id: string | null;
  reason: string;
}

export interface SyncPushResponse {
  accepted: string[];
  duplicates: string[];
  rejected: RejectedItem[];
}

export interface SyncPullResponse {
  observations: HealthObservation[];
  next_cursor: number;
  has_more: boolean;
}
