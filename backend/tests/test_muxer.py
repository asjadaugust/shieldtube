import pytest
from unittest.mock import patch, MagicMock
from pathlib import Path

from backend.services.muxer import mux_streams


def test_mux_streams_calls_ffmpeg_with_stream_copy(tmp_path):
    output = tmp_path / "output.mp4"

    with patch("backend.services.muxer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = mux_streams(
            video_url="https://example.com/video.webm",
            audio_url="https://example.com/audio.webm",
            output_path=output,
        )

        args = mock_run.call_args[0][0]
        assert "ffmpeg" in args[0]
        idx_cv = args.index("-c:v")
        assert args[idx_cv + 1] == "copy"
        idx_ca = args.index("-c:a")
        assert args[idx_ca + 1] == "copy"
        idx_mov = args.index("-movflags")
        assert "+faststart" in args[idx_mov + 1]
        assert result == output


def test_mux_streams_raises_on_ffmpeg_failure(tmp_path):
    output = tmp_path / "output.mp4"

    with patch("backend.services.muxer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=1, stderr="encoding error")

        with pytest.raises(RuntimeError, match="FFmpeg muxing failed"):
            mux_streams(
                video_url="https://example.com/video.webm",
                audio_url="https://example.com/audio.webm",
                output_path=output,
            )


def test_mux_streams_no_audio_url(tmp_path):
    """When audio_url is None, FFmpeg is called with only the video -i arg."""
    output = tmp_path / "output.mp4"

    with patch("backend.services.muxer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)

        result = mux_streams(
            video_url="https://example.com/best.mp4",
            audio_url=None,
            output_path=output,
        )

        args = mock_run.call_args[0][0]
        assert args.count("-i") == 1
        assert "https://example.com/best.mp4" in args
        assert result == output


def test_mux_streams_creates_parent_dirs(tmp_path):
    output = tmp_path / "nested" / "dir" / "output.mp4"

    with patch("backend.services.muxer.subprocess.run") as mock_run:
        mock_run.return_value = MagicMock(returncode=0)
        mux_streams("https://v.com/v.webm", "https://v.com/a.webm", output)
        assert output.parent.exists()
