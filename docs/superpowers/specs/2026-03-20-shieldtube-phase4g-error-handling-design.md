# Phase 4g: Error Handling & Resilience — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft
**Source:** [ShieldTube PRD](../../ShieldTube_PRD.md) — Phase 4: Polish + P1 Features

---

## Goal

Add retry logic to flaky external calls and proper error responses throughout the backend. Shield app shows user-friendly errors instead of crashes.

**Success criteria:** YouTube API temporary failure → backend retries 3 times → succeeds or returns clean 503. Shield app shows toast and returns to browse.

---

## Design

### Backend: Retry Logic

Add a `retry` decorator to `backend/services/retry.py`:

```python
async def with_retry(fn, max_retries=3, backoff_base=1.0):
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as e:
            if attempt == max_retries:
                raise
            wait = backoff_base * (2 ** attempt)
            await asyncio.sleep(wait)
```

Apply to:
- `YouTubeAPI` methods (all 4: get_home_feed, get_subscriptions, search, get_video_details) — retry on httpx errors
- `resolve_stream()` in DownloadManager — retry on yt-dlp extraction failures
- `SponsorBlock.get_segments()` — already handles errors gracefully, no change needed

### Backend: Error Responses

Add FastAPI exception handlers in `backend/api/main.py`:
- `httpx.TimeoutException` → 503 with `{"error": "External service timeout", "retry_after": 5}`
- `ValueError` (no OAuth token) → 401 with `{"error": "Not authenticated"}`
- Generic unhandled → 500 with `{"error": "Internal server error"}` (no stack trace in response)

### Shield App: Error UI

In `BrowseFragment.kt` and `SearchFragment.kt`:
- On API error: show Toast with user-friendly message ("Couldn't load feed. Check your connection.")
- Don't crash — show empty state or stale cached data
- Already partially implemented (both fragments have try/catch with Toast)

In `PlaybackFragment.kt`:
- On stream error: show Toast "Video unavailable" and pop back to browse
- On progress report error: already silently caught (no change)

**Files:**

| File | Change |
|------|--------|
| `backend/services/retry.py` | New: retry decorator with exponential backoff |
| `backend/services/youtube_api.py` | Wrap API calls with retry |
| `backend/services/download_manager.py` | Wrap resolve_stream with retry |
| `backend/api/main.py` | Add exception handlers |
| `backend/tests/test_retry.py` | New: retry logic tests |
| `shield-app/.../ui/BrowseFragment.kt` | Improve error messages |
| `shield-app/.../ui/SearchFragment.kt` | Improve error messages |
| `shield-app/.../player/PlaybackFragment.kt` | Handle stream errors gracefully |

---

## What This Phase Does NOT Include

- Circuit breaker pattern
- Offline mode / network state detection
- Retry configuration (hardcoded 3 retries)
- Error reporting / telemetry
