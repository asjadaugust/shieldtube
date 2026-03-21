CREATE TABLE IF NOT EXISTS recommendation_runs (
    run_id TEXT PRIMARY KEY,
    run_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,
    model_name TEXT,
    video_count INTEGER DEFAULT 0
);

CREATE TABLE IF NOT EXISTS recommendations (
    video_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    score REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'ml',
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (video_id, run_id),
    FOREIGN KEY (run_id) REFERENCES recommendation_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_recommendations_score ON recommendations(run_id, score DESC);

CREATE TABLE IF NOT EXISTS watch_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    session_start TEXT NOT NULL,
    completion_rate REAL DEFAULT 0,
    pause_count INTEGER DEFAULT 0,
    seek_forward_count INTEGER DEFAULT 0,
    avg_playback_speed REAL DEFAULT 1.0,
    time_of_day INTEGER,
    abandoned_at_pct REAL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_watch_signals_video ON watch_signals(video_id);

ALTER TABLE videos ADD COLUMN cached_at TEXT;
