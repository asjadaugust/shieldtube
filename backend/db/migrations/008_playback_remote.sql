CREATE TABLE IF NOT EXISTS playback_commands (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    action TEXT NOT NULL,
    value TEXT,
    created_at TEXT DEFAULT (datetime('now'))
);

CREATE TABLE IF NOT EXISTS playback_status (
    id INTEGER PRIMARY KEY CHECK (id = 1),
    video_id TEXT,
    title TEXT,
    position_ms INTEGER,
    duration_ms INTEGER,
    is_playing INTEGER,
    speed REAL DEFAULT 1.0,
    updated_at TEXT
);
