import { DATA_ORIGINS, MODULE_IDS, type HealthObservation } from "./types";

function isRecord(value: unknown): value is Record<string, unknown> {
  return typeof value === "object" && value !== null && !Array.isArray(value);
}

/** Structural check for data crossing a trust boundary (network or IndexedDB). */
export function isHealthObservation(value: unknown): value is HealthObservation {
  if (!isRecord(value)) return false;
  const p = value.provenance;
  return (
    value.schema_version === 1 &&
    typeof value.id === "string" &&
    typeof value.astronaut_id === "string" &&
    (MODULE_IDS as readonly unknown[]).includes(value.module) &&
    typeof value.metric === "string" &&
    typeof value.value === "number" &&
    Number.isFinite(value.value) &&
    typeof value.unit === "string" &&
    typeof value.observed_at === "string" &&
    isRecord(p) &&
    (DATA_ORIGINS as readonly unknown[]).includes(p.origin) &&
    typeof p.source === "string" &&
    isRecord(value.context)
  );
}
