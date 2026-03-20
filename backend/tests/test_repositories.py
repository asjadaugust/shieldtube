"""Tests for all repository CRUD operations."""
from __future__ import annotations

import json
from datetime import datetime, timezone, timedelta

import pytest
import aiosqlite

from backend.db.database import _run_migrations
from backend.db.models import Video, FeedCache, Thumbnail, AuthToken
from backend.db.repositories import VideoRepo, FeedCacheRepo, ThumbnailRepo, AuthTokenRepo


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_video(
    video_id: str = "vid1",
    title: str = "Test Video",
    channel_name: str = "Test Channel",
    channel_id: str = "ch1",
) -> Video:
    return Video(
        id=video_id,
        title=title,
        channel_name=channel_name,
        channel_id=channel_id,
    )


# ---------------------------------------------------------------------------
# VideoRepo
# ---------------------------------------------------------------------------

class TestVideoRepo:
    async def test_upsert_and_get(self, db):
        repo = VideoRepo(db)
        video = make_video()
        await repo.upsert(video)

        result = await repo.get("vid1")
        assert result is not None
        assert result.id == "vid1"
        assert result.title == "Test Video"
        assert result.channel_name == "Test Channel"

    async def test_get_returns_none_for_missing(self, db):
        repo = VideoRepo(db)
        result = await repo.get("nonexistent")
        assert result is None

    async def test_upsert_is_idempotent(self, db):
        repo = VideoRepo(db)
        video = make_video(title="Original Title")
        await repo.upsert(video)

        updated = make_video(title="Updated Title")
        await repo.upsert(updated)

        result = await repo.get("vid1")
        assert result is not None
        assert result.title == "Updated Title"

    async def test_upsert_optional_fields(self, db):
        repo = VideoRepo(db)
        video = Video(
            id="vid2",
            title="Rich Video",
            channel_name="Rich Channel",
            channel_id="ch2",
            view_count=1_000_000,
            duration=600,
            published_at="2024-01-01T00:00:00Z",
            description="A description",
            thumbnail_path="/cache/thumb.jpg",
            cache_status="cached",
        )
        await repo.upsert(video)

        result = await repo.get("vid2")
        assert result is not None
        assert result.view_count == 1_000_000
        assert result.duration == 600
        assert result.description == "A description"
        assert result.cache_status == "cached"

    async def test_upsert_many(self, db):
        repo = VideoRepo(db)
        videos = [make_video(f"v{i}", f"Video {i}", "Chan", "ch") for i in range(5)]
        await repo.upsert_many(videos)

        for i in range(5):
            result = await repo.get(f"v{i}")
            assert result is not None
            assert result.title == f"Video {i}"

    async def test_upsert_many_empty_list(self, db):
        repo = VideoRepo(db)
        await repo.upsert_many([])  # should not raise

    async def test_upsert_many_from_dicts(self, db):
        repo = VideoRepo(db)
        dicts = [
            {"id": "d1", "title": "Dict Video 1", "channel_name": "Chan", "channel_id": "ch"},
            {"id": "d2", "title": "Dict Video 2", "channel_name": "Chan", "channel_id": "ch"},
        ]
        await repo.upsert_many_from_dicts(dicts)

        r1 = await repo.get("d1")
        r2 = await repo.get("d2")
        assert r1 is not None and r1.title == "Dict Video 1"
        assert r2 is not None and r2.title == "Dict Video 2"

    async def test_upsert_many_from_dicts_partial_fields(self, db):
        """Dicts with only the required fields (id, title, channel_name, channel_id) must work."""
        repo = VideoRepo(db)
        dicts = [{"id": "p1", "title": "Partial", "channel_name": "C", "channel_id": "c"}]
        await repo.upsert_many_from_dicts(dicts)

        result = await repo.get("p1")
        assert result is not None
        assert result.title == "Partial"
        assert result.view_count is None

    async def test_get_many_preserves_order(self, db):
        repo = VideoRepo(db)
        videos = [make_video(f"v{i}", f"Video {i}", "Chan", "ch") for i in range(5)]
        await repo.upsert_many(videos)

        ids = ["v4", "v1", "v3", "v0", "v2"]
        results = await repo.get_many(ids)
        assert [r.id for r in results] == ids

    async def test_get_many_skips_missing(self, db):
        repo = VideoRepo(db)
        await repo.upsert(make_video("exists"))

        results = await repo.get_many(["missing", "exists"])
        assert len(results) == 1
        assert results[0].id == "exists"

    async def test_get_many_empty(self, db):
        repo = VideoRepo(db)
        results = await repo.get_many([])
        assert results == []


