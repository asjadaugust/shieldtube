# Phase 4a: SponsorBlock Integration — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft
**Source:** [ShieldTube PRD](../../ShieldTube_PRD.md) — Phase 4: Polish + P1 Features
**Depends on:** Phase 3b Shield Playback Enhancement (complete)

---

## Goal

Automatically skip sponsor segments, intros, and outros during video playback using community-sourced SponsorBlock data.

**Success criteria:** Play a video with known sponsor segments → playback automatically skips past them without user interaction. Brief toast notification confirms the skip.

---

## Components

3 components. Backend and Shield app are independent (connected via HTTP API) and can be built in parallel.

### Component 1: SponsorBlock API Client

**Purpose:** Fetch skip segments from the SponsorBlock community API and cache them locally.

**File:** `backend/services/sponsorblock.py`

**Behavior:**
- `async get_segments(video_id: str) -> list[dict]`
- Calls `https://sponsor.ajay.app/api/skipSegments?videoID={video_id}&categories=["sponsor","intro","outro"]`
- Returns list of `{"start": float, "end": float, "category": str}`
- Uses `httpx.AsyncClient` with 3-second timeout (don't block playback)
- If SponsorBlock returns 404 (no segments for this video): return empty list
- If SponsorBlock returns error or timeout: return empty list (graceful degradation)

**Caching:**
- New migration `003_sponsor_segments.sql`: adds `sponsor_segments_json TEXT` column to `videos` table
- After fetching segments, store as JSON string in `videos.sponsor_segments_json`
- On subsequent requests, check cache first. If `sponsor_segments_json` is not null, parse and return without hitting SponsorBlock API
- Cache empty lists too (as `"[]"`) to avoid re-fetching for videos with no segments
- No cache expiry in Phase 4a — segments rarely change. Cache can be invalidated manually or in a future phase.

### Component 2: SponsorBlock Endpoint

**Purpose:** Serve cached or freshly-fetched sponsor segments to the Shield app.

**Added to:** `backend/api/routers/video.py`

**Endpoint:** `GET /api/sponsorblock/{video_id}`

**Flow:**
1. Get DB connection, query `videos.sponsor_segments_json` for this video_id
2. If cached (not null): parse JSON, return immediately
3. If not cached: call `sponsorblock.get_segments(video_id)`, cache result, return
4. Response format:
```json
{
  "video_id": "dQw4w9WgXcQ",
  "segments": [
    {"start": 30.5, "end": 60.2, "category": "sponsor"},
    {"start": 180.0, "end": 195.5, "category": "intro"}
  ]
}
```

### Component 3: Shield App Auto-Skip

**Purpose:** Automatically skip past sponsor/intro/outro segments during playback.

**Modified files:**
- `shield-app/.../api/ShieldTubeApi.kt` — add `getSponsorSegments()`
- `shield-app/.../api/models.kt` — add `SponsorSegment`, `SponsorResponse`
- `shield-app/.../player/PlaybackFragment.kt` — add skip logic

**New data classes:**
```kotlin
data class SponsorSegment(
    val start: Double,
    val end: Double,
    val category: String
)

data class SponsorResponse(
    @SerializedName("video_id") val videoId: String,
    val segments: List<SponsorSegment>
)
```

**New API method:**
```kotlin
@GET("/api/sponsorblock/{videoId}")
suspend fun getSponsorSegments(@Path("videoId") videoId: String): SponsorResponse
```

**PlaybackFragment changes:**
- After player is prepared, fetch segments via `ApiClient.api.getSponsorSegments(videoId)` in a coroutine
- Store segments in a `List<SponsorSegment>` field
- Add a periodic position check (every 500ms via coroutine delay loop) that:
  - Gets current position in seconds: `player.currentPosition / 1000.0`
  - Checks if position falls within any segment's start..end range
  - If yes: seek to segment end, show toast "Skipped {category} ({duration}s)"
- Track which segments have been skipped (by index) to avoid re-skipping on the same segment
- Don't skip if user manually seeks into a segment — detect manual seek via `onPositionDiscontinuity` with reason `DISCONTINUITY_REASON_SEEK` and temporarily disable skip for that segment
- All API errors caught silently — if SponsorBlock data unavailable, playback continues normally

---

## New/Modified Files

### Backend

| File | Change |
|------|--------|
| `backend/services/sponsorblock.py` | New: SponsorBlock API client with caching |
| `backend/api/routers/video.py` | Add: GET /api/sponsorblock/{video_id} endpoint |
| `backend/db/migrations/003_sponsor_segments.sql` | New: add sponsor_segments_json column |
| `backend/tests/test_sponsorblock.py` | New: service + endpoint tests |

### Shield App

| File | Change |
|------|--------|
| `shield-app/.../api/ShieldTubeApi.kt` | Add: getSponsorSegments() |
| `shield-app/.../api/models.kt` | Add: SponsorSegment, SponsorResponse |
| `shield-app/.../player/PlaybackFragment.kt` | Add: segment fetch, skip logic, toast |
| `shield-app/.../api/ModelsTest.kt` | Add: SponsorSegment/Response deserialization tests |

---

## Migration

```sql
-- backend/db/migrations/003_sponsor_segments.sql
ALTER TABLE videos ADD COLUMN sponsor_segments_json TEXT;
```

---

## Parallel Workstream Strategy

```
Task 0: Migration (sequential)
        |
        +-- Workstream A: Backend (sponsorblock service + endpoint + tests)
        +-- Workstream B: Shield app (API + models + skip logic + tests)
```

Backend and Shield app touch entirely different files. The only shared contract is the JSON response format, which is defined in this spec.

---

## Testing Strategy

- **Backend service:** Mock httpx to return SponsorBlock API fixture. Test: segments parsed correctly, 404 returns empty list, timeout returns empty list, caching works (second call doesn't hit API).
- **Backend endpoint:** Integration test with mocked service. Test: returns cached segments, fetches on miss, correct JSON response format.
- **Shield models:** Gson deserialization tests for SponsorSegment and SponsorResponse.
- **Shield skip logic:** Manual test on device — play a video with known sponsors, verify auto-skip and toast.

---

## What This Phase Does NOT Include

- User-configurable skip categories (always sponsor + intro + outro)
- Skip segment UI overlay (no visual indicator on timeline)
- Manual segment submission to SponsorBlock
- Cache expiry/refresh for sponsor data
