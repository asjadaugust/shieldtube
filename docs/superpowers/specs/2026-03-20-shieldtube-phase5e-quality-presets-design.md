# Phase 5e: Quality Presets — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft

---

## Goal

Let users choose video quality (resolution) before or during playback.

**Success criteria:** Click a video → quality picker appears (4K, 1080p, 720p) → video plays at selected quality.

---

## Design

### Backend

1. **Modify `resolve_stream()`** — Accept optional `quality` parameter. Map to yt-dlp format selector:
   - "4K_HDR": `bestvideo[vcodec=vp09.02][height<=2160]+bestaudio`
   - "4K": `bestvideo[height<=2160]+bestaudio`
   - "1080p": `bestvideo[height<=1080]+bestaudio`
   - "720p": `bestvideo[height<=720]+bestaudio`
   - "auto" (default): current HDR-first logic

2. **Modify stream endpoint** — Accept `?quality=1080p` query parameter, pass to DownloadManager/resolver.

3. **New endpoint: `GET /api/video/{id}/formats`** — Returns available formats from yt-dlp (resolution, codec, size estimate) so the Shield app can show options.

### Shield App

1. **Quality selection dialog** — Before playback (or via D-pad menu during playback), show available qualities. Default to "auto".
2. **PlaybackFragment.kt** — Pass selected quality to stream URL: `/api/video/{id}/stream?quality=1080p`.

**Files:**

| File | Change |
|------|--------|
| `backend/services/stream_resolver.py` | Add quality parameter to resolve_stream |
| `backend/services/download_manager.py` | Pass quality through to resolver |
| `backend/api/routers/video.py` | Add quality param to stream endpoint, add formats endpoint |
| `shield-app/.../player/PlaybackFragment.kt` | Quality selection UI |
| `shield-app/.../api/ShieldTubeApi.kt` | Add getFormats() |
| `shield-app/.../api/models.kt` | Add VideoFormat data class |
| `backend/tests/test_quality.py` | New: tests |
