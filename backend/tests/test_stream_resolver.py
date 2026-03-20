import pytest
from unittest.mock import patch, MagicMock

from backend.services.stream_resolver import resolve_stream


@pytest.fixture
def mock_yt_dlp_info():
    return {
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
    }


def test_resolve_stream_returns_video_and_audio_urls(mock_yt_dlp_info):
    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_yt_dlp_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        result = resolve_stream("dQw4w9WgXcQ")

        assert result["video_url"] == "https://rr1.example.com/video.webm"
        assert result["audio_url"] == "https://rr1.example.com/audio.webm"
        assert result["duration"] == 212
        assert result["title"] == "Test Video"


def test_resolve_stream_prefers_hdr_format(mock_yt_dlp_info):
    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_yt_dlp_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        resolve_stream("dQw4w9WgXcQ", prefer_hdr=True)

        opts = mock_cls.call_args[0][0]
        assert "vp09.02" in opts["format"]


def test_resolve_stream_non_hdr_fallback(mock_yt_dlp_info):
    with patch("backend.services.stream_resolver.yt_dlp.YoutubeDL") as mock_cls:
        instance = MagicMock()
        instance.extract_info.return_value = mock_yt_dlp_info
        mock_cls.return_value.__enter__ = MagicMock(return_value=instance)
        mock_cls.return_value.__exit__ = MagicMock(return_value=False)

        resolve_stream("dQw4w9WgXcQ", prefer_hdr=False)

        opts = mock_cls.call_args[0][0]
        assert "vp09.02" not in opts["format"]
