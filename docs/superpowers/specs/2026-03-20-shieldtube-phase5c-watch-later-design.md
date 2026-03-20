# Phase 5c: Watch Later Queue Sync — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft

---

## Goal

Sync YouTube's Watch Later playlist so users can add videos on their phone and watch them on Shield.

**Success criteria:** Add a video to Watch Later on YouTube → it appears in ShieldTube's Watch Later feed → click to play.

---

## Design

### Backend

1. **New endpoint: `GET /api/feed/watch-later`** — Fetches the user's Watch Later playlist via YouTube Data API (`playlistItems.list` with `playlistId=WL`). Returns same feed response format.

2. **Periodic sync** — Add Watch Later to the feed refresher (refresh every 15 minutes alongside Home feed).

3. **Caching** — Store in `feed_cache` with `feed_type = "watch_later"`. ETag caching applies.

### Shield App

1. **BrowseFragment.kt** — Add "Watch Later" as a third sidebar header. Loads from `/api/feed/watch-later`.

**Files:**

| File | Change |
|------|--------|
| `backend/services/youtube_api.py` | Add get_watch_later() method |
| `backend/api/routers/feed.py` | Add GET /api/feed/watch-later endpoint |
| `backend/services/feed_refresher.py` | Add Watch Later to refresh loop |
| `shield-app/.../ui/BrowseFragment.kt` | Add Watch Later header |
| `backend/tests/test_watch_later.py` | New: tests |

---

## Note

YouTube's Watch Later playlist (`WL`) requires authenticated access. The existing OAuth token (youtube.readonly scope) should have access. If not, this is a known YouTube API limitation — some accounts restrict WL access via API.
