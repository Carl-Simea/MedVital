-- The checker (parts report in every few seconds), the link log, and DONKI space weather fetched by Cloudflare.
CREATE TABLE IF NOT EXISTS nodes (node TEXT PRIMARY KEY, seen_at TEXT NOT NULL, report TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS link_log (id INTEGER PRIMARY KEY AUTOINCREMENT, at TEXT NOT NULL,
    event TEXT NOT NULL, detail TEXT NOT NULL);
CREATE TABLE IF NOT EXISTS donki (id TEXT PRIMARY KEY, type TEXT NOT NULL, start TEXT NOT NULL,
    end_time TEXT, summary TEXT NOT NULL, link TEXT, fetched_at TEXT NOT NULL);
