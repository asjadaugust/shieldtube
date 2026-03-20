# Phase 3a: Backend Progressive Download — Implementation Plan

> **For agentic workers:** This plan uses Ralph Loop methodology with parallel sub-agents in git worktrees. Use `superpowers:dispatching-parallel-agents` to run Workstreams A and B concurrently. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the blocking stream endpoint with a streaming pipe that serves bytes as FFmpeg produces them, plus watch history with position tracking.

**Architecture:** DownloadManager starts FFmpeg as an async subprocess writing to a growing file. Stream endpoint serves bytes from the growing file, waiting for FFmpeg to write ahead of the read position. Watch history tracks playback position via periodic POST from Shield app.

**Tech Stack:** Python 3.11+, FastAPI, aiosqlite, asyncio subprocess (all already in requirements.txt)

---

## Execution Model

```
Task 0: Migration + model + repo + config + resolve_stream update (sequential)
        |
        +-- Workstream A: Download manager (worktree)
        +-- Workstream B: Watch history endpoints (worktree)
                |
        Task 3: Growing-file stream endpoint (sequential, integrates A)
        Task 4: Register routes + main.py integration (sequential)
```

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `backend/services/download_manager.py` | DownloadManager + DownloadState: async FFmpeg subprocess, active download tracking |
| `backend/db/migrations/002_watch_history.sql` | watch_history table |
| `backend/api/routers/watch.py` | POST progress, GET meta, GET history, GET download-status |
| `backend/tests/test_download_manager.py` | DownloadManager unit tests |
| `backend/tests/test_watch_endpoints.py` | Watch history endpoint tests |
| `backend/tests/test_growing_file_stream.py` | Growing-file range-request tests |
| `backend/tests/test_watch_history_repo.py` | WatchHistoryRepo CRUD tests |

### Modified Files

| File | Changes |
|------|---------|
| `backend/config.py` | Add `download_wait_timeout: int = 30` |
| `backend/services/stream_resolver.py` | Return `filesize` from yt-dlp format info |
| `backend/db/models.py` | Add `WatchHistoryEntry` dataclass |
| `backend/db/repositories.py` | Add `WatchHistoryRepo` |
| `backend/api/routers/video.py` | Replace blocking stream with DownloadManager + growing-file serving |
| `backend/api/main.py` | Register watch router, init DownloadManager in lifespan |

---

## Task 0: Scaffolding (Sequential)

- [ ] **Step 1: Add config setting** — Add `download_wait_timeout: int = 30` to Settings class in `backend/config.py`

- [ ] **Step 2: Update stream_resolver to return filesize** — Modify `resolve_stream()` in `backend/services/stream_resolver.py` to extract `filesize` and `filesize_approx` from yt-dlp's format info. For the `requested_formats` branch: sum `video_fmt.get("filesize") or video_fmt.get("filesize_approx") or 0` + audio equivalent. For the single-stream fallback branch (`else: video_url = info["url"]`): use `info.get("filesize") or info.get("filesize_approx") or 0`. Fall back to 100MB if all are zero/None. Add `"filesize"` key to returned dict.

- [ ] **Step 3: Create watch_history migration** — `backend/db/migrations/002_watch_history.sql` with `watch_history` table (video_id TEXT PRIMARY KEY, watched_at TEXT NOT NULL, position_seconds INTEGER DEFAULT 0, duration INTEGER, completed INTEGER DEFAULT 0).

- [ ] **Step 4: Add WatchHistoryEntry to models.py** — Append dataclass with fields: video_id, watched_at, position_seconds (default 0), duration (optional), completed (default 0).

- [ ] **Step 5: Add WatchHistoryRepo to repositories.py** — `upsert(entry)` with auto-completion at 90% threshold, `get(video_id)`, `get_recent(limit=50)` ordered by watched_at DESC.

- [ ] **Step 6: Write repo tests** — `backend/tests/test_watch_history_repo.py` with in-memory SQLite. Test upsert, completion detection, update existing, get_recent ordering, limit.

- [ ] **Step 7: Run tests** — `python -m pytest backend/tests/test_watch_history_repo.py -v` — ALL pass

- [ ] **Step 8: Commit** — `chore: add Phase 3a scaffolding`

---

## Workstream A: Download Manager (Parallel -- Worktree)

**Completion Promise:** `DOWNLOAD MANAGER COMPLETE`

Agent builds `backend/services/download_manager.py` with DownloadState dataclass and DownloadManager class:

