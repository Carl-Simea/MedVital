-- MedVital link to Earth (D1). Every record the spacecraft sends, kept forever; NASA pulls by seq.
CREATE TABLE IF NOT EXISTS records (
    seq          INTEGER PRIMARY KEY AUTOINCREMENT,  -- NASA's pull cursor
    id           TEXT NOT NULL UNIQUE,               -- the record id: the same id is never stored twice
    type         TEXT NOT NULL,                      -- reading | alert | summary | test | lab | profile | event
    astronaut_id TEXT NOT NULL,
    body         TEXT NOT NULL,                      -- the whole record as JSON
    received_at  TEXT NOT NULL
);
CREATE INDEX IF NOT EXISTS records_by_astronaut ON records (astronaut_id, type);

CREATE TABLE IF NOT EXISTS settings (key TEXT PRIMARY KEY, value TEXT NOT NULL);  -- link_up = 1 | 0

CREATE TABLE IF NOT EXISTS ai_calls (minute TEXT PRIMARY KEY, n INTEGER NOT NULL);  -- demo rate limit
