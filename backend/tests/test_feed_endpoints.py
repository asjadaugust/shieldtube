"""Tests for /api/feed/home and /api/feed/subscriptions endpoints."""
from __future__ import annotations

import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch, MagicMock

from backend.db.database import _run_migrations

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Sample video data
# ---------------------------------------------------------------------------

SAMPLE_VIDEOS = [
    {
        "id": "dQw4w9WgXcQ",
        "title": "Never Gonna Give You Up",
        "channel_name": "Rick Astley",
        "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
        "view_count": 1_500_000_000,
        "duration": 213,
        "published_at": "2009-10-25T06:57:33Z",
        "description": "The official video",
    },
    {
        "id": "9bZkp7q19f0",
        "title": "Gangnam Style",
        "channel_name": "officialpsy",
        "channel_id": "UCrDkAvwZum-UTjHmzDI2iIw",
        "view_count": 4_800_000_000,
        "duration": 252,
        "published_at": "2012-07-15T07:46:32Z",
        "description": "PSY - GANGNAM STYLE",
    },
]


# ---------------------------------------------------------------------------
# Fixture: in-memory DB + patched app
# ---------------------------------------------------------------------------

@pytest.fixture
async def mem_db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


@pytest.fixture
async def client(mem_db):
    """AsyncClient wired to the FastAPI app with a real in-memory DB."""
    from backend.api.main import app

    async def _fake_get_db():
        return mem_db

    with (
        patch("backend.db.database.init_db", new_callable=AsyncMock),
        patch("backend.db.database.close_db", new_callable=AsyncMock),
        patch("backend.api.routers.feed.get_db", new=_fake_get_db),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ---------------------------------------------------------------------------
# /feed/home tests
# ---------------------------------------------------------------------------

class TestHomeFeed:
    async def test_home_feed_returns_correct_shape(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.feed.YouTubeAPI.get_home_feed",
                new_callable=AsyncMock,
                return_value=(SAMPLE_VIDEOS, False, None),
            ),
            patch(
                "backend.api.routers.feed.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.feed.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/feed/home")

        assert response.status_code == 200
        data = response.json()
        assert data["feed_type"] == "home"
        assert isinstance(data["videos"], list)
        assert len(data["videos"]) == 2

    async def test_home_feed_video_fields(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.feed.YouTubeAPI.get_home_feed",
                new_callable=AsyncMock,
                return_value=(SAMPLE_VIDEOS, False, None),
            ),
            patch(
                "backend.api.routers.feed.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.feed.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/feed/home")

        data = response.json()
        video = data["videos"][0]
        assert video["id"] == "dQw4w9WgXcQ"
        assert video["title"] == "Never Gonna Give You Up"
        assert video["channel_name"] == "Rick Astley"
        assert video["channel_id"] == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert video["view_count"] == 1_500_000_000
        assert video["duration"] == 213
        assert video["published_at"] == "2009-10-25T06:57:33Z"

    async def test_home_feed_thumbnail_url_pattern(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.feed.YouTubeAPI.get_home_feed",
                new_callable=AsyncMock,
                return_value=(SAMPLE_VIDEOS, False, None),
            ),
            patch(
                "backend.api.routers.feed.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.feed.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/feed/home")

        data = response.json()
        for video in data["videos"]:
            expected = f"/api/video/{video['id']}/thumbnail?res=maxres"
            assert video["thumbnail_url"] == expected

    async def test_home_feed_not_from_cache(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.feed.YouTubeAPI.get_home_feed",
                new_callable=AsyncMock,
                return_value=(SAMPLE_VIDEOS, False, None),
            ),
            patch(
                "backend.api.routers.feed.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.feed.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/feed/home")

        data = response.json()
        assert data["from_cache"] is False
        assert data["cached_at"] is None

    async def test_home_feed_from_cache(self, client, mem_db):
        cached_at = "2026-03-20T10:00:00+00:00"
        with (
            patch(
                "backend.api.routers.feed.YouTubeAPI.get_home_feed",
                new_callable=AsyncMock,
                return_value=(SAMPLE_VIDEOS, True, cached_at),
            ),
            patch(
                "backend.api.routers.feed.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.feed.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/feed/home")

        data = response.json()
        assert data["from_cache"] is True
        assert data["cached_at"] == cached_at


# ---------------------------------------------------------------------------
# /feed/subscriptions tests
# ---------------------------------------------------------------------------

class TestSubscriptionsFeed:
    async def test_subscriptions_feed_returns_correct_shape(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.feed.YouTubeAPI.get_subscriptions",
                new_callable=AsyncMock,
                return_value=(SAMPLE_VIDEOS, False, None),
            ),
            patch(
                "backend.api.routers.feed.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.feed.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/feed/subscriptions")

        assert response.status_code == 200
        data = response.json()
        assert data["feed_type"] == "subscriptions"
        assert isinstance(data["videos"], list)
        assert len(data["videos"]) == 2

    async def test_subscriptions_feed_thumbnail_url_pattern(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.feed.YouTubeAPI.get_subscriptions",
                new_callable=AsyncMock,
                return_value=(SAMPLE_VIDEOS, False, None),
            ),
            patch(
                "backend.api.routers.feed.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.feed.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/feed/subscriptions")

        data = response.json()
        for video in data["videos"]:
            expected = f"/api/video/{video['id']}/thumbnail?res=maxres"
            assert video["thumbnail_url"] == expected

    async def test_subscriptions_feed_not_from_cache(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.feed.YouTubeAPI.get_subscriptions",
                new_callable=AsyncMock,
                return_value=(SAMPLE_VIDEOS, False, None),
            ),
            patch(
                "backend.api.routers.feed.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.feed.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/feed/subscriptions")

        data = response.json()
        assert data["from_cache"] is False
        assert data["cached_at"] is None
