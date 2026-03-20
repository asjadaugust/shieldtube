"""Tests for the video stream endpoint — updated for DownloadManager-backed streaming."""
import pytest
from unittest.mock import AsyncMock, MagicMock
from pathlib import Path

from backend.services.download_manager import DownloadState

pytestmark = pytest.mark.asyncio


def _make_state(tmp_path: Path, video_id: str, status: str, size: int) -> DownloadState:
    file_path = tmp_path / f"{video_id}.mp4"
    file_path.write_bytes(b"\x00" * size)
    return DownloadState(
        video_id=video_id,
        file_path=file_path,
        expected_size=size,
        process=None,
        status=status,
    )


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


async def test_stream_endpoint_returns_video(client, tmp_path):
    from backend.api.main import app

    state = _make_state(tmp_path, "dQw4w9WgXcQ", "cached", 2048)
    mock_dm = MagicMock()
    mock_dm.get_or_start_download = AsyncMock(return_value=state)
    app.state.download_manager = mock_dm

    response = await client.get("/api/video/dQw4w9WgXcQ/stream")

    assert response.status_code == 200
    assert response.headers["accept-ranges"] == "bytes"
    assert response.headers["content-type"] == "video/mp4"


async def test_stream_endpoint_range_request(client, tmp_path):
    from backend.api.main import app

    state = _make_state(tmp_path, "dQw4w9WgXcQ", "cached", 2048)
    mock_dm = MagicMock()
    mock_dm.get_or_start_download = AsyncMock(return_value=state)
    app.state.download_manager = mock_dm

    response = await client.get(
        "/api/video/dQw4w9WgXcQ/stream",
        headers={"Range": "bytes=0-1023"},
    )

    assert response.status_code == 206
    assert "content-range" in response.headers
    assert response.headers["content-range"] == "bytes 0-1023/2048"
    assert len(response.content) == 1024


async def test_stream_endpoint_range_request_suffix(client, tmp_path):
    from backend.api.main import app

    state = _make_state(tmp_path, "test", "cached", 2048)
    mock_dm = MagicMock()
    mock_dm.get_or_start_download = AsyncMock(return_value=state)
    app.state.download_manager = mock_dm

    response = await client.get(
        "/api/video/test/stream",
        headers={"Range": "bytes=1024-"},
    )

    assert response.status_code == 206
    assert len(response.content) == 1024
