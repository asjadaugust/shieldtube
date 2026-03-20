"""Tests for DownloadManager — Phase 3a progressive download."""
from __future__ import annotations

import asyncio
import os
from pathlib import Path
from unittest.mock import AsyncMock, patch, MagicMock

import aiosqlite
import pytest

from backend.db.database import _run_migrations
from backend.services.download_manager import DownloadManager, DownloadState


# ---------------------------------------------------------------------------
# Helpers / fixtures
# ---------------------------------------------------------------------------

class MockProcess:
    def __init__(self, returncode: int = 0, stderr: bytes = b""):
        self.returncode = returncode
        self._stderr = stderr

    async def communicate(self):
        return (b"", self._stderr)


FAKE_STREAM = {
    "video_url": "https://example.com/video.webm",
    "audio_url": "https://example.com/audio.webm",
    "filesize": 50_000_000,
    "duration": 120,
    "title": "Test Video",
}

FAKE_STREAM_NO_AUDIO = {
    "video_url": "https://example.com/best.mp4",
    "audio_url": None,
    "filesize": 30_000_000,
    "duration": 60,
    "title": "Test Video No Audio",
}


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


@pytest.fixture
async def db_with_video(db):
    """Database with a seeded video row so UPDATE queries match."""
    await db.execute(
        """
        INSERT INTO videos (id, title, channel_name, channel_id, cache_status)
        VALUES (?, ?, ?, ?, ?)
        """,
        ("test_vid", "Test Video", "Test Channel", "ch1", "none"),
    )
    await db.commit()
    yield db


@pytest.fixture
def manager(db_with_video):
    return DownloadManager(db=db_with_video)


# ---------------------------------------------------------------------------
# test_cached_file_returns_cached_state
# ---------------------------------------------------------------------------

async def test_cached_file_returns_cached_state(tmp_path, db_with_video):
    """If a file already exists on disk, get_or_start_download returns cached state without spawning FFmpeg."""
    cached_file = tmp_path / "test_vid.mp4"
    cached_file.write_bytes(b"fake video data")

    mgr = DownloadManager(db=db_with_video, cache_dir=tmp_path)

    with patch("backend.services.download_manager.asyncio.create_subprocess_exec") as mock_exec:
        state = await mgr.get_or_start_download("test_vid")

    assert state.status == "cached"
    assert state.video_id == "test_vid"
    assert state.file_path == cached_file
    mock_exec.assert_not_called()


# ---------------------------------------------------------------------------
# test_new_download_starts_ffmpeg
# ---------------------------------------------------------------------------

