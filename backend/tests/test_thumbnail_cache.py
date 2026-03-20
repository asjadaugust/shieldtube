"""Tests for ThumbnailCache service and the /video/{id}/thumbnail endpoint."""
import asyncio
import hashlib
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from httpx import AsyncClient, ASGITransport, Response

from backend.db.database import _run_migrations
from backend.services.thumbnail_cache import ThumbnailCache

pytestmark = pytest.mark.asyncio

FAKE_JPEG = b"\xff\xd8\xff\xe0" + b"\x00" * 100  # minimal fake JPEG bytes


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_httpx_response(status_code: int, content: bytes = FAKE_JPEG) -> Response:
    """Build a minimal httpx.Response for mocking."""
    return Response(status_code=status_code, content=content)


def _mock_client(responses):
    """Return a patched httpx.AsyncClient context manager with side_effect responses."""
    mock_client = AsyncMock()
    if isinstance(responses, list):
        mock_client.get = AsyncMock(side_effect=responses)
    else:
        mock_client.get = AsyncMock(return_value=responses)

    mock_client_cls = MagicMock()
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_client_cls, mock_client


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
def cache(db):
    return ThumbnailCache(db)


# ---------------------------------------------------------------------------
# ThumbnailCache.cache_thumbnails — basic download & storage
# ---------------------------------------------------------------------------


