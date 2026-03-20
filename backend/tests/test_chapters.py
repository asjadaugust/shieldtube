"""Tests for Phase 4b: Chapter Markers."""
from __future__ import annotations

import json
import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport
from unittest.mock import patch, MagicMock, AsyncMock

from backend.db.database import _run_migrations
from backend.db.models import Video
from backend.services.stream_resolver import resolve_stream

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
        patch("backend.db.database.get_db", new=_fake_get_db),
        patch("backend.api.routers.watch.get_db", new=_fake_get_db),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


async def _seed_video(db, video_id: str, chapters_json: str | None = None) -> None:
    """Insert a minimal video row with optional chapters_json into the DB."""
    from backend.db.repositories import VideoRepo

    repo = VideoRepo(db)
    video = Video(
        id=video_id,
        title=f"Title {video_id}",
        channel_name="Test Channel",
        channel_id="UC_test",
        duration=600,
        cache_status="none",
    )
    await repo.upsert(video)

    if chapters_json is not None:
        await db.execute(
            "UPDATE videos SET chapters_json = ? WHERE id = ?",
            (chapters_json, video_id),
        )
        await db.commit()


# ---------------------------------------------------------------------------
# resolve_stream returns chapters
# ---------------------------------------------------------------------------


def test_resolve_stream_returns_chapters():
    """resolve_stream() should include chapters from yt-dlp info."""
    sample_chapters = [
        {"title": "Intro", "start_time": 0.0, "end_time": 30.0},
        {"title": "Main Content", "start_time": 30.0, "end_time": 300.0},
        {"title": "Outro", "start_time": 300.0, "end_time": 360.0},
    ]
    mock_info = {
        "requested_formats": [
            {
                "url": "https://example.com/video.webm",
                "ext": "webm",
                "vcodec": "vp9",
                "height": 1080,
            },
            {
                "url": "https://example.com/audio.webm",
                "ext": "webm",
                "acodec": "opus",
            },
        ],
        "duration": 360,
        "title": "Test Video With Chapters",
        "id": "test123",
        "chapters": sample_chapters,
    }

    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = resolve_stream("test123")

    assert "chapters" in result
    assert result["chapters"] == sample_chapters
    assert len(result["chapters"]) == 3
    assert result["chapters"][0]["title"] == "Intro"
    assert result["chapters"][1]["start_time"] == 30.0
    assert result["chapters"][2]["end_time"] == 360.0


def test_resolve_stream_returns_empty_chapters_when_none():
    """When yt-dlp info has no chapters field, resolve_stream returns empty list."""
    mock_info = {
        "requested_formats": [
            {
                "url": "https://example.com/video.webm",
                "ext": "webm",
                "vcodec": "vp9",
                "height": 1080,
            },
            {
                "url": "https://example.com/audio.webm",
                "ext": "webm",
                "acodec": "opus",
            },
        ],
        "duration": 180,
        "title": "Video Without Chapters",
        "id": "nochap",
        # No "chapters" key
    }

    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = resolve_stream("nochap")

    assert "chapters" in result
    assert result["chapters"] == []


def test_resolve_stream_returns_empty_chapters_when_null():
    """When yt-dlp info has chapters=None, resolve_stream returns empty list."""
    mock_info = {
        "requested_formats": [
            {
                "url": "https://example.com/video.webm",
                "ext": "webm",
                "vcodec": "vp9",
                "height": 1080,
            },
            {
                "url": "https://example.com/audio.webm",
                "ext": "webm",
                "acodec": "opus",
            },
        ],
        "duration": 180,
        "title": "Video With Null Chapters",
        "id": "nullchap",
        "chapters": None,
    }

    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = resolve_stream("nullchap")

    assert "chapters" in result
    assert result["chapters"] == []


# ---------------------------------------------------------------------------
# GET /api/video/{video_id}/meta includes chapters
# ---------------------------------------------------------------------------


class TestMetaReturnsChapters:
    async def test_meta_returns_chapters(self, client, mem_db):
        """GET /meta should include parsed chapters list from DB."""
        chapters = [
            {"title": "Intro", "start_time": 0.0, "end_time": 60.0},
            {"title": "Main", "start_time": 60.0, "end_time": 540.0},
            {"title": "Outro", "start_time": 540.0, "end_time": 600.0},
        ]
        await _seed_video(mem_db, "vid_chapters", chapters_json=json.dumps(chapters))

        response = await client.get("/api/video/vid_chapters/meta")
        assert response.status_code == 200
        data = response.json()
        assert "chapters" in data
        assert len(data["chapters"]) == 3
        assert data["chapters"][0]["title"] == "Intro"
        assert data["chapters"][0]["start_time"] == 0.0
        assert data["chapters"][0]["end_time"] == 60.0
        assert data["chapters"][1]["title"] == "Main"
        assert data["chapters"][2]["title"] == "Outro"

    async def test_meta_returns_empty_chapters_when_none(self, client, mem_db):
        """GET /meta should return empty list when video has no chapters_json."""
        await _seed_video(mem_db, "vid_nochap", chapters_json=None)

        response = await client.get("/api/video/vid_nochap/meta")
        assert response.status_code == 200
        data = response.json()
        assert "chapters" in data
        assert data["chapters"] == []

    async def test_meta_returns_empty_chapters_when_empty_array(self, client, mem_db):
        """GET /meta should return empty list when chapters_json is '[]'."""
        await _seed_video(mem_db, "vid_emptychap", chapters_json="[]")

        response = await client.get("/api/video/vid_emptychap/meta")
        assert response.status_code == 200
        data = response.json()
        assert "chapters" in data
        assert data["chapters"] == []
