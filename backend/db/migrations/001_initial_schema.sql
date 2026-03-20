CREATE TABLE IF NOT EXISTS videos (
    id TEXT PRIMARY KEY,
    title TEXT NOT NULL,
    channel_name TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    view_count INTEGER,
    duration INTEGER,
    published_at TEXT,
    description TEXT,
    thumbnail_path TEXT,
    cached_video_path TEXT,
    cache_status TEXT DEFAULT 'none',
    last_accessed TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE TABLE IF NOT EXISTS feed_cache (
    feed_type TEXT PRIMARY KEY,
    video_ids_json TEXT NOT NULL,
    etag TEXT,
    fetched_at TEXT NOT NULL
);

CREATE TABLE IF NOT EXISTS thumbnails (
    video_id TEXT NOT NULL,
    resolution TEXT NOT NULL,
    local_path TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    content_hash TEXT,
    PRIMARY KEY (video_id, resolution)
);

CREATE TABLE IF NOT EXISTS auth_tokens (
    id INTEGER PRIMARY KEY DEFAULT 1,
    access_token TEXT NOT NULL,
    refresh_token TEXT,
    token_type TEXT DEFAULT 'Bearer',
    expires_at TEXT,
    scopes TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);
