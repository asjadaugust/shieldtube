"""Tests for watch history and playback progress endpoints."""
from __future__ import annotations

import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch

from backend.db.database import _run_migrations
from backend.db.models import Video, WatchHistoryEntry

pytestmark = pytest.mark.asyncio

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
        patch("backend.api.routers.watch.get_db", new=_fake_get_db),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_video(db, video_id: str, cache_status: str = "none") -> None:
    """Insert a minimal video row into the DB."""
    from backend.db.repositories import VideoRepo

    repo = VideoRepo(db)
    await repo.upsert(
        Video(
            id=video_id,
            title=f"Title {video_id}",
            channel_name="Test Channel",
            channel_id="UC_test",
            duration=600,
            cache_status=cache_status,
        )
    )


async def _seed_watch(db, video_id: str, position: int, watched_at: str) -> None:
    """Insert a watch history entry directly into the DB."""
    from backend.db.repositories import WatchHistoryRepo

    repo = WatchHistoryRepo(db)
    entry = WatchHistoryEntry(
        video_id=video_id,
        watched_at=watched_at,
        position_seconds=position,
        duration=600,
    )
    await repo.upsert(entry)


# ---------------------------------------------------------------------------
# POST /api/video/{video_id}/progress
# ---------------------------------------------------------------------------


class TestReportProgress:
    async def test_report_progress_upserts(self, client, mem_db):
        response = await client.post(
            "/api/video/vid1/progress",
            json={"position_seconds": 120, "duration": 600},
        )
        assert response.status_code == 200
        assert response.json() == {"status": "ok"}

    async def test_report_progress_updates_position(self, client, mem_db):
        """Second POST with a different position should overwrite the first."""
        await client.post(
            "/api/video/vid1/progress",
            json={"position_seconds": 120, "duration": 600},
        )
        await client.post(
            "/api/video/vid1/progress",
            json={"position_seconds": 300, "duration": 600},
        )

        # Read back directly from DB
        from backend.db.repositories import WatchHistoryRepo

        repo = WatchHistoryRepo(mem_db)
        entry = await repo.get("vid1")
        assert entry is not None
        assert entry.position_seconds == 300


# ---------------------------------------------------------------------------
# GET /api/video/{video_id}/meta
# ---------------------------------------------------------------------------


class TestGetVideoMeta:
    async def test_get_meta_returns_video_with_position(self, client, mem_db):
        await _seed_video(mem_db, "vid1")
        await _seed_watch(mem_db, "vid1", position=120, watched_at="2026-03-20T10:00:00+00:00")

        response = await client.get("/api/video/vid1/meta")
        assert response.status_code == 200
        data = response.json()
        assert data["id"] == "vid1"
        assert data["last_position_seconds"] == 120

    async def test_get_meta_returns_zero_for_unwatched(self, client, mem_db):
        await _seed_video(mem_db, "vid2")

        response = await client.get("/api/video/vid2/meta")
        assert response.status_code == 200
        assert response.json()["last_position_seconds"] == 0

    async def test_get_meta_returns_404_for_missing_video(self, client, mem_db):
        response = await client.get("/api/video/nonexistent/meta")
        assert response.status_code == 404
        assert response.json()["error"] == "Video not found"


# ---------------------------------------------------------------------------
# GET /api/feed/history
# ---------------------------------------------------------------------------


class TestFeedHistory:
    async def test_feed_history_returns_ordered_list(self, client, mem_db):
        """Videos should appear in descending watched_at order."""
        await _seed_video(mem_db, "vid_old")
        await _seed_video(mem_db, "vid_new")
        await _seed_watch(mem_db, "vid_old", position=10, watched_at="2026-03-19T08:00:00+00:00")
        await _seed_watch(mem_db, "vid_new", position=50, watched_at="2026-03-20T10:00:00+00:00")

        response = await client.get("/api/feed/history")
        assert response.status_code == 200
        data = response.json()
        assert data["feed_type"] == "history"
        assert len(data["videos"]) == 2
        # Most-recently-watched comes first
        assert data["videos"][0]["id"] == "vid_new"
        assert data["videos"][1]["id"] == "vid_old"

    async def test_feed_history_returns_empty(self, client, mem_db):
        response = await client.get("/api/feed/history")
        assert response.status_code == 200
        data = response.json()
        assert data["feed_type"] == "history"
        assert data["videos"] == []
        assert data["from_cache"] is False
        assert data["cached_at"] is None


# ---------------------------------------------------------------------------
# GET /api/video/{video_id}/download-status
# ---------------------------------------------------------------------------


class TestDownloadStatus:
    async def test_download_status_returns_none_for_unknown(self, client, mem_db):
        response = await client.get("/api/video/unknown/download-status")
        assert response.status_code == 200
        assert response.json() == {"status": "none", "percent": 0}

    async def test_download_status_returns_cached(self, client, mem_db):
        await _seed_video(mem_db, "vid_cached", cache_status="cached")

        response = await client.get("/api/video/vid_cached/download-status")
        assert response.status_code == 200
        assert response.json() == {"status": "cached", "percent": 100}
