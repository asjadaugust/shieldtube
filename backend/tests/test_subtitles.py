"""Tests for subtitle extraction, caching, and API endpoints."""
import json
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest
from httpx import AsyncClient, ASGITransport, Request, Response

from backend.services.stream_resolver import resolve_stream

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------

MOCK_YT_DLP_INFO_WITH_SUBTITLES = {
    "requested_formats": [
        {
            "url": "https://rr1.example.com/video.webm",
            "ext": "webm",
            "vcodec": "vp9",
            "height": 2160,
        },
        {
            "url": "https://rr1.example.com/audio.webm",
            "ext": "webm",
            "acodec": "opus",
        },
    ],
    "duration": 212,
    "title": "Test Video",
    "id": "dQw4w9WgXcQ",
    "subtitles": {
        "en": [
            {"url": "https://sub.example.com/en.srv3", "ext": "srv3", "name": "English"},
            {"url": "https://sub.example.com/en.vtt", "ext": "vtt", "name": "English"},
        ],
        "fr": [
            {"url": "https://sub.example.com/fr.vtt", "ext": "vtt", "name": "French"},
        ],
    },
    "automatic_captions": {
        "de": [
            {"url": "https://sub.example.com/de.vtt", "ext": "vtt", "name": "German"},
        ],
        # "en" already in subtitles — should not overwrite with auto
        "en": [
            {"url": "https://sub.example.com/en_auto.vtt", "ext": "vtt", "name": "English"},
        ],
    },
}

MOCK_STREAM_INFO = {
    "video_url": "https://rr1.example.com/video.webm",
    "audio_url": "https://rr1.example.com/audio.webm",
    "duration": 212,
    "title": "Test Video",
    "filesize": 100_000_000,
    "chapters": [],
    "subtitles": {
        "en": {"url": "https://sub.example.com/en.vtt", "ext": "vtt", "name": "English"},
        "fr": {"url": "https://sub.example.com/fr.vtt", "ext": "vtt", "name": "French"},
        "de": {
            "url": "https://sub.example.com/de.vtt",
            "ext": "vtt",
            "name": "German (auto)",
            "auto": True,
        },
    },
}


def _make_ydl_mock(info: dict):
    """Return a patched yt_dlp.YoutubeDL context manager returning *info*."""
    instance = MagicMock()
    instance.extract_info.return_value = info
    mock_cls = MagicMock()
    mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
    mock_cls.return_value.__exit__ = MagicMock(return_value=False)
    return mock_cls


# ---------------------------------------------------------------------------
# test_resolve_stream_returns_subtitles
# ---------------------------------------------------------------------------


def test_resolve_stream_returns_subtitles():
    """resolve_stream() includes subtitles dict, preferring vtt and manual over auto."""
    mock_cls = _make_ydl_mock(MOCK_YT_DLP_INFO_WITH_SUBTITLES)

    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL", mock_cls):
        result = resolve_stream("dQw4w9WgXcQ")

    assert "subtitles" in result
    subs = result["subtitles"]

    # English: vtt preferred over srv3
    assert "en" in subs
    assert subs["en"]["ext"] == "vtt"
    assert subs["en"]["url"] == "https://sub.example.com/en.vtt"
    assert subs["en"]["name"] == "English"
    assert "auto" not in subs["en"]  # manual subtitle — no auto flag

    # French: only vtt available
    assert "fr" in subs
    assert subs["fr"]["url"] == "https://sub.example.com/fr.vtt"

    # German: comes from automatic_captions (en already taken by manual)
    assert "de" in subs
    assert subs["de"]["auto"] is True
    assert "(auto)" in subs["de"]["name"]

    # English auto-caption must NOT overwrite manual English
    assert subs["en"]["url"] == "https://sub.example.com/en.vtt"


def test_resolve_stream_no_subtitles():
    """resolve_stream() returns empty subtitles dict when none are available."""
    info = {
        "url": "https://rr1.example.com/best.mp4",
        "duration": 60,
        "title": "No Subs Video",
        "id": "nosubs",
    }
    mock_cls = _make_ydl_mock(info)

    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL", mock_cls):
        result = resolve_stream("nosubs")

    assert result["subtitles"] == {}


# ---------------------------------------------------------------------------
# test_list_subtitles_endpoint
# ---------------------------------------------------------------------------