async def test_cache_thumbnails_downloads_and_writes_to_disk(cache, db, tmp_path):
    """Happy path: maxres thumbnail downloaded and written to disk."""
    videos = [{"id": "abc123"}]

    mock_client_cls, mock_client = _mock_client(_make_httpx_response(200))

    with patch("backend.services.thumbnail_cache.settings") as mock_settings:
        mock_settings.cache_dir = str(tmp_path)
        mock_settings.thumbnail_concurrency = 5

        with patch("backend.services.thumbnail_cache.httpx.AsyncClient", mock_client_cls):
            await cache.cache_thumbnails(videos)

    thumb_path = tmp_path / "thumbnails" / "abc123_maxres.jpg"
    assert thumb_path.exists(), "Thumbnail file should be written to disk"
    assert thumb_path.read_bytes() == FAKE_JPEG

    async with db.execute(
        "SELECT video_id, resolution, content_hash FROM thumbnails WHERE video_id = 'abc123'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row["video_id"] == "abc123"
    assert row["resolution"] == "maxres"
    expected_hash = hashlib.md5(FAKE_JPEG).hexdigest()
    assert row["content_hash"] == expected_hash


async def test_cache_thumbnails_updates_videos_table(cache, db, tmp_path):
    """After caching, videos.thumbnail_path should be updated."""
    # Insert a video row first
    await db.execute(
        "INSERT INTO videos (id, title, channel_name, channel_id) VALUES (?, ?, ?, ?)",
        ("vid1", "Test Video", "Channel", "ch1"),
    )
    await db.commit()

    videos = [{"id": "vid1"}]
    mock_client_cls, mock_client = _mock_client(_make_httpx_response(200))

    with patch("backend.services.thumbnail_cache.settings") as mock_settings:
        mock_settings.cache_dir = str(tmp_path)
        mock_settings.thumbnail_concurrency = 5

        with patch("backend.services.thumbnail_cache.httpx.AsyncClient", mock_client_cls):
            await cache.cache_thumbnails(videos)

    async with db.execute(
        "SELECT thumbnail_path FROM videos WHERE id = 'vid1'"
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row["thumbnail_path"] is not None
    assert "vid1_maxres.jpg" in row["thumbnail_path"]


# ---------------------------------------------------------------------------
# ThumbnailCache.cache_thumbnails — idempotency
# ---------------------------------------------------------------------------


async def test_cache_thumbnails_idempotent_skips_already_cached(cache, db, tmp_path):
    """Second call with same video IDs must not call httpx.get again."""
    # Pre-insert into thumbnails table to simulate already-cached state
    local_path = str(tmp_path / "thumbnails" / "vid2_maxres.jpg")
    await db.execute(
        "INSERT INTO thumbnails (video_id, resolution, local_path, fetched_at, content_hash) "
        "VALUES (?, ?, ?, datetime('now'), ?)",
        ("vid2", "maxres", local_path, "abc"),
    )
    await db.commit()

    videos = [{"id": "vid2"}]
    mock_client_cls, mock_client = _mock_client(_make_httpx_response(200))

    with patch("backend.services.thumbnail_cache.settings") as mock_settings:
        mock_settings.cache_dir = str(tmp_path)
        mock_settings.thumbnail_concurrency = 5

        with patch("backend.services.thumbnail_cache.httpx.AsyncClient", mock_client_cls):
            await cache.cache_thumbnails(videos)

    # httpx.AsyncClient should not even have been entered (no uncached videos)
    mock_client.get.assert_not_called()


async def test_cache_thumbnails_only_downloads_uncached(cache, db, tmp_path):
    """Mix of cached and uncached: only uncached ones trigger a download."""
    local_path = str(tmp_path / "thumbnails" / "cached_maxres.jpg")
    await db.execute(
        "INSERT INTO thumbnails (video_id, resolution, local_path, fetched_at, content_hash) "
        "VALUES (?, ?, ?, datetime('now'), ?)",
        ("cached", "maxres", local_path, "abc"),
    )
    await db.commit()

    videos = [{"id": "cached"}, {"id": "fresh"}]
    mock_client_cls, mock_client = _mock_client(_make_httpx_response(200))

    with patch("backend.services.thumbnail_cache.settings") as mock_settings:
        mock_settings.cache_dir = str(tmp_path)
        mock_settings.thumbnail_concurrency = 5

        with patch("backend.services.thumbnail_cache.httpx.AsyncClient", mock_client_cls):
            await cache.cache_thumbnails(videos)

    # Only "fresh" video should have triggered a download (one get call)
    assert mock_client.get.call_count == 1
    call_url = mock_client.get.call_args[0][0]
    assert "fresh" in call_url


# ---------------------------------------------------------------------------
# ThumbnailCache.cache_thumbnails — maxres 404 fallback
# ---------------------------------------------------------------------------


async def test_cache_thumbnails_falls_back_to_hqdefault_on_404(cache, db, tmp_path):
    """If maxresdefault.jpg returns 404, hqdefault.jpg should be fetched."""
    videos = [{"id": "nohires"}]

    response_404 = _make_httpx_response(404, b"")
    response_hq = _make_httpx_response(200, FAKE_JPEG)
    mock_client_cls, mock_client = _mock_client([response_404, response_hq])

    with patch("backend.services.thumbnail_cache.settings") as mock_settings:
        mock_settings.cache_dir = str(tmp_path)
        mock_settings.thumbnail_concurrency = 5

        with patch("backend.services.thumbnail_cache.httpx.AsyncClient", mock_client_cls):
            await cache.cache_thumbnails(videos)

    assert mock_client.get.call_count == 2
    first_url = mock_client.get.call_args_list[0][0][0]
    second_url = mock_client.get.call_args_list[1][0][0]
    assert "maxresdefault.jpg" in first_url
    assert "hqdefault.jpg" in second_url

    # File should still be written
    thumb_path = tmp_path / "thumbnails" / "nohires_maxres.jpg"
    assert thumb_path.exists()


# ---------------------------------------------------------------------------
# ThumbnailCache.cache_thumbnails — concurrency semaphore
# ---------------------------------------------------------------------------


async def test_cache_thumbnails_respects_concurrency_semaphore(tmp_path):
    """Semaphore limits parallel downloads to thumbnail_concurrency."""
    concurrent_count = 0
    max_concurrent = 0

    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    cache = ThumbnailCache(conn)

    semaphore_limit = 3
    videos = [{"id": f"vid{i}"} for i in range(10)]

    async def slow_get(url):
        nonlocal concurrent_count, max_concurrent
        concurrent_count += 1
        max_concurrent = max(max_concurrent, concurrent_count)
        await asyncio.sleep(0.01)
        concurrent_count -= 1
        return _make_httpx_response(200)

    mock_client_cls, mock_client = _mock_client(_make_httpx_response(200))
    mock_client.get = slow_get  # override with async function that tracks concurrency

    with patch("backend.services.thumbnail_cache.settings") as mock_settings:
        mock_settings.cache_dir = str(tmp_path)
        mock_settings.thumbnail_concurrency = semaphore_limit

        with patch("backend.services.thumbnail_cache.httpx.AsyncClient", mock_client_cls):
            await cache.cache_thumbnails(videos)

    assert max_concurrent <= semaphore_limit, (
        f"Max concurrent downloads {max_concurrent} exceeded semaphore limit {semaphore_limit}"
    )
    await conn.close()


# ---------------------------------------------------------------------------
# ThumbnailCache.get_thumbnail_path
# ---------------------------------------------------------------------------


async def test_get_thumbnail_path_returns_none_for_uncached(cache):
    result = await cache.get_thumbnail_path("nonexistent")
    assert result is None


async def test_get_thumbnail_path_returns_none_when_file_missing_from_disk(cache, db, tmp_path):
    """DB row exists but file was deleted — should return None."""
    local_path = str(tmp_path / "thumbnails" / "gone_maxres.jpg")
    # Insert row but don't create file
    await db.execute(
        "INSERT INTO thumbnails (video_id, resolution, local_path, fetched_at, content_hash) "
        "VALUES (?, ?, ?, datetime('now'), ?)",
        ("gone", "maxres", local_path, "abc"),
    )
    await db.commit()

    result = await cache.get_thumbnail_path("gone")
    assert result is None


async def test_get_thumbnail_path_returns_path_for_cached_video(cache, db, tmp_path):
    """DB row exists and file is on disk — should return path."""
    thumb_dir = tmp_path / "thumbnails"
    thumb_dir.mkdir(parents=True)
    local_path = str(thumb_dir / "existing_maxres.jpg")
    Path(local_path).write_bytes(FAKE_JPEG)

    await db.execute(
        "INSERT INTO thumbnails (video_id, resolution, local_path, fetched_at, content_hash) "
        "VALUES (?, ?, ?, datetime('now'), ?)",
        ("existing", "maxres", local_path, "abc"),
    )
    await db.commit()

    result = await cache.get_thumbnail_path("existing")
    assert result == local_path


async def test_get_thumbnail_path_respects_resolution_param(cache, db, tmp_path):
    """Query for 'high' resolution when only 'maxres' is stored returns None."""
    thumb_dir = tmp_path / "thumbnails"
    thumb_dir.mkdir(parents=True)
    local_path = str(thumb_dir / "vid_maxres.jpg")
    Path(local_path).write_bytes(FAKE_JPEG)

    await db.execute(
        "INSERT INTO thumbnails (video_id, resolution, local_path, fetched_at, content_hash) "
        "VALUES (?, ?, ?, datetime('now'), ?)",
        ("vid", "maxres", local_path, "abc"),
    )
    await db.commit()

    # Asking for 'high' when only 'maxres' stored — should be None
    result = await cache.get_thumbnail_path("vid", resolution="high")
    assert result is None

    # Asking for 'maxres' should work
    result = await cache.get_thumbnail_path("vid", resolution="maxres")
    assert result == local_path


# ---------------------------------------------------------------------------
# ThumbnailCache.get_youtube_thumbnail_url (static method)
# ---------------------------------------------------------------------------


def test_get_youtube_thumbnail_url_maxres():
    url = ThumbnailCache.get_youtube_thumbnail_url("abc123")
    assert url == "https://i.ytimg.com/vi/abc123/maxresdefault.jpg"


def test_get_youtube_thumbnail_url_high():
    url = ThumbnailCache.get_youtube_thumbnail_url("abc123", resolution="high")
    assert url == "https://i.ytimg.com/vi/abc123/hqdefault.jpg"


# ---------------------------------------------------------------------------
# Thumbnail endpoint tests
# ---------------------------------------------------------------------------


async def test_thumbnail_endpoint_returns_file_response_when_cached(tmp_path):
    """GET /api/video/{id}/thumbnail returns 200 FileResponse when thumbnail is cached."""
    from backend.api.main import app

    # Create the thumbnail file
    thumb_dir = tmp_path / "thumbnails"
    thumb_dir.mkdir(parents=True)
    local_path = str(thumb_dir / "cached_vid_maxres.jpg")
    Path(local_path).write_bytes(FAKE_JPEG)

    async def mock_get_db():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await _run_migrations(conn)
        return conn

    async def mock_get_thumbnail_path(self, video_id, resolution="maxres"):
        return local_path

    with patch("backend.api.routers.video.get_db", side_effect=mock_get_db):
        with patch.object(ThumbnailCache, "get_thumbnail_path", mock_get_thumbnail_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get("/api/video/cached_vid/thumbnail")

    assert response.status_code == 200
    assert "image/jpeg" in response.headers["content-type"]


async def test_thumbnail_endpoint_returns_redirect_when_not_cached(tmp_path):
    """GET /api/video/{id}/thumbnail returns 302 redirect when not cached."""
    from backend.api.main import app

    async def mock_get_db():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await _run_migrations(conn)
        return conn

    async def mock_get_thumbnail_path(self, video_id, resolution="maxres"):
        return None

    with patch("backend.api.routers.video.get_db", side_effect=mock_get_db):
        with patch.object(ThumbnailCache, "get_thumbnail_path", mock_get_thumbnail_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as ac:
                response = await ac.get("/api/video/uncached_vid/thumbnail")

    assert response.status_code == 302
    location = response.headers["location"]
    assert "uncached_vid" in location
    assert "ytimg.com" in location


async def test_thumbnail_endpoint_redirect_url_is_correct():
    """302 redirect points to YouTube CDN with correct video_id and resolution."""
    from backend.api.main import app

    async def mock_get_db():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await _run_migrations(conn)
        return conn

    async def mock_get_thumbnail_path(self, video_id, resolution="maxres"):
        return None

    with patch("backend.api.routers.video.get_db", side_effect=mock_get_db):
        with patch.object(ThumbnailCache, "get_thumbnail_path", mock_get_thumbnail_path):
            transport = ASGITransport(app=app)
            async with AsyncClient(
                transport=transport, base_url="http://test", follow_redirects=False
            ) as ac:
                response = await ac.get("/api/video/dQw4w9WgXcQ/thumbnail?res=high")

    assert response.status_code == 302
    location = response.headers["location"]
    assert "dQw4w9WgXcQ" in location
    assert "hqdefault.jpg" in location
