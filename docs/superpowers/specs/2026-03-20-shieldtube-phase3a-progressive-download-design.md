# Phase 3a: Backend Progressive Download — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft
**Source:** [ShieldTube PRD](../../ShieldTube_PRD.md) — Phase 3: Progressive Download
**Depends on:** Phase 2a Backend Browse API (complete)

---

## Goal

Replace the block-until-muxed stream endpoint with a streaming pipe that serves bytes as FFmpeg produces them, plus watch history with position tracking.

**Success criteria:** Click play → first bytes served within 3 seconds → seek works on partially-downloaded file → watch position saved every 10 seconds → resume from last position on re-play.

---

## Architecture Change

```
BEFORE (Phase 1):
  Click → yt-dlp resolve → FFmpeg mux ENTIRE file → serve complete file
  (blocks for full mux duration — minutes for 4K)

AFTER (Phase 3a):
  Click → yt-dlp resolve → FFmpeg pipes to growing file → serve immediately
  (first bytes available in ~2 seconds, file grows in background)

  ┌──────────────────────────────────────────────────────┐
  │  Download Manager                                     │
  │                                                       │
  │  Active downloads: {video_id: DownloadState}          │
  │                                                       │
  │  DownloadState:                                       │
  │    - process: FFmpeg async subprocess                  │
  │    - file_path: growing MP4 file                      │
  │    - expected_size: from yt-dlp format info            │
  │    - bytes_written: current file size                  │
  │    - status: downloading | cached | error              │
  │                                                       │
  │  Stream endpoint reads from growing file:              │
  │    - Content-Length = expected_size                     │
  │    - Yields available bytes                            │
  │    - Waits for more bytes if client seeks ahead        │
  └──────────────────────────────────────────────────────┘
```

---

## Components

4 components. Components A and B are independent and can be built in parallel.

### Component 1: Streaming Download Manager

**Purpose:** Manage concurrent streaming downloads. Start FFmpeg as a background subprocess that writes to a growing file. Track active downloads so multiple requests for the same video share one download.

**Files:**
- `backend/services/download_manager.py` — DownloadManager + DownloadState

**DownloadState dataclass:**
- `video_id: str`
- `file_path: Path`
- `expected_size: int` — total bytes expected (from yt-dlp format info)
- `process: asyncio.subprocess.Process | None` — FFmpeg subprocess
- `status: str` — "downloading", "cached", "error"
- `error_message: str | None`
- `started_at: str`

**DownloadManager class:**
- `__init__(self, db)` — stores DB reference, initializes active downloads dict and per-video locks dict
- `async get_or_start_download(video_id) -> DownloadState`:
  - If file exists on disk and not actively downloading → return cached state
  - If active download exists → return it (multiple requests share one download)
  - Otherwise → start new download