# ---------------------------------------------------------------------------
# FeedCacheRepo
# ---------------------------------------------------------------------------

class TestFeedCacheRepo:
    async def test_get_returns_none_when_empty(self, db):
        repo = FeedCacheRepo(db)
        result = await repo.get("home")
        assert result is None

    async def test_upsert_and_get(self, db):
        repo = FeedCacheRepo(db)
        fc = FeedCache(
            feed_type="home",
            video_ids_json=json.dumps(["v1", "v2", "v3"]),
            etag="etag123",
            fetched_at="2024-01-01T00:00:00Z",
        )
        await repo.upsert(fc)

        result = await repo.get("home")
        assert result is not None
        assert result.feed_type == "home"
        assert result.etag == "etag123"
        assert result.video_ids == ["v1", "v2", "v3"]

    async def test_upsert_is_idempotent(self, db):
        repo = FeedCacheRepo(db)
        fc1 = FeedCache(
            feed_type="home",
            video_ids_json=json.dumps(["v1"]),
            fetched_at="2024-01-01T00:00:00Z",
        )
        await repo.upsert(fc1)

        fc2 = FeedCache(
            feed_type="home",
            video_ids_json=json.dumps(["v1", "v2"]),
            fetched_at="2024-02-01T00:00:00Z",
        )
        await repo.upsert(fc2)

        result = await repo.get("home")
        assert result is not None
        assert result.video_ids == ["v1", "v2"]

    async def test_video_ids_property(self, db):
        repo = FeedCacheRepo(db)
        fc = FeedCache(
            feed_type="subs",
            video_ids_json=json.dumps(["a", "b", "c"]),
            fetched_at="2024-01-01T00:00:00Z",
        )
        await repo.upsert(fc)
        result = await repo.get("subs")
        assert result is not None
        assert isinstance(result.video_ids, list)
        assert result.video_ids == ["a", "b", "c"]

    async def test_multiple_feed_types(self, db):
        repo = FeedCacheRepo(db)
        for ft in ["home", "subscriptions", "history"]:
            fc = FeedCache(
                feed_type=ft,
                video_ids_json=json.dumps([ft]),
                fetched_at="2024-01-01T00:00:00Z",
            )
            await repo.upsert(fc)

        for ft in ["home", "subscriptions", "history"]:
            result = await repo.get(ft)
            assert result is not None
            assert result.video_ids == [ft]


# ---------------------------------------------------------------------------
# ThumbnailRepo
# ---------------------------------------------------------------------------

