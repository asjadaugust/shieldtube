"""DownloadManager — Phase 3a progressive download via FFmpeg fragmented MP4."""
from __future__ import annotations

import asyncio
import json
from asyncio.subprocess import DEVNULL, PIPE
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from backend.config import settings
from backend.services.retry import with_retry
from backend.services.stream_resolver import resolve_stream


@dataclass
class DownloadState:
    video_id: str
    file_path: Path
    expected_size: int
    process: asyncio.subprocess.Process | None = None
    status: str = "downloading"  # "downloading" | "cached" | "error"
    error_message: str | None = None
    started_at: str = field(
        default_factory=lambda: datetime.now(timezone.utc).isoformat()
    )


class DownloadManager:
    """Manages async FFmpeg downloads, tracks active state, updates DB."""

    def __init__(
        self,
        db: aiosqlite.Connection,
        cache_dir: Path | None = None,
    ) -> None:
        self._db = db
        self._cache_dir = Path(cache_dir) if cache_dir is not None else Path(settings.cache_dir)
        self._active: dict[str, DownloadState] = {}
        self._locks: dict[str, asyncio.Lock] = {}

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_or_start_download(self, video_id: str, quality: str = "auto") -> DownloadState:
        """Return existing or start a new download.

        Order of precedence:
        1. File already exists on disk and not tracked → return cached state.
        2. Download already active → return existing state.
        3. Otherwise start a new download.
        """
        cache_key = f"{video_id}_{quality}" if quality != "auto" else video_id
        output_path = self._output_path(cache_key)

        # Fast path: file on disk, not currently tracked
        if output_path.exists() and cache_key not in self._active:
            return DownloadState(
                video_id=video_id,
                file_path=output_path,
                expected_size=output_path.stat().st_size,
                process=None,
                status="cached",
            )

        if cache_key in self._active:
            return self._active[cache_key]

        return await self._start_download(video_id, quality=quality)

    def get_download_status(self, video_id: str, quality: str = "auto") -> dict | None:
        """Return progress dict for an active download, or None if unknown."""
        cache_key = f"{video_id}_{quality}" if quality != "auto" else video_id
        state = self._active.get(cache_key)
        if state is None:
            return None

        bytes_downloaded = 0
        if state.file_path.exists():
            bytes_downloaded = state.file_path.stat().st_size

        bytes_total = state.expected_size or 1
        percent = (bytes_downloaded / bytes_total) * 100.0

        return {
            "status": state.status,
            "bytes_downloaded": bytes_downloaded,
            "bytes_total": state.expected_size,
            "percent": percent,
        }

    # ------------------------------------------------------------------
    # Internal helpers
    # ------------------------------------------------------------------

    async def _start_download(self, video_id: str, quality: str = "auto") -> DownloadState:
        """Acquire per-video lock, resolve stream, launch FFmpeg."""
        cache_key = f"{video_id}_{quality}" if quality != "auto" else video_id
        if cache_key not in self._locks:
            self._locks[cache_key] = asyncio.Lock()

        async with self._locks[cache_key]:
            # Double-check: another coroutine may have raced us to the lock
            if cache_key in self._active:
                return self._active[cache_key]

            # Resolve stream URLs without blocking the event loop
            stream_info = await with_retry(
                lambda: asyncio.to_thread(resolve_stream, video_id, True, quality),
                max_retries=2,
                description=f"resolve_stream({video_id}, quality={quality})",
            )

            video_url: str = stream_info["video_url"]
            audio_url: str | None = stream_info["audio_url"]
            filesize: int = stream_info["filesize"]

            # Store chapters in DB
            chapters_json = json.dumps(stream_info.get("chapters", []))
            await self._db.execute(
                "UPDATE videos SET chapters_json = ? WHERE id = ?",
                (chapters_json, video_id),
            )
            await self._db.commit()

            output_path = self._output_path(cache_key)
            output_path.parent.mkdir(parents=True, exist_ok=True)

            cmd = ["ffmpeg", "-y", "-i", video_url]
            if audio_url is not None:
                cmd += ["-i", audio_url]
            cmd += [
                "-c:v", "copy",
                "-c:a", "copy",
                "-movflags", "+frag_keyframe+empty_moov",
                "-f", "mp4",
                str(output_path),
            ]

            process = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=DEVNULL,
                stderr=PIPE,
            )

            state = DownloadState(
                video_id=video_id,
                file_path=output_path,
                expected_size=filesize,
                process=process,
                status="downloading",
            )
            self._active[cache_key] = state

            # Persist to DB
            await self._db.execute(
                "UPDATE videos SET cache_status = 'downloading', cached_video_path = ? WHERE id = ?",
                (str(output_path), video_id),
            )
            await self._db.commit()

            # Monitor in background
            asyncio.create_task(self._monitor_download(cache_key, video_id, process))

            return state

    async def _monitor_download(
        self,
        cache_key: str,
        video_id: str,
        process: asyncio.subprocess.Process,
    ) -> None:
        """Wait for FFmpeg to finish, then update state and DB."""
        _, stderr = await process.communicate()

        state = self._active.get(cache_key)

        if process.returncode == 0:
            # Update to actual file size
            actual_size = 0
            if state is not None and state.file_path.exists():
                actual_size = state.file_path.stat().st_size

            if state is not None:
                state.status = "cached"
                state.expected_size = actual_size

            await self._db.execute(
                "UPDATE videos SET cache_status = 'cached' WHERE id = ?",
                (video_id,),
            )
            await self._db.commit()
        else:
            error_tail = stderr[-500:].decode("utf-8", errors="replace") if stderr else ""

            if state is not None:
                state.status = "error"
                state.error_message = error_tail

            await self._db.execute(
                "UPDATE videos SET cache_status = 'error' WHERE id = ?",
                (video_id,),
            )
            await self._db.commit()

        # Grace period then clean up tracking dicts
        await asyncio.sleep(5)
        self._active.pop(cache_key, None)
        self._locks.pop(cache_key, None)

    def _output_path(self, video_id: str) -> Path:
        return self._cache_dir / f"{video_id}.mp4"
