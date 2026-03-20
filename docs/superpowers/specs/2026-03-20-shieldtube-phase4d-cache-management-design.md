# Phase 4d: Cache Management — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft
**Source:** [ShieldTube PRD](../../ShieldTube_PRD.md) — Phase 4: Polish + P1 Features
**Depends on:** Phase 3a Backend Progressive Download (complete)

---

## Goal

API endpoints to inspect cache disk usage and evict cached videos.

**Success criteria:** `GET /api/cache/status` returns total cache size and per-video breakdown. `DELETE /api/cache/{id}` removes a video from disk and resets DB status.

---

## Endpoints

### GET /api/cache/status

Scans `{CACHE_DIR}/videos/` directory. Joins with `videos` table for metadata.

**Response:**
```json
{
  "total_size_bytes": 5368709120,
  "total_size_human": "5.0 GB",
  "video_count": 12,
  "videos": [
    {
      "id": "dQw4w9WgXcQ",
      "title": "Never Gonna Give You Up",
      "file_size_bytes": 157286400,
      "file_size_human": "150.0 MB",
      "cache_status": "cached",
      "last_accessed": "2026-03-20T14:30:00Z"
    }
  ]
}
```

- Lists only videos with files on disk (not "none" or "error" status)
- Sorted by last_accessed descending (most recently watched first)
- `file_size_human` formatted as KB/MB/GB

### DELETE /api/cache/{video_id}

- Deletes `{CACHE_DIR}/videos/{video_id}.mp4` from disk
- Resets `videos.cache_status` to "none"
- Clears `videos.cached_video_path` to null
- Returns `{"status": "deleted", "video_id": "..."}` on success
- Returns 404 if video not cached or file doesn't exist

---

## New/Modified Files

| File | Change |
|------|--------|
| `backend/api/routers/cache.py` | New: GET /api/cache/status, DELETE /api/cache/{video_id} |
| `backend/api/main.py` | Register cache router |
| `backend/tests/test_cache_endpoints.py` | New: status + delete tests |

---

## Testing Strategy

- **Status endpoint:** Create tmp_path with fake video files, seed videos table, verify response includes correct sizes and metadata.
- **Delete endpoint:** Create a cached file, call DELETE, verify file removed from disk and DB status reset. Test 404 for non-existent video.

---

## What This Phase Does NOT Include

- Automatic LRU eviction (deferred)
- Cache size limit configuration
- Shield app or web dashboard UI
- Thumbnail cache management (only video files)