- `async _start_download(video_id) -> DownloadState`:
  - Acquire per-video asyncio.Lock (prevents duplicate downloads)
  - Resolve stream via `asyncio.to_thread(resolve_stream, video_id)` (non-blocking)
  - Estimate expected file size from yt-dlp format info
  - Start FFmpeg as `asyncio.create_subprocess_exec` writing to `{cache_dir}/videos/{id}.mp4`
  - FFmpeg command: `ffmpeg -y -i {video_url} [-i {audio_url}] -c:v copy -c:a copy -movflags +frag_keyframe+empty_moov -f mp4 {output}`
  - Update DB: `videos.cache_status = 'downloading'`, `videos.cached_video_path = path`
  - Launch `_monitor_download()` as background task
  - Return DownloadState immediately (don't wait for FFmpeg to finish)
- `async _monitor_download(video_id, process, path)`:
  - `await process.communicate()` — waits for FFmpeg to finish
  - On success (returncode 0): set status="cached", update DB
  - On failure: set status="error", store stderr, update DB
  - After 5-second delay: remove from active downloads dict
- `get_download_status(video_id) -> dict | None`:
  - Returns `{status, bytes_downloaded, bytes_total, percent}` for active downloads
  - Returns None if no active download
- `_estimate_size(stream_info) -> int`:
  - `resolve_stream()` must be modified to also return `filesize` and `filesize_approx` from yt-dlp's format info (available in `info["requested_formats"][0]` and `[1]`)
  - Sums video + audio filesize estimates
  - Falls back to `100_000_000` (100MB) if neither field is available

**Design decisions:**
- Singleton per app lifetime — initialized in FastAPI lifespan, stored on app.state
- Per-video `asyncio.Lock` prevents duplicate downloads for the same video
- FFmpeg uses `asyncio.create_subprocess_exec` for non-blocking subprocess management
- `resolve_stream` wrapped in `asyncio.to_thread` to unblock the event loop
- Active downloads cleaned up 5 seconds after FFmpeg exits (allows in-flight range requests to finish)

### Component 2: Growing-File Range-Request Server

**Purpose:** Serve bytes from a file that is still being written by FFmpeg. Wait for bytes that haven't been written yet rather than returning an error.

**Modifications to:** `backend/api/routers/video.py`

**Behavior:**
- When `status == "cached"`: serve normally (existing behavior, no change)
- When `status == "downloading"`:
  - Set `Content-Length` to `expected_size` from DownloadState
  - For range requests: if requested bytes are within current file size, serve immediately. If requested bytes are beyond current file size, poll file size every 100ms until bytes are available (with configurable timeout, default 30s)
  - If timeout: return 503 Service Unavailable
- When `status == "none"`: trigger download via DownloadManager, then serve growing file

**Growing-file read loop (async generator):**
- Track current read position and target end position
- While position < target:
  - Check file size. If bytes available → read chunk, yield, advance position
  - If download complete (cached) and position beyond file → break
  - If download error → break
  - If bytes not yet available → poll every 100ms, timeout after `DOWNLOAD_WAIT_TIMEOUT` seconds
  - If timeout → break (caller returns 503)

### Component 3: Watch History

**Purpose:** Track what the user has watched, at what position, and whether they completed it. Enables resume-from-last-position and a History feed.

**New migration:** `backend/db/migrations/002_watch_history.sql`

```sql
CREATE TABLE IF NOT EXISTS watch_history (
    video_id TEXT PRIMARY KEY,
    watched_at TEXT NOT NULL,
    position_seconds INTEGER DEFAULT 0,
    duration INTEGER,
    completed INTEGER DEFAULT 0
);
```

Single row per video (upsert on each progress report). `completed` is set to 1 when `position_seconds > 0.9 * duration`.

**New dataclass:** `WatchHistoryEntry(video_id, watched_at, position_seconds, duration, completed)`

**New repository:** `WatchHistoryRepo`
- `upsert(entry)` — INSERT OR REPLACE, auto-sets `completed` based on 90% threshold
- `get(video_id) -> WatchHistoryEntry | None`
- `get_recent(limit=50) -> list[WatchHistoryEntry]` — ORDER BY watched_at DESC

**New endpoints (in `backend/api/routers/watch.py`):**

`POST /api/video/{video_id}/progress`
- Body: `{"position_seconds": 180, "duration": 600}`
- Upserts into watch_history with current timestamp
- Returns `{"status": "ok"}`

`GET /api/video/{video_id}/meta`
- Returns video metadata from `videos` table + `last_position_seconds` from `watch_history`
- Response: `{"id": "...", "title": "...", "channel_name": "...", "duration": 600, "cache_status": "cached", "last_position_seconds": 180}`

`GET /api/feed/history`
- Returns recently watched videos ordered by watched_at desc
- Same response format as other feed endpoints: `{"feed_type": "history", "videos": [...], "cached_at": null, "from_cache": false}`

### Component 4: Download Status Endpoint

**Purpose:** Report download progress for active downloads.

**Added to:** `backend/api/routers/watch.py`

`GET /api/video/{video_id}/download-status`
- Queries DownloadManager for active download state
- If active: returns `{"status": "downloading", "bytes_downloaded": N, "bytes_total": M, "percent": P}`
- If not active, check DB `videos.cache_status`:
  - "cached": return `{"status": "cached", "percent": 100}`
  - "none": return `{"status": "none", "percent": 0}`
  - "error": return `{"status": "error", "percent": 0}`

---

## Modified Files Summary

| File | Change |
|------|--------|
| `backend/services/download_manager.py` | New: DownloadManager + DownloadState |
| `backend/api/routers/video.py` | Modify: stream endpoint uses DownloadManager, growing-file serving |
| `backend/db/migrations/002_watch_history.sql` | New: watch_history table |
| `backend/db/models.py` | Add: WatchHistoryEntry dataclass |
| `backend/db/repositories.py` | Add: WatchHistoryRepo |
| `backend/api/routers/watch.py` | New: POST progress, GET meta, GET history, GET download-status |
| `backend/api/main.py` | Modify: register watch router, init DownloadManager in lifespan |
| `backend/config.py` | Add: DOWNLOAD_WAIT_TIMEOUT setting |

---

## New API Endpoints

```
POST /api/video/{id}/progress        ← Shield reports position every 10s
  Body: {"position_seconds": 180, "duration": 600}
  Response: {"status": "ok"}

GET  /api/video/{id}/meta            ← Video metadata + resume position
  Response: {
    "id": "...", "title": "...", "channel_name": "...",
    "duration": 600, "cache_status": "cached",
    "last_position_seconds": 180
  }

GET  /api/feed/history               ← Watch history feed
  Response: {"feed_type": "history", "videos": [...], "cached_at": null, "from_cache": false}

GET  /api/video/{id}/download-status ← Download progress
  Response: {"status": "downloading", "bytes_downloaded": 524288000, "bytes_total": 2100000000, "percent": 25}
```

---

## New Config Variables

| Variable | Purpose | Default |
|----------|---------|---------|
| `DOWNLOAD_WAIT_TIMEOUT` | Max seconds to wait for bytes in growing-file serving | 30 |

---

## Parallel Workstream Strategy

```
Task 0: Migration + model + repo + config (sequential)
        │
        ├── Workstream A: Download manager (worktree)
        │     - DownloadManager class
        │     - FFmpeg async subprocess
        │     - Download state tracking
        │
        ├── Workstream B: Watch history endpoints (worktree)
        │     - POST progress
        │     - GET meta
        │     - GET history
        │     - GET download-status
        │
        Task 3: Growing-file stream endpoint (sequential, integrates A)
        Task 4: Register routes + integration (sequential)
```

Components A (DownloadManager) and B (watch history endpoints) touch entirely different files and can be parallel.

---

## Testing Strategy

- **DownloadManager:** Mock FFmpeg subprocess (use `asyncio.create_subprocess_exec` with a simple cat/dd command or mock). Test: start download creates file, duplicate requests share same download, lock prevents races, monitor sets "cached" on success and "error" on failure, cleanup removes from active dict.
- **Growing-file server:** Create a file, append bytes in a background task simulating FFmpeg, verify range requests wait and return correct data. Test timeout returns 503.
- **Watch history:** Test CRUD with in-memory SQLite. Test completion detection (>90% sets completed=1, <90% sets completed=0). Test get_recent ordering.
- **Endpoints:** Integration tests with mocked DownloadManager. Test progress POST upserts correctly, meta returns last_position_seconds, history returns ordered list, download-status reports correct percent.
- **Stream endpoint:** Test cached file serves normally (unchanged behavior), downloading file serves growing content, unknown video triggers download.

---

## What This Phase Does NOT Include

- Shield app changes (deferred to Phase 3b)
- Background download queue / pre-caching (Phase 4)
- Segmented download with seek-triggered reprioritization (streaming pipe covers the success criteria)
- Download pause/resume (Phase 4)
- Concurrent download limits (single-user, one video at a time is sufficient)
