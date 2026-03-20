"""Tests for the growing-file progressive stream endpoint (Phase 3a)."""
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport

from backend.services.download_manager import DownloadState

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


def _make_cached_state(tmp_path: Path, video_id: str, size: int) -> DownloadState:
    """Create a DownloadState with status='cached' backed by a real file."""
    file_path = tmp_path / f"{video_id}.mp4"
    file_path.write_bytes(b"\xAB" * size)
    return DownloadState(
        video_id=video_id,
        file_path=file_path,
        expected_size=size,
        process=None,
        status="cached",
    )


def _make_downloading_state(
    tmp_path: Path, video_id: str, expected_size: int, written_size: int
) -> DownloadState:
    """Create a DownloadState with status='downloading' and a partial file."""
    file_path = tmp_path / f"{video_id}.mp4"
    file_path.write_bytes(b"\xCD" * written_size)
    return DownloadState(
        video_id=video_id,
        file_path=file_path,
        expected_size=expected_size,
        process=None,
        status="downloading",
    )


def _make_missing_file_state(tmp_path: Path, video_id: str) -> DownloadState:
    """Create a DownloadState where the file does NOT exist on disk."""
    file_path = tmp_path / f"{video_id}.mp4"
    # Deliberately do NOT write the file
    return DownloadState(
        video_id=video_id,
        file_path=file_path,
        expected_size=1024,
        process=None,
        status="downloading",
    )


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture(autouse=True)
def clean_app_state():
    """Restore app.state.download_manager after each test to avoid test pollution."""
    from backend.api.main import app

    original = getattr(app.state, "download_manager", None)
    yield
    if original is None:
        try:
            del app.state.download_manager
        except AttributeError:
            pass
    else:
        app.state.download_manager = original


@pytest.fixture
async def app_client():
    """AsyncClient wired directly to the FastAPI app, bypassing lifespan."""
    from backend.api.main import app

    with (
        patch("backend.db.database.init_db", new_callable=AsyncMock),
        patch("backend.db.database.close_db", new_callable=AsyncMock),
        patch("backend.db.database.get_db", new_callable=AsyncMock),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac, app


# ---------------------------------------------------------------------------
# test_cached_file_serves_200
# ---------------------------------------------------------------------------


async def test_cached_file_serves_200(tmp_path):
    """Cached file → 200 with Accept-Ranges: bytes."""
    from backend.api.main import app

    state = _make_cached_state(tmp_path, "abc123", 4096)
    mock_dm = MagicMock()
    mock_dm.get_or_start_download = AsyncMock(return_value=state)
    app.state.download_manager = mock_dm

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get("/api/video/abc123/stream")

    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "video/mp4"
    assert len(response.content) == 4096


# ---------------------------------------------------------------------------
# test_cached_file_serves_206_range
# ---------------------------------------------------------------------------


async def test_cached_file_serves_206_range(tmp_path):
    """Cached file with Range header → 206 with correct Content-Range."""
    from backend.api.main import app

    state = _make_cached_state(tmp_path, "abc123", 4096)
    mock_dm = MagicMock()
    mock_dm.get_or_start_download = AsyncMock(return_value=state)
    app.state.download_manager = mock_dm

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/video/abc123/stream",
            headers={"Range": "bytes=0-1023"},
        )

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-1023/4096"
    assert response.headers["content-length"] == "1024"
    assert len(response.content) == 1024


# ---------------------------------------------------------------------------
# test_growing_file_serves_available_bytes
# ---------------------------------------------------------------------------


async def test_growing_file_serves_available_bytes(tmp_path):
    """Growing file with a range request within already-written bytes → 206 with correct content."""
    from backend.api.main import app

    # 4096 total expected, 2048 already written
    state = _make_downloading_state(tmp_path, "vid456", expected_size=4096, written_size=2048)
    # Request bytes=0-2047 which are all available immediately
    # Mark as cached with correct size so the iterator exits cleanly
    state.status = "cached"
    state.expected_size = 2048

    mock_dm = MagicMock()
    mock_dm.get_or_start_download = AsyncMock(return_value=state)
    app.state.download_manager = mock_dm

    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as ac:
        response = await ac.get(
            "/api/video/vid456/stream",
            headers={"Range": "bytes=0-2047"},
        )

    assert response.status_code == 206
    assert response.headers["content-range"] == "bytes 0-2047/2048"
    assert len(response.content) == 2048
    # All bytes should be 0xCD as written
    assert response.content == b"\xCD" * 2048


# ---------------------------------------------------------------------------
# test_stream_returns_503_when_file_missing
# ---------------------------------------------------------------------------


async def test_stream_returns_503_when_file_missing(tmp_path):
    """When status='downloading' but file never appears → 503 with Retry-After."""
    from backend.api.main import app

    state = _make_missing_file_state(tmp_path, "missing99")
    mock_dm = MagicMock()
    mock_dm.get_or_start_download = AsyncMock(return_value=state)
    app.state.download_manager = mock_dm

    # Patch asyncio.sleep in the video router so the 5-second wait is instant
    with patch("backend.api.routers.video.asyncio.sleep", new_callable=AsyncMock):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/video/missing99/stream")

    assert response.status_code == 503
    assert response.headers.get("retry-after") == "5"
