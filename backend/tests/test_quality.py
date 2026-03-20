"""Tests for quality preset support across stream_resolver, download_manager, and endpoints."""
import pytest
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.stream_resolver import resolve_stream, QUALITY_FORMATS
from backend.services.download_manager import DownloadState

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

@pytest.fixture
def mock_yt_dlp_info():
    return {
        "requested_formats": [
            {
                "url": "https://rr1.example.com/video.webm",
                "ext": "webm",
                "vcodec": "vp9",
                "height": 1080,
                "filesize": 50_000_000,
            },
            {
                "url": "https://rr1.example.com/audio.webm",
                "ext": "webm",
                "acodec": "opus",
                "filesize": 5_000_000,
            },
        ],
        "duration": 212,
        "title": "Test Video",
        "id": "dQw4w9WgXcQ",
        "subtitles": {},
        "automatic_captions": {},
        "chapters": [],
    }


def _patch_ydl(info):
    """Return a context manager that patches yt_dlp.YoutubeDL with the given info dict."""
    patcher = patch("backend.services.stream_resolver.yt_dlp.YoutubeDL")

    def _start(mock_cls):
        instance = MagicMock()
        instance.extract_info.return_value = info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)
        return mock_cls

    return patcher, _start


# ---------------------------------------------------------------------------
# stream_resolver tests
# ---------------------------------------------------------------------------

def test_resolve_stream_with_1080p_quality(mock_yt_dlp_info):
    """Passing quality='1080p' should set the yt-dlp format string to the 1080p preset."""
    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_yt_dlp_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        resolve_stream("dQw4w9WgXcQ", quality="1080p")

        opts = mock_cls.call_args[0][0]
        assert opts["format"] == QUALITY_FORMATS["1080p"]
        assert "height<=1080" in opts["format"]


def test_resolve_stream_with_720p_quality(mock_yt_dlp_info):
    """Passing quality='720p' should use the 720p format preset."""
    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_yt_dlp_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        resolve_stream("dQw4w9WgXcQ", quality="720p")

        opts = mock_cls.call_args[0][0]
        assert opts["format"] == QUALITY_FORMATS["720p"]
        assert "height<=720" in opts["format"]


def test_resolve_stream_with_4k_hdr_quality(mock_yt_dlp_info):
    """Passing quality='4K_HDR' should include the VP9 HDR codec selector."""
    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_yt_dlp_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        resolve_stream("dQw4w9WgXcQ", quality="4K_HDR")

        opts = mock_cls.call_args[0][0]
        assert opts["format"] == QUALITY_FORMATS["4K_HDR"]
        assert "vp09.02" in opts["format"]


def test_resolve_stream_auto_uses_hdr_default(mock_yt_dlp_info):
    """quality='auto' with prefer_hdr=True should use the existing HDR fallback chain."""
    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_yt_dlp_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        resolve_stream("dQw4w9WgXcQ", prefer_hdr=True, quality="auto")

        opts = mock_cls.call_args[0][0]
        # Should use the HDR preference chain, not the 4K_HDR preset
        assert "vp09.02" in opts["format"]
        # HDR chain has multiple fallback parts separated by /
        assert opts["format"].count("/") >= 2


def test_resolve_stream_auto_non_hdr(mock_yt_dlp_info):
    """quality='auto' with prefer_hdr=False should use the non-HDR fallback."""
    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_yt_dlp_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        resolve_stream("dQw4w9WgXcQ", prefer_hdr=False, quality="auto")

        opts = mock_cls.call_args[0][0]
        assert "vp09.02" not in opts["format"]


def test_resolve_stream_unknown_quality_falls_back_to_hdr(mock_yt_dlp_info):
    """An unrecognised quality value should fall through to the HDR preference logic."""
    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_yt_dlp_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        resolve_stream("dQw4w9WgXcQ", prefer_hdr=True, quality="unknown_preset")

        opts = mock_cls.call_args[0][0]
        assert "vp09.02" in opts["format"]


# ---------------------------------------------------------------------------
# formats endpoint
# ---------------------------------------------------------------------------

async def test_formats_endpoint(client):
    """GET /api/video/{id}/formats should return the five quality options."""
    response = await client.get("/api/video/dQw4w9WgXcQ/formats")

    assert response.status_code == 200
    body = response.json()
    assert body["video_id"] == "dQw4w9WgXcQ"

    qualities = [f["quality"] for f in body["formats"]]
    assert "auto" in qualities
    assert "4K_HDR" in qualities
    assert "4K" in qualities
    assert "1080p" in qualities
    assert "720p" in qualities
    assert len(body["formats"]) == 5


async def test_formats_endpoint_labels(client):
    """Each format entry must include a non-empty label."""
    response = await client.get("/api/video/abc123/formats")
    assert response.status_code == 200
    for fmt in response.json()["formats"]:
        assert fmt.get("label"), f"Missing label for quality {fmt['quality']}"


# ---------------------------------------------------------------------------
# stream endpoint quality pass-through
# ---------------------------------------------------------------------------

def _make_state(tmp_path: Path, video_id: str, quality: str = "auto") -> DownloadState:
    filename = f"{video_id}_{quality}.mp4" if quality != "auto" else f"{video_id}.mp4"
    file_path = tmp_path / filename
    file_path.write_bytes(b"\x00" * 1024)
    return DownloadState(
        video_id=video_id,
        file_path=file_path,
        expected_size=1024,
        process=None,
        status="cached",
    )


@pytest.fixture(autouse=True)
def clean_app_state():
    """Restore app.state.download_manager after each test."""
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


async def test_stream_endpoint_accepts_quality_param(client, tmp_path):
    """Stream endpoint should pass quality param to download manager."""
    from backend.api.main import app

    state = _make_state(tmp_path, "dQw4w9WgXcQ", "1080p")
    mock_dm = MagicMock()
    mock_dm.get_or_start_download = AsyncMock(return_value=state)
    app.state.download_manager = mock_dm

    response = await client.get("/api/video/dQw4w9WgXcQ/stream?quality=1080p")

    assert response.status_code == 200
    mock_dm.get_or_start_download.assert_called_once_with("dQw4w9WgXcQ", quality="1080p")


async def test_stream_endpoint_default_quality_is_auto(client, tmp_path):
    """Stream endpoint without quality param should call download manager with quality='auto'."""
    from backend.api.main import app

    state = _make_state(tmp_path, "dQw4w9WgXcQ", "auto")
    mock_dm = MagicMock()
    mock_dm.get_or_start_download = AsyncMock(return_value=state)
    app.state.download_manager = mock_dm

    response = await client.get("/api/video/dQw4w9WgXcQ/stream")

    assert response.status_code == 200
    mock_dm.get_or_start_download.assert_called_once_with("dQw4w9WgXcQ", quality="auto")
