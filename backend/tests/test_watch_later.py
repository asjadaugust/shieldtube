"""Tests for Watch Later playlist sync — YouTubeAPI.get_watch_later and feed endpoint."""
from __future__ import annotations

import json
import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, MagicMock, patch

from backend.db.database import _run_migrations
from backend.services.auth_manager import AuthManager
from backend.services.youtube_api import YouTubeAPI

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


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
# Helpers
# ---------------------------------------------------------------------------


def _make_mock_auth() -> MagicMock:
    auth = MagicMock(spec=AuthManager)
    auth.get_auth_headers = AsyncMock(return_value={"Authorization": "Bearer test-token"})
    return auth


def _make_mock_http_response(
    status_code: int = 200, json_body: dict | None = None, headers: dict | None = None
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()
    return resp


def _make_mock_client(get_responses: list | None = None) -> AsyncMock:
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    if get_responses:
        mock_client.get = AsyncMock(side_effect=get_responses)
    return mock_client


def _make_playlist_item(video_id: str) -> dict:
    return {
        "kind": "youtube#playlistItem",
        "snippet": {
            "title": f"Video {video_id}",
            "channelTitle": "Test Channel",
        },
        "contentDetails": {
            "videoId": video_id,
        },
    }


def _make_video_detail_item(
    video_id: str,
    title: str = "Test Video",
    duration: str = "PT5M0S",
    view_count: str = "1000",
) -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "channelTitle": "Test Channel",
            "channelId": "UCtest",
            "publishedAt": "2024-01-01T00:00:00Z",
            "description": "A test video",
        },
        "contentDetails": {"duration": duration},
        "statistics": {"viewCount": view_count},
    }


SAMPLE_WATCH_LATER_VIDEOS = [
    {
        "id": "vid001",
        "title": "Watch Later Video 1",
        "channel_name": "Channel A",
        "channel_id": "UCaaaaa",
        "view_count": 100_000,
        "duration": 300,
        "published_at": "2024-06-01T00:00:00Z",
        "description": "",
    },
    {
        "id": "vid002",
        "title": "Watch Later Video 2",
        "channel_name": "Channel B",
        "channel_id": "UCbbbbb",
        "view_count": 200_000,
        "duration": 600,
        "published_at": "2024-06-02T00:00:00Z",
        "description": "",
    },
]


# ---------------------------------------------------------------------------
# YouTubeAPI.get_watch_later tests
# ---------------------------------------------------------------------------


async def test_get_watch_later_parses_playlist_items(db):
    """get_watch_later correctly parses playlistItems response and calls get_video_details."""
    auth = _make_mock_auth()
    api = YouTubeAPI(auth, db)

    playlist_resp = _make_mock_http_response(
        json_body={
            "etag": "wl-etag-v1",
            "items": [
                _make_playlist_item("vid001"),
                _make_playlist_item("vid002"),
            ],
        }
    )
    detail_resp = _make_mock_http_response(
        json_body={
            "etag": "detail-etag",
            "items": [
                _make_video_detail_item("vid001", title="Video One", duration="PT5M0S"),
                _make_video_detail_item("vid002", title="Video Two", duration="PT10M0S"),
            ],
        }
    )
    mock_client = _make_mock_client(get_responses=[playlist_resp, detail_resp])

    with patch("backend.services.youtube_api.httpx.AsyncClient", return_value=mock_client):
        videos, from_cache, cached_at = await api.get_watch_later(max_results=50)

    assert from_cache is False
    assert cached_at is None
    assert len(videos) == 2
    assert videos[0]["id"] == "vid001"
    assert videos[0]["title"] == "Video One"
    assert videos[0]["duration"] == 300   # PT5M0S
    assert videos[1]["id"] == "vid002"
    assert videos[1]["duration"] == 600   # PT10M0S

    # ETag should be stored in feed_cache
    row = await (
        await db.execute("SELECT etag, video_ids_json FROM feed_cache WHERE feed_type = 'watch_later'")
    ).fetchone()
    assert row is not None
    assert row["etag"] == "wl-etag-v1"
    stored_ids = json.loads(row["video_ids_json"])
    assert stored_ids == ["vid001", "vid002"]


async def test_get_watch_later_empty_playlist(db):
    """get_watch_later returns empty list when playlist has no items."""
    auth = _make_mock_auth()
    api = YouTubeAPI(auth, db)

    playlist_resp = _make_mock_http_response(
        json_body={"etag": "empty-etag", "items": []}
    )
    mock_client = _make_mock_client(get_responses=[playlist_resp])

    with patch("backend.services.youtube_api.httpx.AsyncClient", return_value=mock_client):
        videos, from_cache, cached_at = await api.get_watch_later()

    assert videos == []
    assert from_cache is False
    assert cached_at is None


