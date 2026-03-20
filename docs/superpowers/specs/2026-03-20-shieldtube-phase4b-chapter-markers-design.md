# Phase 4b: Chapter Markers — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft
**Source:** [ShieldTube PRD](../../ShieldTube_PRD.md) — Phase 4: Polish + P1 Features
**Depends on:** Phase 3a Backend Progressive Download (complete)

---

## Goal

Display chapter markers during video playback so users can see the current chapter and jump between chapters using the D-pad.

**Success criteria:** Play a video with chapters → current chapter title shown as overlay → D-pad left/right long-press jumps between chapters.

---

## Components

3 components, all sequential (small scope, no parallelism needed).

### Component 1: Return Chapters from yt-dlp

**Purpose:** Extract chapter data during stream resolution and store it.

**Modified files:**
- `backend/services/stream_resolver.py` — add `chapters` to return dict
- `backend/db/migrations/004_chapters.sql` — add `chapters_json` column to videos

**Changes to resolve_stream():**

yt-dlp provides chapters in `info["chapters"]` as:
```python
[
    {"title": "Intro", "start_time": 0.0, "end_time": 150.0},
    {"title": "Main Topic", "start_time": 150.0, "end_time": 615.0},
    {"title": "Conclusion", "start_time": 615.0, "end_time": 720.0},
]
```

Add to the return dict:
```python
"chapters": info.get("chapters") or []
```

**Migration:**
```sql
ALTER TABLE videos ADD COLUMN chapters_json TEXT;
```

### Component 2: Chapters in Meta Endpoint

**Purpose:** Serve chapter data to the Shield app via the existing meta endpoint.

**Modified file:** `backend/api/routers/watch.py`

**Changes to `GET /api/video/{id}/meta`:**
- After loading the video from DB, include `chapters_json` in the response
- Parse the JSON string to a list and return as `chapters` field
- If chapters_json is null, return empty list

**Updated response:**
```json
{
  "id": "dQw4w9WgXcQ",
  "title": "Never Gonna Give You Up",
  "channel_name": "Rick Astley",
  "duration": 212,
  "cache_status": "cached",
  "last_position_seconds": 120,
  "chapters": [
    {"title": "Intro", "start_time": 0.0, "end_time": 150.0},
    {"title": "Main Topic", "start_time": 150.0, "end_time": 615.0}
  ]
}
```

**Chapter caching:** When the DownloadManager resolves a stream, it should store chapters_json in the videos table. Modify `download_manager.py` to save `stream_info["chapters"]` as JSON during `_start_download()`.

### Component 3: Shield App Chapter Display + Navigation

**Purpose:** Show current chapter title and enable chapter jumping during playback.

**Modified files:**
- `shield-app/.../api/models.kt` — add Chapter data class, add chapters to VideoMeta
- `shield-app/.../player/PlaybackFragment.kt` — chapter overlay + navigation

**New data class:**
```kotlin
data class Chapter(
    val title: String,
    @SerializedName("start_time") val startTime: Double,
    @SerializedName("end_time") val endTime: Double
)
```

**Update VideoMeta:**
```kotlin
data class VideoMeta(
    // ... existing fields ...
    val chapters: List<Chapter> = emptyList()
)
```

**PlaybackFragment changes:**

- Add `chapters: List<Chapter>` field, populated from meta endpoint (already fetched for resume position)
- Add `currentChapterIndex: Int` field tracking which chapter is active
- Add a chapter title overlay: a `TextView` positioned at the top of the PlayerView that shows the current chapter title. Fades in when chapter changes, fades out after 3 seconds.
- Add a 1-second polling coroutine (can share the skip-check loop or run separately) that detects chapter transitions by checking `player.currentPosition` against chapter start/end times. When chapter changes, update the overlay text and fade it in.
- **Chapter navigation:** Override `onKeyDown` in PlaybackFragment or add a key listener. On D-pad left long-press: seek to previous chapter's `start_time`. On D-pad right long-press: seek to next chapter's `start_time`. Regular D-pad left/right retains default seek behavior (10-second jump).

---

## Modified Files Summary

### Backend

| File | Change |
|------|--------|
| `backend/services/stream_resolver.py` | Add `chapters` to return dict |
| `backend/services/download_manager.py` | Store chapters_json during download |
| `backend/db/migrations/004_chapters.sql` | Add chapters_json column |
| `backend/api/routers/watch.py` | Add chapters to meta endpoint response |
| `backend/tests/test_sponsorblock.py` | (no change) |

### Shield App

| File | Change |
|------|--------|
| `shield-app/.../api/models.kt` | Add Chapter, update VideoMeta |
| `shield-app/.../player/PlaybackFragment.kt` | Chapter overlay, navigation |
| `shield-app/.../api/ModelsTest.kt` | Add Chapter deserialization test |

---

## Testing Strategy

- **Backend:** Test resolve_stream returns chapters field. Test meta endpoint includes chapters. Mock yt-dlp with chapters fixture.
- **Shield models:** Gson deserialization test for Chapter and updated VideoMeta with chapters.
- **Shield UI:** Manual test on device — play video with chapters, verify overlay and navigation.

---

## What This Phase Does NOT Include

- Chapter markers on the seek bar / timeline (requires custom ExoPlayer UI)
- Chapter list view / table of contents
- Editing or submitting chapters