async def test_new_download_starts_ffmpeg(tmp_path, db_with_video):
    """Starting a fresh download builds the correct FFmpeg command."""
    mock_proc = MockProcess(returncode=0)

    with (
        patch(
            "backend.services.download_manager.asyncio.to_thread",
            new=AsyncMock(return_value=FAKE_STREAM),
        ),
        patch(
            "backend.services.download_manager.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ) as mock_exec,
    ):
        mgr = DownloadManager(db=db_with_video, cache_dir=tmp_path)
        state = await mgr.get_or_start_download("test_vid")

    assert state.status == "downloading"
    assert state.video_id == "test_vid"
    assert state.expected_size == FAKE_STREAM["filesize"]

    # Verify FFmpeg command structure
    call_args = mock_exec.call_args[0]  # positional args (the cmd items)
    cmd = list(call_args)

    assert cmd[0] == "ffmpeg"
    assert "-y" in cmd
    assert FAKE_STREAM["video_url"] in cmd
    assert FAKE_STREAM["audio_url"] in cmd
    assert "-c:v" in cmd
    assert "copy" in cmd
    assert "-c:a" in cmd
    assert "-movflags" in cmd

    # Must use frag_keyframe+empty_moov, NOT faststart
    movflags_idx = cmd.index("-movflags")
    movflags_val = cmd[movflags_idx + 1]
    assert "frag_keyframe" in movflags_val
    assert "empty_moov" in movflags_val
    assert "faststart" not in movflags_val

    assert "-f" in cmd
    assert "mp4" in cmd


# ---------------------------------------------------------------------------
# test_duplicate_requests_share_download
# ---------------------------------------------------------------------------

async def test_duplicate_requests_share_download(tmp_path, db_with_video):
    """Calling get_or_start_download twice returns the same DownloadState object."""
    mock_proc = MockProcess(returncode=0)
    call_count = 0

    async def fake_to_thread(fn, *args, **kwargs):
        nonlocal call_count
        call_count += 1
        return FAKE_STREAM

    with (
        patch(
            "backend.services.download_manager.asyncio.to_thread",
            side_effect=fake_to_thread,
        ),
        patch(
            "backend.services.download_manager.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ),
    ):
        mgr = DownloadManager(db=db_with_video, cache_dir=tmp_path)
        state1 = await mgr.get_or_start_download("test_vid")
        state2 = await mgr.get_or_start_download("test_vid")

    assert state1 is state2
    assert call_count == 1  # resolve_stream called exactly once


# ---------------------------------------------------------------------------
# test_monitor_sets_cached_on_success
# ---------------------------------------------------------------------------

async def test_monitor_sets_cached_on_success(tmp_path, db_with_video):
    """When FFmpeg exits with returncode=0, state transitions to 'cached'."""
    output_path = tmp_path / "test_vid.mp4"

    mock_proc = MockProcess(returncode=0)

    with (
        patch(
            "backend.services.download_manager.asyncio.to_thread",
            new=AsyncMock(return_value=FAKE_STREAM),
        ),
        patch(
            "backend.services.download_manager.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ),
    ):
        mgr = DownloadManager(db=db_with_video, cache_dir=tmp_path)
        state = await mgr.get_or_start_download("test_vid")

        # Write fake output so stat() works
        output_path.write_bytes(b"x" * 1000)

        # Run monitor directly and await it
        with patch("backend.services.download_manager.asyncio.sleep", new=AsyncMock()):
            await mgr._monitor_download("test_vid", "test_vid", mock_proc)

    assert state.status == "cached"
    assert state.expected_size == 1000  # updated to actual file size

    # Verify DB updated
    async with db_with_video.execute(
        "SELECT cache_status FROM videos WHERE id = ?", ("test_vid",)
    ) as cursor:
        row = await cursor.fetchone()
    assert row["cache_status"] == "cached"


# ---------------------------------------------------------------------------
# test_monitor_sets_error_on_failure
# ---------------------------------------------------------------------------

async def test_monitor_sets_error_on_failure(tmp_path, db_with_video):
    """When FFmpeg exits with returncode != 0, state transitions to 'error'."""
    mock_proc = MockProcess(returncode=1, stderr=b"fatal error: codec not found")

    with (
        patch(
            "backend.services.download_manager.asyncio.to_thread",
            new=AsyncMock(return_value=FAKE_STREAM),
        ),
        patch(
            "backend.services.download_manager.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ),
    ):
        mgr = DownloadManager(db=db_with_video, cache_dir=tmp_path)
        state = await mgr.get_or_start_download("test_vid")

        with patch("backend.services.download_manager.asyncio.sleep", new=AsyncMock()):
            await mgr._monitor_download("test_vid", "test_vid", mock_proc)

    assert state.status == "error"
    assert state.error_message is not None
    assert "codec not found" in state.error_message

    # Verify DB updated
    async with db_with_video.execute(
        "SELECT cache_status FROM videos WHERE id = ?", ("test_vid",)
    ) as cursor:
        row = await cursor.fetchone()
    assert row["cache_status"] == "error"


# ---------------------------------------------------------------------------
# test_get_download_status_returns_progress
# ---------------------------------------------------------------------------

async def test_get_download_status_returns_progress(tmp_path, db_with_video):
    """get_download_status returns a dict with bytes_downloaded, bytes_total, percent."""
    mock_proc = MockProcess(returncode=0)
    output_path = tmp_path / "test_vid.mp4"

    with (
        patch(
            "backend.services.download_manager.asyncio.to_thread",
            new=AsyncMock(return_value=FAKE_STREAM),
        ),
        patch(
            "backend.services.download_manager.asyncio.create_subprocess_exec",
            new=AsyncMock(return_value=mock_proc),
        ),
    ):
        mgr = DownloadManager(db=db_with_video, cache_dir=tmp_path)
        await mgr.get_or_start_download("test_vid")

    # Simulate partial download
    output_path.write_bytes(b"x" * 25_000_000)

    progress = mgr.get_download_status("test_vid")

    assert progress is not None
    assert progress["status"] == "downloading"
    assert progress["bytes_downloaded"] == 25_000_000
    assert progress["bytes_total"] == FAKE_STREAM["filesize"]
    assert progress["percent"] == pytest.approx(50.0, abs=0.1)


# ---------------------------------------------------------------------------
# test_get_download_status_returns_none_for_unknown
# ---------------------------------------------------------------------------

async def test_get_download_status_returns_none_for_unknown(tmp_path, db_with_video):
    """get_download_status returns None for a video_id not in _active."""
    mgr = DownloadManager(db=db_with_video, cache_dir=tmp_path)
    result = mgr.get_download_status("nonexistent_vid")
    assert result is None
