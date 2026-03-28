"""DownloadManager — Phase 3a progressive download via FFmpeg fragmented MP4."""
from __future__ import annotations

import asyncio
import json
import logging
from asyncio.subprocess import DEVNULL, PIPE
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from backend.config import settings
from backend.services.retry import with_retry
from backend.services.stream_resolver import resolve_stream, QUALITY_FORMATS

logger = logging.getLogger(__name__)


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

    async def _remux_to_faststart(self, file_path: Path, video_id: str) -> None:
        """Remux a fragmented MP4 to standard MP4 with moov at start for seeking."""
        temp_path = file_path.with_suffix(".tmp.mp4")
        cmd = [
            "ffmpeg", "-y", "-i", str(file_path),
            "-c", "copy",
            "-movflags", "+faststart",
            "-f", "mp4",
            str(temp_path),
        ]
        proc = await asyncio.create_subprocess_exec(*cmd, stdout=DEVNULL, stderr=PIPE)
        _, stderr = await proc.communicate()
        if proc.returncode == 0 and temp_path.exists():
            temp_path.replace(file_path)
            logger.info("Remuxed %s to seekable MP4 (faststart)", video_id)
        else:
            temp_path.unlink(missing_ok=True)
            logger.warning("Faststart remux failed for %s, keeping original", video_id)

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
                "-movflags", "+frag_keyframe+empty_moov+default_base_moof",
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
            # Remux fragmented MP4 to seekable MP4 with moov at start
            if state is not None and state.file_path.exists():
                await self._remux_to_faststart(state.file_path, video_id)

            # Update to actual file size
            actual_size = 0
            if state is not None and state.file_path.exists():
                actual_size = state.file_path.stat().st_size

            if state is not None:
                state.status = "cached"
                state.expected_size = actual_size

            await self._db.execute(
                "UPDATE videos SET cache_status = 'cached', cached_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), video_id),
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

    # ------------------------------------------------------------------
    # Queue download path (yt-dlp concurrent fragments)
    # ------------------------------------------------------------------

    async def download_for_queue(self, video_id: str, quality: str = "auto") -> DownloadState:
        """Download using yt-dlp concurrent fragments (for background queue).

        Falls back to the standard FFmpeg pipeline on failure.
        """
        cache_key = f"{video_id}_{quality}" if quality != "auto" else video_id
        output_path = self._output_path(cache_key)

        # Already cached on disk
        if output_path.exists() and cache_key not in self._active:
            return DownloadState(
                video_id=video_id, file_path=output_path,
                expected_size=output_path.stat().st_size,
                process=None, status="cached",
            )

        try:
            return await self._start_download_ytdlp(video_id, quality)
        except Exception as exc:
            logger.warning("yt-dlp download failed for %s, falling back to FFmpeg: %s", video_id, exc)
            return await self.get_or_start_download(video_id, quality)

    async def _start_download_ytdlp(self, video_id: str, quality: str = "auto") -> DownloadState:
        """Download via yt-dlp --concurrent-fragments, then remux to fragmented MP4."""
        cache_key = f"{video_id}_{quality}" if quality != "auto" else video_id
        if cache_key not in self._locks:
            self._locks[cache_key] = asyncio.Lock()

        async with self._locks[cache_key]:
            if cache_key in self._active:
                return self._active[cache_key]

            output_path = self._output_path(cache_key)
            temp_path = self._cache_dir / f"{video_id}_temp.mp4"
            output_path.parent.mkdir(parents=True, exist_ok=True)

            # Build format spec
            fmt = QUALITY_FORMATS.get(quality)
            if fmt is None:
                fmt = (
                    "bestvideo[vcodec^=vp9][height<=2160]+bestaudio/"
                    "bestvideo[height<=2160]+bestaudio/best"
                )

            url = f"https://www.youtube.com/watch?v={video_id}"
            n_frags = settings.ytdlp_concurrent_fragments

            # Resolve metadata first (title, filesize) for DB and progress tracking
            stream_info = await with_retry(
                lambda: asyncio.to_thread(resolve_stream, video_id, True, quality),
                max_retries=2,
                description=f"resolve_stream({video_id})",
            )
            expected_size = stream_info.get("filesize", 100_000_000)
            title = stream_info.get("title", "")
            channel_name = stream_info.get("channel_name", "")
            channel_id = stream_info.get("channel_id", "")

            # Update video metadata in DB
            chapters_json = json.dumps(stream_info.get("chapters", []))
            await self._db.execute(
                """UPDATE videos SET title = COALESCE(NULLIF(title, ''), ?),
                   channel_name = COALESCE(NULLIF(channel_name, ''), ?),
                   channel_id = COALESCE(NULLIF(channel_id, ''), ?),
                   chapters_json = ?
                   WHERE id = ?""",
                (title, channel_name, channel_id, chapters_json, video_id),
            )
            await self._db.commit()

            cmd = [
                "yt-dlp",
                "--concurrent-fragments", str(n_frags),
                "--format", fmt,
                "--merge-output-format", "mp4",
                "--no-part",
                "--quiet", "--no-warnings",
                "-o", str(temp_path),
                url,
            ]

            logger.info("yt-dlp queue download starting: %s '%s' (fragments=%d)", video_id, title, n_frags)

            # Mark as downloading in DB and track state
            # Use cache_dir for progress — sum all temp files for this video
            state = DownloadState(
                video_id=video_id,
                file_path=output_path,  # final path for progress tracking
                expected_size=expected_size,
                process=None,
                status="downloading",
            )
            self._active[cache_key] = state

            await self._db.execute(
                "UPDATE videos SET cache_status = 'downloading', cached_video_path = ? WHERE id = ?",
                (str(output_path), video_id),
            )
            await self._db.commit()

            # Run yt-dlp (uses create_subprocess_exec — no shell injection risk)
            process = await asyncio.create_subprocess_exec(
                *cmd, stdout=DEVNULL, stderr=PIPE,
            )
            state.process = process
            _, stderr = await process.communicate()

            if process.returncode != 0:
                error_msg = stderr[-500:].decode("utf-8", errors="replace") if stderr else ""
                state.status = "error"
                state.error_message = error_msg
                self._active.pop(cache_key, None)
                self._locks.pop(cache_key, None)
                temp_path.unlink(missing_ok=True)
                for leftover in self._cache_dir.glob(f"{video_id}_temp*"):
                    leftover.unlink(missing_ok=True)
                raise RuntimeError(f"yt-dlp failed (rc={process.returncode}): {error_msg[:200]}")

            # Remux to seekable MP4 with moov at start (fast, stream copy)
            logger.info("Remuxing %s to seekable MP4 (faststart)...", video_id)
            remux_cmd = [
                "ffmpeg", "-y", "-i", str(temp_path),
                "-c", "copy",
                "-movflags", "+faststart",
                "-f", "mp4",
                str(output_path),
            ]
            remux = await asyncio.create_subprocess_exec(
                *remux_cmd, stdout=DEVNULL, stderr=PIPE,
            )
            _, remux_stderr = await remux.communicate()

            # Clean up temp file and any yt-dlp intermediaries (.fXXX.webm etc)
            temp_path.unlink(missing_ok=True)
            for leftover in self._cache_dir.glob(f"{video_id}_temp*"):
                leftover.unlink(missing_ok=True)

            if remux.returncode != 0:
                error_msg = remux_stderr[-500:].decode("utf-8", errors="replace") if remux_stderr else ""
                state.status = "error"
                state.error_message = f"remux failed: {error_msg}"
                await self._db.execute(
                    "UPDATE videos SET cache_status = 'error' WHERE id = ?", (video_id,),
                )
                await self._db.commit()
                self._active.pop(cache_key, None)
                self._locks.pop(cache_key, None)
                raise RuntimeError(f"FFmpeg remux failed: {error_msg[:200]}")

            # Success
            actual_size = output_path.stat().st_size if output_path.exists() else 0
            state.status = "cached"
            state.file_path = output_path
            state.expected_size = actual_size

            await self._db.execute(
                "UPDATE videos SET cache_status = 'cached', cached_at = ? WHERE id = ?",
                (datetime.now(timezone.utc).isoformat(), video_id),
            )
            await self._db.commit()

            logger.info("yt-dlp queue download complete: %s (%d MB)", video_id, actual_size // (1024 * 1024))

            # Grace period then clean up
            await asyncio.sleep(5)
            self._active.pop(cache_key, None)
            self._locks.pop(cache_key, None)

            return state

    def _output_path(self, video_id: str) -> Path:
        return self._cache_dir / f"{video_id}.mp4"