async def test_get_watch_later_etag_cache_hit(db):
    """get_watch_later returns cached videos on 304 response."""
    # Pre-populate feed_cache
    fetched_at = "2026-03-20T12:00:00+00:00"
    video_ids = ["vid001", "vid002"]
    await db.execute(
        "INSERT INTO feed_cache (feed_type, video_ids_json, etag, fetched_at) VALUES (?, ?, ?, ?)",
        ("watch_later", json.dumps(video_ids), "wl-etag-v1", fetched_at),
    )
    # Pre-populate videos table
    for vid_id, title in [("vid001", "Video One"), ("vid002", "Video Two")]:
        await db.execute(
            """INSERT INTO videos (id, title, channel_name, channel_id, view_count, duration, published_at)
               VALUES (?, ?, ?, ?, ?, ?, ?)""",
            (vid_id, title, "Test Channel", "UCtest", 1000, 300, "2024-01-01T00:00:00Z"),
        )
    await db.commit()

    auth = _make_mock_auth()
    api = YouTubeAPI(auth, db)

    resp_304 = _make_mock_http_response(status_code=304)
    mock_client = _make_mock_client(get_responses=[resp_304])

    with patch("backend.services.youtube_api.httpx.AsyncClient", return_value=mock_client):
        videos, from_cache, returned_cached_at = await api.get_watch_later()

    assert from_cache is True
    assert returned_cached_at == fetched_at
    assert len(videos) == 2
    ids = {v["id"] for v in videos}
    assert ids == {"vid001", "vid002"}

    # Verify the If-None-Match header was sent (auth.get_auth_headers called, then header added)
    auth.get_auth_headers.assert_called_once()


async def test_get_watch_later_sends_etag_header(db):
    """get_watch_later sends If-None-Match header when a cached ETag exists."""
    fetched_at = "2026-03-20T12:00:00+00:00"
    await db.execute(
        "INSERT INTO feed_cache (feed_type, video_ids_json, etag, fetched_at) VALUES (?, ?, ?, ?)",
        ("watch_later", json.dumps([]), "existing-etag", fetched_at),
    )
    await db.commit()

    auth = _make_mock_auth()
    api = YouTubeAPI(auth, db)

    # Return 200 with empty items (not 304)
    playlist_resp = _make_mock_http_response(
        json_body={"etag": "new-etag", "items": []}
    )
    captured_headers: dict = {}

    async def _fake_get(url, headers=None, params=None):
        captured_headers.update(headers or {})
        return playlist_resp

    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)
    mock_client.get = _fake_get

    with patch("backend.services.youtube_api.httpx.AsyncClient", return_value=mock_client):
        await api.get_watch_later()

    assert captured_headers.get("If-None-Match") == "existing-etag"


# ---------------------------------------------------------------------------
# /api/feed/watch-later endpoint tests
# ---------------------------------------------------------------------------


async def test_watch_later_endpoint_returns_feed(client, mem_db):
    """GET /api/feed/watch-later returns correct feed shape."""
    with (
        patch(
            "backend.api.routers.feed.YouTubeAPI.get_watch_later",
            new_callable=AsyncMock,
            return_value=(SAMPLE_WATCH_LATER_VIDEOS, False, None),
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
        response = await client.get("/api/feed/watch-later")

    assert response.status_code == 200
    data = response.json()
    assert data["feed_type"] == "watch_later"
    assert isinstance(data["videos"], list)
    assert len(data["videos"]) == 2
    assert data["from_cache"] is False
    assert data["cached_at"] is None


async def test_watch_later_endpoint_video_fields(client, mem_db):
    """GET /api/feed/watch-later returns correct video fields."""
    with (
        patch(
            "backend.api.routers.feed.YouTubeAPI.get_watch_later",
            new_callable=AsyncMock,
            return_value=(SAMPLE_WATCH_LATER_VIDEOS, False, None),
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
        response = await client.get("/api/feed/watch-later")

    data = response.json()
    video = data["videos"][0]
    assert video["id"] == "vid001"
    assert video["title"] == "Watch Later Video 1"
    assert video["channel_name"] == "Channel A"
    assert video["view_count"] == 100_000
    assert video["duration"] == 300
    assert video["thumbnail_url"] == "/api/video/vid001/thumbnail?res=maxres"


async def test_watch_later_endpoint_empty(client, mem_db):
    """GET /api/feed/watch-later returns empty list when playlist has no items."""
    with (
        patch(
            "backend.api.routers.feed.YouTubeAPI.get_watch_later",
            new_callable=AsyncMock,
            return_value=([], False, None),
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
        response = await client.get("/api/feed/watch-later")

    assert response.status_code == 200
    data = response.json()
    assert data["feed_type"] == "watch_later"
    assert data["videos"] == []


async def test_watch_later_endpoint_from_cache(client, mem_db):
    """GET /api/feed/watch-later reflects cache metadata when served from cache."""
    cached_at = "2026-03-20T10:00:00+00:00"
    with (
        patch(
            "backend.api.routers.feed.YouTubeAPI.get_watch_later",
            new_callable=AsyncMock,
            return_value=(SAMPLE_WATCH_LATER_VIDEOS, True, cached_at),
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
        response = await client.get("/api/feed/watch-later")

    data = response.json()
    assert data["from_cache"] is True
    assert data["cached_at"] == cached_at
