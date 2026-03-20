# Phase 5b: Subtitle/CC Support — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft

---

## Goal

Display subtitles/closed captions during video playback with language selection.

**Success criteria:** Play a video with subtitles → captions render on screen → user can switch language.

---

## Design

### Backend

1. **Modify `resolve_stream()`** — Extract subtitle tracks from yt-dlp: `info.get("subtitles", {})` and `info.get("automatic_captions", {})`. Return available languages with download URLs.

2. **New endpoint: `GET /api/video/{id}/subtitles`** — Returns list of available subtitle languages with URLs. Optionally downloads and caches subtitle files (WebVTT format).

3. **Subtitle caching** — Download subtitles to `{CACHE_DIR}/subtitles/{video_id}_{lang}.vtt`. Serve via `GET /api/video/{id}/subtitles/{lang}`.

### Shield App

1. **PlaybackFragment.kt** — Add subtitle track selection:
   - Fetch available subtitles from `/api/video/{id}/subtitles`
   - ExoPlayer supports `MergingMediaSource` to add subtitle tracks
   - Add `SingleSampleMediaSource` for each subtitle WebVTT URL
   - Add UI to select subtitle track (D-pad menu or long-press action)
   - Use ExoPlayer's built-in `SubtitleView` for rendering

**Files:**

| File | Change |
|------|--------|
| `backend/services/stream_resolver.py` | Return subtitle info from yt-dlp |
| `backend/services/subtitle_cache.py` | New: download + cache subtitle files |
| `backend/api/routers/video.py` | Add subtitle list + serve endpoints |
| `shield-app/.../api/ShieldTubeApi.kt` | Add getSubtitles() |
| `shield-app/.../api/models.kt` | Add SubtitleTrack data class |
| `shield-app/.../player/PlaybackFragment.kt` | Add subtitle selection + rendering |
| `backend/tests/test_subtitles.py` | New: tests |
