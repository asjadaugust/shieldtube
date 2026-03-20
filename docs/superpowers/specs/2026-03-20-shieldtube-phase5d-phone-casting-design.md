# Phase 5d: Phone → Shield Casting — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft

---

## Goal

Cast a video from your phone to ShieldTube — browse YouTube on your phone, share a link, it plays on the TV.

**Success criteria:** On phone, share a YouTube URL to ShieldTube → video starts playing on Shield TV.

---

## Design

Simple HTTP-based casting (no DIAL/CAST protocol needed — ShieldTube controls its own playback).

### Backend

1. **New endpoint: `POST /api/cast`** — Accepts `{"url": "https://youtube.com/watch?v=..."}` or `{"video_id": "..."}`. Extracts video ID, stores as "now playing" in a simple state.

2. **New endpoint: `GET /api/cast/now-playing`** — Returns the currently queued video ID, or null if nothing queued. Shield app polls this.

### Shield App

1. **Polling service** — BrowseFragment polls `GET /api/cast/now-playing` every 5 seconds. When a video ID appears, navigates to PlaybackFragment automatically.

### Phone (No App Needed)

Users share YouTube URLs to the backend via:
- Browser bookmarklet: `javascript:fetch('http://NAS_IP:8080/api/cast',{method:'POST',headers:{'Content-Type':'application/json'},body:JSON.stringify({url:location.href})})`
- curl: `curl -X POST http://NAS_IP:8080/api/cast -H 'Content-Type: application/json' -d '{"url":"https://youtube.com/watch?v=VIDEO_ID"}'`
- iOS/Android Shortcut that sends the shared URL to the API

**Files:**

| File | Change |
|------|--------|
| `backend/api/routers/cast.py` | New: POST /api/cast, GET /api/cast/now-playing |
| `backend/api/main.py` | Register cast router |
| `shield-app/.../ui/BrowseFragment.kt` | Poll now-playing, auto-navigate |
| `backend/tests/test_cast.py` | New: tests |

---

## What This Does NOT Include

- DIAL protocol / Google Cast integration
- Dedicated phone app
- Queue management (single video, not a playlist)
