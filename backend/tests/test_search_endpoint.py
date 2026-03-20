"""Tests for GET /api/search endpoint."""
from __future__ import annotations

import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from backend.db.database import _run_migrations

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Sample data
# ---------------------------------------------------------------------------

SAMPLE_SEARCH_RESULTS = [
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
# Fixtures
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
        patch("backend.api.routers.search.get_db", new=_fake_get_db),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

class TestSearchEndpoint:
    async def test_search_returns_correct_shape(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.search.YouTubeAPI.search",
                new_callable=AsyncMock,
                return_value=SAMPLE_SEARCH_RESULTS,
            ),
            patch(
                "backend.api.routers.search.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.search.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/search?q=rick+astley")

        assert response.status_code == 200
        data = response.json()
        assert isinstance(data["videos"], list)
        assert len(data["videos"]) == 2

    async def test_search_feed_type_includes_query(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.search.YouTubeAPI.search",
                new_callable=AsyncMock,
                return_value=SAMPLE_SEARCH_RESULTS,
            ),
            patch(
                "backend.api.routers.search.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.search.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/search?q=rick+astley")

        data = response.json()
        assert data["feed_type"] == "search:rick astley"

    async def test_search_thumbnail_url_pattern(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.search.YouTubeAPI.search",
                new_callable=AsyncMock,
                return_value=SAMPLE_SEARCH_RESULTS,
            ),
            patch(
                "backend.api.routers.search.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.search.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/search?q=test")

        data = response.json()
        for video in data["videos"]:
            expected = f"/api/video/{video['id']}/thumbnail?res=maxres"
            assert video["thumbnail_url"] == expected

    async def test_search_requires_q_parameter(self, client, mem_db):
        response = await client.get("/api/search")
        assert response.status_code == 422

    async def test_search_q_must_not_be_empty(self, client, mem_db):
        response = await client.get("/api/search?q=")
        assert response.status_code == 422

    async def test_search_not_from_cache(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.search.YouTubeAPI.search",
                new_callable=AsyncMock,
                return_value=SAMPLE_SEARCH_RESULTS,
            ),
            patch(
                "backend.api.routers.search.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.search.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/search?q=test")

        data = response.json()
        assert data["from_cache"] is False
        assert data["cached_at"] is None

    async def test_search_empty_results(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.search.YouTubeAPI.search",
                new_callable=AsyncMock,
                return_value=[],
            ),
            patch(
                "backend.api.routers.search.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.search.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/search?q=xyzzy123notarealvideo")

        assert response.status_code == 200
        data = response.json()
        assert data["videos"] == []
        assert data["feed_type"] == "search:xyzzy123notarealvideo"

    async def test_search_video_fields(self, client, mem_db):
        with (
            patch(
                "backend.api.routers.search.YouTubeAPI.search",
                new_callable=AsyncMock,
                return_value=SAMPLE_SEARCH_RESULTS,
            ),
            patch(
                "backend.api.routers.search.VideoRepo.upsert_many_from_dicts",
                new_callable=AsyncMock,
            ),
            patch(
                "backend.api.routers.search.ThumbnailCache.cache_thumbnails",
                new_callable=AsyncMock,
            ),
        ):
            response = await client.get("/api/search?q=rickroll")

        data = response.json()
        video = data["videos"][0]
        assert video["id"] == "dQw4w9WgXcQ"
        assert video["title"] == "Never Gonna Give You Up"
        assert video["channel_name"] == "Rick Astley"
        assert video["channel_id"] == "UCuAXFkgsw1L7xaCfnd5JJOw"
        assert video["view_count"] == 1_500_000_000
        assert video["duration"] == 213
        assert video["published_at"] == "2009-10-25T06:57:33Z"
