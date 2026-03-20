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
