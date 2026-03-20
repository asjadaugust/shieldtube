# Phase 3b: Shield Playback Enhancement — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft
**Source:** [ShieldTube PRD](../../ShieldTube_PRD.md) — Phase 3: Progressive Download
**Depends on:** Phase 3a Backend Progressive Download (complete)

---

## Goal

Shield app reports playback position every 10 seconds and resumes from last position on re-play. Backend is not modified.

**Success criteria:** Play a video for 2 minutes → leave → come back → playback resumes from the 2-minute mark.

---

## Changes

3 modifications to existing files. No new files.

### Change 1: Add API Methods

**File:** `shield-app/app/src/main/java/com/shieldtube/api/ShieldTubeApi.kt`

Add two new suspend functions:

```kotlin
@POST("/api/video/{videoId}/progress")
suspend fun reportProgress(
    @Path("videoId") videoId: String,
    @Body body: ProgressBody
)

@GET("/api/video/{videoId}/meta")
suspend fun getVideoMeta(@Path("videoId") videoId: String): VideoMeta
```

### Change 2: Add Data Classes

**File:** `shield-app/app/src/main/java/com/shieldtube/api/models.kt`

Add:

```kotlin
data class ProgressBody(
    @SerializedName("position_seconds") val positionSeconds: Int,
    val duration: Int
)

data class VideoMeta(
    val id: String,
    val title: String,
    @SerializedName("channel_name") val channelName: String,
    @SerializedName("channel_id") val channelId: String,
    val duration: Int?,
    @SerializedName("cache_status") val cacheStatus: String?,
    @SerializedName("last_position_seconds") val lastPositionSeconds: Int
)
```

### Change 3: Update PlaybackFragment

**File:** `shield-app/app/src/main/java/com/shieldtube/player/PlaybackFragment.kt`

**Resume from last position:**
- In `initPlayer()`, before `exoPlayer.prepare()`:
  - Call `ApiClient.api.getVideoMeta(videoId)` via `lifecycleScope.launch`
  - If `lastPositionSeconds > 0`: seek to that position after prepare completes
  - Use `exoPlayer.addListener` with `onPlaybackStateChanged` to detect `STATE_READY`, then seek
  - Wrap in try/catch — if meta call fails, just start from beginning (don't block playback)

**Report position every 10 seconds:**
- Add a `progressJob: Job?` field
- After player is prepared and playing, start a coroutine:
  ```kotlin
  progressJob = lifecycleScope.launch {
      while (isActive) {
          delay(10_000)
          player?.let { p ->
              if (p.isPlaying) {
                  try {
                      ApiClient.api.reportProgress(
                          videoId,
                          ProgressBody(
                              positionSeconds = (p.currentPosition / 1000).toInt(),
                              duration = (p.duration / 1000).toInt()
                          )
                      )
                  } catch (e: Exception) {
                      Log.w(TAG, "Failed to report progress: ${e.message}")
                  }
              }
          }
      }
  }
  ```

**Final report on stop:**
- In `releasePlayer()`, before `player?.release()`:
  - Send one final progress report (fire-and-forget via `lifecycleScope.launch`)
  - Cancel `progressJob`

**Error handling:**
- All API calls wrapped in try/catch
- Position reporting failures are logged but don't interrupt playback
- Meta fetch failure means playback starts from beginning (graceful degradation)

---

## Modified Files

| File | Change |
|------|--------|
| `shield-app/app/src/main/java/com/shieldtube/api/ShieldTubeApi.kt` | Add reportProgress, getVideoMeta |
| `shield-app/app/src/main/java/com/shieldtube/api/models.kt` | Add ProgressBody, VideoMeta |
| `shield-app/app/src/main/java/com/shieldtube/player/PlaybackFragment.kt` | Resume + periodic reporting + final report |

---

## Testing

- **Unit test:** Add `VideoMeta` and `ProgressBody` Gson deserialization tests to existing `ModelsTest.kt`
- **Manual on device:** Play video → leave → return → verify resume position. Check backend logs for progress POST requests every 10s.

---

## What This Phase Does NOT Include

- Download progress bar UI (Phase 4)
- Playback speed controls (Phase 5)
- Chapter markers in playback UI (Phase 4)
