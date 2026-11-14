-- MEDVITAL PostgreSQL schema (architecture skeleton; not yet exercised against a live database).
-- Observations are append-only. `server_seq` is the sync cursor handed to offline clients.

CREATE TABLE IF NOT EXISTS health_observations (
    server_seq     BIGINT GENERATED ALWAYS AS IDENTITY UNIQUE,
    id             UUID PRIMARY KEY,
    schema_version SMALLINT NOT NULL,
    astronaut_id   TEXT NOT NULL,
    module         TEXT NOT NULL
                   CHECK (module IN ('radiation', 'bone', 'cardiovascular', 'behavioral')),
    metric         TEXT NOT NULL,
    value          DOUBLE PRECISION NOT NULL,
    unit           TEXT NOT NULL,
    observed_at    TIMESTAMPTZ NOT NULL,
    origin         TEXT NOT NULL CHECK (origin IN ('simulated', 'measured', 'modeled')),
    provenance     JSONB NOT NULL,
    context        JSONB NOT NULL DEFAULT '{}'::jsonb,
    device_id      TEXT,
    -- Canonical JSON of the full observation; used to tell duplicates from conflicts.
    payload        JSONB NOT NULL,
    received_at    TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_obs_astronaut_module_metric_time
    ON health_observations (astronaut_id, module, metric, observed_at);
CREATE INDEX IF NOT EXISTS idx_obs_origin ON health_observations (origin);