- `get_or_start_download(video_id)` -- returns cached/active/new DownloadState
- `_start_download(video_id)` -- resolves stream via asyncio.to_thread, starts FFmpeg with `asyncio.create_subprocess_exec`, movflags `+frag_keyframe+empty_moov`, monitors in background
- `_monitor_download(video_id, process)` -- waits for FFmpeg, sets cached/error status, updates DB, cleans up after 5s delay
- `get_download_status(video_id)` -- returns progress dict or None
- Per-video asyncio.Lock prevents duplicate downloads

Tests in `backend/tests/test_download_manager.py`:
- Cached file returns cached state
- New download starts FFmpeg subprocess
- Duplicate requests share one download
- Monitor sets "cached" on success
- Monitor sets "error" on failure
- get_download_status returns progress
- get_download_status returns None for unknown

All FFmpeg subprocess and resolve_stream calls mocked.

---

## Workstream B: Watch History Endpoints (Parallel -- Worktree)

**Completion Promise:** `WATCH ENDPOINTS COMPLETE`

Agent builds `backend/api/routers/watch.py` with 4 endpoints:

- `POST /video/{video_id}/progress` -- accepts `{position_seconds, duration}`, upserts watch_history, returns `{"status": "ok"}`
- `GET /video/{video_id}/meta` -- returns video metadata + last_position_seconds from watch_history join
- `GET /feed/history` -- returns recently watched videos ordered by watched_at desc, same format as other feeds
- `GET /video/{video_id}/download-status` -- checks app.state.download_manager first, falls back to DB cache_status

Tests in `backend/tests/test_watch_endpoints.py`:
- Progress POST upserts correctly
- Progress POST updates on second call
- Meta returns last_position_seconds
- Meta returns 0 for unwatched
- History returns ordered list
- History returns empty when no history
- Download-status returns "none" for unknown
- Download-status returns "cached" for cached video

All DB operations use patched in-memory SQLite.

---

## Task 3: Growing-File Stream Endpoint (Sequential -- After Workstream A)

**Depends on:** Workstream A merged

- [ ] **Step 1: Replace stream endpoint** -- Modify `backend/api/routers/video.py`:
  - Remove `get_or_create_stream()` function
  - `stream_video()` now uses `request.app.state.download_manager.get_or_start_download(video_id)`
  - For cached files: serve normally via FileResponse (200 with Accept-Ranges)
  - For downloading files (range request): serve via `_iter_growing_file()` async generator (206)
  - For downloading files (no range header): serve via `_iter_growing_file(path, 0, expected_size-1, state)` with `Content-Length: expected_size`, `Accept-Ranges: bytes` (200) — ExoPlayer issues a non-range GET first to discover file size
  - `_iter_growing_file(file_path, start, end, state)`: reads available bytes, yields chunks, polls every 100ms for bytes beyond file size, times out after `settings.download_wait_timeout` seconds
  - Wait up to 5s for file to appear on disk before returning 503
  - Remove `from backend.services.muxer import mux_streams` import (muxer.py is now dead code — DownloadManager handles FFmpeg directly)
  - Keep thumbnail endpoint unchanged

- [ ] **Step 2: Write growing-file tests** -- `backend/tests/test_growing_file_stream.py`:
  - Cached file serves 200
  - Cached file serves 206 for range request
  - Growing file serves available bytes
  - Growing file waits for bytes beyond current size
  - Returns 503 when file never appears

- [ ] **Step 3: Run all tests** -- `python -m pytest backend/tests/ -v` -- ALL pass

- [ ] **Step 4: Commit** -- `feat: replace blocking stream with growing-file progressive download`

---

## Task 4: Register Routes + Integration (Sequential)

**Depends on:** Task 3 + Workstream B merged

- [ ] **Step 1: Update main.py** -- Register watch router, init DownloadManager in lifespan (stored on `app.state.download_manager`), bump version to 0.3.0

- [ ] **Step 2: Run full test suite** -- `python -m pytest backend/tests/ -v` -- ALL pass

- [ ] **Step 3: Commit** -- `feat: register watch router and init DownloadManager in lifespan`

---

## Parallel Dispatch Summary

| Workstream | Worktree Branch | Completion Promise | Depends On |
|---|---|---|---|
| A: Download Manager | `ws/download-manager` | `DOWNLOAD MANAGER COMPLETE` | Task 0 |
| B: Watch Endpoints | `ws/watch-endpoints` | `WATCH ENDPOINTS COMPLETE` | Task 0 |
| Task 3: Growing-file stream | main | N/A | A |
| Task 4: Integration | main | N/A | A + B + Task 3 |

**Orchestrator flow:**
1. Execute Task 0 (scaffolding) on main
2. Dispatch Workstreams A and B in parallel (separate worktrees)
3. As each completes, review and merge
4. Execute Task 3 (growing-file stream) on main
5. Execute Task 4 (register routes) on main
6. Run full test suite
7. Linearize history, strip Co-Authored-By
