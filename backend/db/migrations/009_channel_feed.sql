CREATE TABLE IF NOT EXISTS channel_feed_cache (
    video_id TEXT NOT NULL,
    channel_id TEXT NOT NULL,
    fetched_at TEXT NOT NULL,
    PRIMARY KEY (video_id)
);