class TestThumbnailRepo:
    async def test_get_returns_none_when_missing(self, db):
        repo = ThumbnailRepo(db)
        result = await repo.get("v1", "high")
        assert result is None

    async def test_upsert_and_get(self, db):
        repo = ThumbnailRepo(db)
        thumb = Thumbnail(
            video_id="v1",
            resolution="high",
            local_path="/cache/v1_high.jpg",
            fetched_at="2024-01-01T00:00:00Z",
            content_hash="abc123",
        )
        await repo.upsert(thumb)

        result = await repo.get("v1", "high")
        assert result is not None
        assert result.video_id == "v1"
        assert result.resolution == "high"
        assert result.local_path == "/cache/v1_high.jpg"
        assert result.content_hash == "abc123"

    async def test_upsert_is_idempotent(self, db):
        repo = ThumbnailRepo(db)
        t1 = Thumbnail(
            video_id="v1",
            resolution="high",
            local_path="/old/path.jpg",
            fetched_at="2024-01-01T00:00:00Z",
        )
        await repo.upsert(t1)

        t2 = Thumbnail(
            video_id="v1",
            resolution="high",
            local_path="/new/path.jpg",
            fetched_at="2024-02-01T00:00:00Z",
        )
        await repo.upsert(t2)

        result = await repo.get("v1", "high")
        assert result is not None
        assert result.local_path == "/new/path.jpg"

    async def test_get_cached_ids(self, db):
        repo = ThumbnailRepo(db)
        for vid in ["v1", "v2", "v3"]:
            thumb = Thumbnail(
                video_id=vid,
                resolution="high",
                local_path=f"/cache/{vid}.jpg",
                fetched_at="2024-01-01T00:00:00Z",
            )
            await repo.upsert(thumb)

        cached = await repo.get_cached_ids(["v1", "v2", "v4", "v5"], "high")
        assert cached == {"v1", "v2"}

    async def test_get_cached_ids_resolution_specific(self, db):
        repo = ThumbnailRepo(db)
        thumb = Thumbnail(
            video_id="v1",
            resolution="high",
            local_path="/cache/v1.jpg",
            fetched_at="2024-01-01T00:00:00Z",
        )
        await repo.upsert(thumb)

        cached_high = await repo.get_cached_ids(["v1"], "high")
        cached_medium = await repo.get_cached_ids(["v1"], "medium")
        assert cached_high == {"v1"}
        assert cached_medium == set()

    async def test_get_cached_ids_empty_input(self, db):
        repo = ThumbnailRepo(db)
        result = await repo.get_cached_ids([], "high")
        assert result == set()


# ---------------------------------------------------------------------------
# AuthTokenRepo
# ---------------------------------------------------------------------------

class TestAuthTokenRepo:
    async def test_get_returns_none_when_empty(self, db):
        repo = AuthTokenRepo(db)
        result = await repo.get()
        assert result is None

    async def test_upsert_and_get(self, db):
        repo = AuthTokenRepo(db)
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        token = AuthToken(
            id=1,
            access_token="access123",
            refresh_token="refresh456",
            token_type="Bearer",
            expires_at=future,
            scopes="https://www.googleapis.com/auth/youtube.readonly",
        )
        await repo.upsert(token)

        result = await repo.get()
        assert result is not None
        assert result.access_token == "access123"
        assert result.refresh_token == "refresh456"
        assert result.token_type == "Bearer"

    async def test_upsert_always_uses_id_1(self, db):
        """Multiple upserts must not create multiple rows."""
        repo = AuthTokenRepo(db)
        for i in range(3):
            token = AuthToken(id=1, access_token=f"token{i}", refresh_token=None)
            await repo.upsert(token)

        async with db.execute("SELECT COUNT(*) as cnt FROM auth_tokens") as cursor:
            row = await cursor.fetchone()
        assert row["cnt"] == 1

        result = await repo.get()
        assert result is not None
        assert result.access_token == "token2"

    async def test_is_expired_when_expires_at_is_none(self, db):
        token = AuthToken(id=1, access_token="tok", expires_at=None)
        assert token.is_expired is True

    async def test_is_expired_when_in_future(self, db):
        future = (datetime.now(timezone.utc) + timedelta(hours=1)).isoformat()
        token = AuthToken(id=1, access_token="tok", expires_at=future)
        assert token.is_expired is False

    async def test_is_expired_when_in_past(self, db):
        past = (datetime.now(timezone.utc) - timedelta(hours=1)).isoformat()
        token = AuthToken(id=1, access_token="tok", expires_at=past)
        assert token.is_expired is True

    async def test_upsert_minimal_token(self, db):
        """Token with only access_token (no refresh, no expiry) must persist."""
        repo = AuthTokenRepo(db)
        token = AuthToken(id=1, access_token="minimal_token")
        await repo.upsert(token)

        result = await repo.get()
        assert result is not None
        assert result.access_token == "minimal_token"
        assert result.refresh_token is None
