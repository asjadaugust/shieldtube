CREATE TABLE IF NOT EXISTS watch_history (
    video_id TEXT PRIMARY KEY,
    watched_at TEXT NOT NULL,
    position_seconds INTEGER DEFAULT 0,
    duration INTEGER,
    completed INTEGER DEFAULT 0
);