async def test_list_subtitles_endpoint():
    """GET /api/video/{id}/subtitles returns correct JSON with track list."""
    from backend.api.main import app

    # resolve_stream is a sync function called via asyncio.to_thread; patch at source
    with patch(
        "backend.services.stream_resolver.resolve_stream",
        return_value=MOCK_STREAM_INFO,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/video/dQw4w9WgXcQ/subtitles")

    assert response.status_code == 200
    body = response.json()
    assert body["video_id"] == "dQw4w9WgXcQ"
    assert "tracks" in body
    langs = {t["lang"] for t in body["tracks"]}
    assert "en" in langs
    assert "fr" in langs
    # de comes from automatic_captions
    assert "de" in langs
    # Auto tracks should have auto=True
    de_track = next(t for t in body["tracks"] if t["lang"] == "de")
    assert de_track["auto"] is True
    # Manual tracks should have auto=False
    en_track = next(t for t in body["tracks"] if t["lang"] == "en")
    assert en_track["auto"] is False


async def test_list_subtitles_endpoint_empty_on_error():
    """GET /api/video/{id}/subtitles returns empty track list when resolve_stream fails."""
    from backend.api.main import app

    with patch(
        "backend.services.stream_resolver.resolve_stream",
        side_effect=Exception("yt-dlp unavailable"),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/video/fail_video/subtitles")

    assert response.status_code == 200
    body = response.json()
    assert body["tracks"] == []


# ---------------------------------------------------------------------------
# test_get_subtitle_serves_vtt
# ---------------------------------------------------------------------------


async def test_get_subtitle_serves_vtt(tmp_path):
    """GET /api/video/{id}/subtitles/{lang} serves cached WebVTT content."""
    from backend.api.main import app

    vtt_content = b"WEBVTT\n\n00:00:01.000 --> 00:00:04.000\nHello, world!\n"

    # Pre-create the cached subtitle file so get_or_download_subtitle returns it
    subtitle_dir = tmp_path / "subtitles"
    subtitle_dir.mkdir()
    cached_file = subtitle_dir / "dQw4w9WgXcQ_en.vtt"
    cached_file.write_bytes(vtt_content)

    with patch(
        "backend.services.stream_resolver.resolve_stream",
        return_value=MOCK_STREAM_INFO,
    ):
        with patch(
            "backend.api.routers.video.get_or_download_subtitle",
            new=AsyncMock(return_value=cached_file),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get("/api/video/dQw4w9WgXcQ/subtitles/en")

    assert response.status_code == 200
    assert "text/vtt" in response.headers["content-type"]
    assert response.content == vtt_content


# ---------------------------------------------------------------------------
# test_get_subtitle_404_unknown_lang
# ---------------------------------------------------------------------------


async def test_get_subtitle_404_unknown_lang():
    """GET /api/video/{id}/subtitles/{lang} returns 404 for unknown language."""
    from backend.api.main import app

    with patch(
        "backend.services.stream_resolver.resolve_stream",
        return_value=MOCK_STREAM_INFO,
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            response = await ac.get("/api/video/dQw4w9WgXcQ/subtitles/xx")

    assert response.status_code == 404
    body = response.json()
    assert "error" in body


async def test_get_subtitle_503_download_failure():
    """GET /api/video/{id}/subtitles/{lang} returns 503 when download fails."""
    from backend.api.main import app

    with patch(
        "backend.services.stream_resolver.resolve_stream",
        return_value=MOCK_STREAM_INFO,
    ):
        with patch(
            "backend.api.routers.video.get_or_download_subtitle",
            new=AsyncMock(return_value=None),
        ):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get("/api/video/dQw4w9WgXcQ/subtitles/en")

    assert response.status_code == 503
    body = response.json()
    assert "error" in body


# ---------------------------------------------------------------------------
# test_subtitle_cache — get_or_download_subtitle
# ---------------------------------------------------------------------------


async def test_subtitle_cache_returns_existing_file(tmp_path):
    """get_or_download_subtitle() returns path immediately if file already cached."""
    from backend.services.subtitle_cache import get_or_download_subtitle

    sub_dir = tmp_path / "subtitles"
    sub_dir.mkdir()
    cached = sub_dir / "vid123_en.vtt"
    cached.write_bytes(b"WEBVTT\n")

    with patch("backend.services.subtitle_cache.settings") as mock_settings:
        mock_settings.cache_dir = str(tmp_path)
        result = await get_or_download_subtitle("vid123", "en", "https://ignored.example.com")

    assert result == cached


async def test_subtitle_cache_downloads_when_missing(tmp_path):
    """get_or_download_subtitle() downloads and writes file when not cached."""
    from backend.services.subtitle_cache import get_or_download_subtitle

    vtt_bytes = b"WEBVTT\n\n00:00:01.000 --> 00:00:02.000\nTest\n"
    dummy_request = Request("GET", "https://sub.example.com/en.vtt")

    mock_resp = Response(200, content=vtt_bytes, request=dummy_request)
    mock_client = AsyncMock()
    mock_client.get = AsyncMock(return_value=mock_resp)

    mock_client_cls = MagicMock()
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.services.subtitle_cache.settings") as mock_settings:
        mock_settings.cache_dir = str(tmp_path)
        with patch("backend.services.subtitle_cache.httpx.AsyncClient", mock_client_cls):
            result = await get_or_download_subtitle(
                "vid123", "en", "https://sub.example.com/en.vtt"
            )

    assert result is not None
    assert result.exists()
    assert result.read_bytes() == vtt_bytes


async def test_subtitle_cache_returns_none_on_http_error(tmp_path):
    """get_or_download_subtitle() returns None when download fails."""
    from backend.services.subtitle_cache import get_or_download_subtitle

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=Exception("network error"))

    mock_client_cls = MagicMock()
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.services.subtitle_cache.settings") as mock_settings:
        mock_settings.cache_dir = str(tmp_path)
        with patch("backend.services.subtitle_cache.httpx.AsyncClient", mock_client_cls):
            result = await get_or_download_subtitle(
                "vid123", "en", "https://sub.example.com/en.vtt"
            )

    assert result is None
