"""Python dataclasses matching the SQLite schema defined in 001_initial_schema.sql."""
from __future__ import annotations

import json
from dataclasses import dataclass, field
from datetime import datetime, timezone


@dataclass
class Video:
    id: str
    title: str
    channel_name: str
    channel_id: str
    view_count: int | None = None
    duration: int | None = None
    published_at: str | None = None
    description: str | None = None
    thumbnail_path: str | None = None
    cached_video_path: str | None = None
    cache_status: str | None = "none"
    last_accessed: str | None = None
    created_at: str | None = None
    updated_at: str | None = None
    cached_at: str | None = None
    download_source: str | None = None
    chapters_json: str | None = None


@dataclass
class FeedCache:
    feed_type: str
    video_ids_json: str
    fetched_at: str
    etag: str | None = None

    @property
    def video_ids(self) -> list[str]:
        """Parse the JSON-encoded video_ids_json into a list of strings."""
        return json.loads(self.video_ids_json)


@dataclass
class Thumbnail:
    video_id: str
    resolution: str
    local_path: str
    fetched_at: str
    content_hash: str | None = None


@dataclass
class AuthToken:
    id: int
    access_token: str
    refresh_token: str | None = None
    token_type: str | None = "Bearer"
    expires_at: str | None = None
    scopes: str | None = None
    created_at: str | None = None
    updated_at: str | None = None

    @property
    def is_expired(self) -> bool:
        """Return True if the token has expired or has no expiry timestamp."""
        if self.expires_at is None:
            return True
        try:
            # Parse ISO format; add UTC if no timezone info present
            expires = datetime.fromisoformat(self.expires_at)
            if expires.tzinfo is None:
                expires = expires.replace(tzinfo=timezone.utc)
            return datetime.now(timezone.utc) >= expires
        except ValueError:
            return True


@dataclass
class WatchHistoryEntry:
    video_id: str
    watched_at: str
    position_seconds: int = 0
    duration: int | None = None
    completed: int = 0


@dataclass
class RecommendationRun:
    run_id: str
    run_at: str
    source: str
    model_name: str | None = None
    video_count: int = 0


@dataclass
class Recommendation:
    video_id: str
    run_id: str
    score: float
    source: str = "ml"
    reason: str | None = None
    created_at: str | None = None


@dataclass
class WatchSignal:
    id: int | None = None
    video_id: str = ""
    session_start: str = ""
    completion_rate: float = 0.0
    pause_count: int = 0
    seek_forward_count: int = 0
    avg_playback_speed: float = 1.0
    time_of_day: int | None = None
    abandoned_at_pct: float | None = None
    updated_at: str | None = None


@dataclass
class VideoRating:
    video_id: str
    rating: str
    rated_at: str | None = None
