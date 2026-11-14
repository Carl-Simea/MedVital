-- MEDVITAL PostgreSQL schema, version 1.
-- STATUS: design artefact. Not yet executed against a live PostgreSQL server
-- (no server was available when this was written). Review before first use.
--
-- Principles
--   * observations are append-only (immutability trigger below);
--   * every row carries its provenance and data_origin;
--   * server_seq is the sync cursor.

CREATE TABLE IF NOT EXISTS observations (
    id              uuid PRIMARY KEY,
    server_seq      bigint GENERATED ALWAYS AS IDENTITY UNIQUE,
    schema_version  integer          NOT NULL CHECK (schema_version = 1),
    subject_id      text             NOT NULL,
    module          text             NOT NULL CHECK (module IN ('radiation','bone','cardiovascular','behavioral')),
    metric          text             NOT NULL CHECK (split_part(metric, '.', 1) = module),
    value           double precision NOT NULL CHECK (value = value AND value NOT IN ('Infinity','-Infinity')),
    unit            text             NOT NULL,
    observed_at     timestamptz      NOT NULL,
    recorded_at     timestamptz      NOT NULL,
    received_at     timestamptz      NOT NULL DEFAULT now(),
    context         jsonb            NOT NULL DEFAULT '{}'::jsonb,
    -- Denormalised from provenance so it can be indexed and constrained.
    data_origin     text             NOT NULL CHECK (data_origin IN ('simulated','measured','modeled')),
    provenance      jsonb            NOT NULL,
    supersedes      uuid,
    fingerprint     text             NOT NULL,
    CHECK (supersedes IS NULL OR supersedes <> id),
    CHECK (provenance ->> 'data_origin' = data_origin)
);

CREATE INDEX IF NOT EXISTS observations_subject_module_time
    ON observations (subject_id, module, observed_at);
CREATE INDEX IF NOT EXISTS observations_origin ON observations (data_origin);

-- Append-only: forbid UPDATE and DELETE. Corrections are new rows with `supersedes`.
CREATE OR REPLACE FUNCTION observations_immutable() RETURNS trigger AS $$
BEGIN
    RAISE EXCEPTION 'observations are append-only (% blocked)', TG_OP;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS observations_no_update_delete ON observations;
CREATE TRIGGER observations_no_update_delete
    BEFORE UPDATE OR DELETE ON observations
    FOR EACH ROW EXECUTE FUNCTION observations_immutable();

-- Sync note: GENERATED ... AS IDENTITY values are assigned at insert time, not commit time,
-- so a long-running transaction can commit a lower server_seq after a higher one is already
-- visible. Writers must insert in short transactions (one per push batch), and clients keep
-- pulling idempotently; see docs/ARCHITECTURE.md §5.4.
