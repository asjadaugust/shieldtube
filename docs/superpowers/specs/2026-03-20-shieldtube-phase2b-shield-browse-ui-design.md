# Phase 2b: Shield Browse UI — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft
**Source:** [ShieldTube PRD](../../ShieldTube_PRD.md) — Phase 2: Browse Experience
**Depends on:** Phase 2a Backend Browse API (complete)

---

## Goal

Transform the Shield app from a single-video player into a browsable YouTube frontend with Home feed, Subscriptions, Search (voice + text), and click-to-play. Backend is not modified in this phase.

**Success criteria:** Open app → see Home feed with real thumbnails → navigate to Subscriptions → search by voice → click any video → it plays.

---

## Architecture

```
┌─────────────────────────────────────────────┐
│  Shield App                                  │
│                                              │
│  MainActivity                                │
│    └─ BrowseFragment (Leanback)              │
│         ├─ Home row (GET /api/feed/home)     │
│         ├─ Subs row (GET /api/feed/subs)     │
│         └─ Header: Search → SearchFragment   │
│                                              │
│  SearchFragment (Leanback)                   │
│    └─ Voice + text → GET /api/search?q=      │
│    └─ Results as card grid                   │
│                                              │
│  PlaybackFragment (updated from Phase 1)     │
│    └─ Accepts video ID via Fragment args      │
│    └─ GET /api/video/{id}/stream             │
│                                              │
│  API Client (Retrofit + Gson)                │
│    └─ ShieldTubeApi interface                │
│    └─ Video, FeedResponse data classes       │
│                                              │
│  Glide image loading                         │
│    └─ Thumbnails from /api/video/{id}/thumb  │
└─────────────────────────────────────────────┘
```

---

## Components

5 components. Components 1 and 5 are independent of each other and can be built in parallel. Components 2-4 depend on 1 (API client).

### Component 1: Retrofit API Client

**Purpose:** Typed HTTP client for all backend API calls.

**Files:**
- `shield-app/app/src/main/java/com/shieldtube/api/ShieldTubeApi.kt` — Retrofit interface
- `shield-app/app/src/main/java/com/shieldtube/api/ApiClient.kt` — Retrofit singleton builder
- `shield-app/app/src/main/java/com/shieldtube/api/models.kt` — Data classes

**Retrofit interface:**

```kotlin
interface ShieldTubeApi {
    @GET("/api/feed/home")
    suspend fun getFeedHome(): FeedResponse

    @GET("/api/feed/subscriptions")
    suspend fun getFeedSubscriptions(): FeedResponse

    @GET("/api/search")
    suspend fun search(@Query("q") query: String): FeedResponse
}
```

**Data classes:**

```kotlin
data class Video(
    val id: String,
    val title: String,
    @SerializedName("channel_name") val channelName: String,
    @SerializedName("channel_id") val channelId: String,
    @SerializedName("view_count") val viewCount: Long?,
    val duration: Int?,
    @SerializedName("published_at") val publishedAt: String?,
    @SerializedName("thumbnail_url") val thumbnailUrl: String
)

data class FeedResponse(
    @SerializedName("feed_type") val feedType: String,
    val videos: List<Video>,
    @SerializedName("cached_at") val cachedAt: String?,
    @SerializedName("from_cache") val fromCache: Boolean
)
```

**ApiClient singleton:**

```kotlin
object ApiClient {
    private const val BASE_URL = "http://192.168.1.100:8080"

    val api: ShieldTubeApi by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ShieldTubeApi::class.java)
    }
}
```

**Design decisions:**
- `BASE_URL` is a constant for Phase 2b. Will be moved to `BuildConfig` field in Phase 4.
- Suspend functions for coroutine integration with Leanback's async patterns.
- `@SerializedName` maps snake_case backend JSON to camelCase Kotlin.

### Component 2: BrowseFragment

**Purpose:** Main browse screen with Leanback sidebar navigation and horizontal card rows.

**Files:**
- `shield-app/app/src/main/java/com/shieldtube/ui/BrowseFragment.kt` — Leanback BrowseSupportFragment

**Behavior:**
- Extends `BrowseSupportFragment`.
- Sets title to "ShieldTube", brand color to dark theme.
- Creates sidebar headers: "Home", "Subscriptions".
- On header selected: loads the corresponding feed via API, populates `ListRow` with video cards.
- Uses `ArrayObjectAdapter` with `ListRowPresenter` for rows.
- Each row contains an `ArrayObjectAdapter` with `CardPresenter` for individual cards.
- On item click: navigates to `PlaybackFragment` with the video ID as argument.
- On search icon click (or D-pad left to "Search" header): navigates to `SearchFragment`.
- Loads data asynchronously using `kotlinx.coroutines` (`lifecycleScope.launch`).
- Shows loading spinner while feeds load.
- Handles errors gracefully (shows toast or error row).

**Feed loading flow:**
1. Header selected → `lifecycleScope.launch { api.getFeedHome() }`
2. Response received → create `ArrayObjectAdapter` with `CardPresenter`
3. Map each `Video` to a card via `CardPresenter`
4. Wrap in `ListRow(HeaderItem("Popular"), adapter)` and add to rows adapter

### Component 3: CardPresenter

**Purpose:** Custom Leanback `Presenter` that renders enhanced `ImageCardView` with channel avatar overlay.

**Files:**
- `shield-app/app/src/main/java/com/shieldtube/ui/CardPresenter.kt` — Custom Presenter

**Card layout:**
- Thumbnail image loaded via Glide from `{BASE_URL}{video.thumbnailUrl}` (e.g., `http://192.168.1.100:8080/api/video/dQw4w9WgXcQ/thumbnail?res=maxres`)
- Duration badge: dark overlay in bottom-right corner of thumbnail (formatted as `M:SS` or `H:MM:SS`)
- Channel avatar placeholder: colored circle with first letter of channel name, overlaid on bottom-left of thumbnail
  - Color derived from hash of channel name (deterministic per channel)
  - Will be replaced with real channel avatars in Phase 4
- Below thumbnail: title (max 2 lines), view count
- Card dimensions: 313dp x 176dp thumbnail (16:9), standard Leanback card width

**Glide integration:**
- Load thumbnail URL into `ImageCardView.mainImageView`
- Placeholder: dark gray rectangle
- Error fallback: dark gray rectangle with video icon
- Disk cache strategy: `DiskCacheStrategy.ALL` (thumbnails rarely change)

**Duration formatting:**
- `formatDuration(seconds: Int): String` — converts 213 → "3:33", 3723 → "1:02:03"

**Channel avatar color:**
- `getChannelColor(channelName: String): Int` — hash channel name to one of 8 predefined colors

### Component 4: SearchFragment

**Purpose:** Voice and text search with results displayed as a card grid.

**Files:**
- `shield-app/app/src/main/java/com/shieldtube/ui/SearchFragment.kt` — Leanback SearchSupportFragment

**Behavior:**
- Extends `SearchSupportFragment`.
- Implements `SearchSupportFragment.SearchResultProvider`.
- On query text change (debounced 300ms): call `api.search(query)`.
- On voice query recognized: call `api.search(query)`.
- Display results in `ObjectAdapter` using `CardPresenter`.
- On result click: navigate to `PlaybackFragment` with video ID.
- Empty state: show "Search for videos" message.
- Loading state: show spinner while API responds.

**Voice search:**
- Leanback's `SearchSupportFragment` handles voice UI natively.
- Shield remote mic button triggers speech recognition.
- Recognized text is passed to `onQueryTextChange`.
- `SearchSupportFragment` delegates voice recognition to the system speech recognizer via `RecognizerIntent`, so `RECORD_AUDIO` permission is not needed.

### Component 5: PlaybackFragment Update

**Purpose:** Accept dynamic video ID instead of hardcoded constant.

**Files:**
- Modify: `shield-app/app/src/main/java/com/shieldtube/player/PlaybackFragment.kt`

**Changes:**
- Remove hardcoded `VIDEO_ID` constant.
- Accept video ID via Fragment arguments: `arguments?.getString("video_id")`.
- Construct stream URL dynamically: `"$BACKEND_HOST/api/video/$videoId/stream"`.
- Add companion object factory method: `fun newInstance(videoId: String): PlaybackFragment`.
- If no video ID provided, show error and return to browse.

---

## Navigation Map

```
App Launch
    │
    ▼
MainActivity
    │
    ▼
BrowseFragment (default: Home header selected)
    │
    ├─ D-pad up/down → scroll card rows
    ├─ D-pad left → sidebar headers
    │   ├─ "Home" → load /api/feed/home
    │   ├─ "Subscriptions" → load /api/feed/subscriptions
    │   └─ Search icon → SearchFragment
    ├─ Select video card → PlaybackFragment(videoId)
    │   └─ Back → BrowseFragment
    └─ Back → exit app

SearchFragment
    ├─ Type or speak query → /api/search?q=
    ├─ Select result → PlaybackFragment(videoId)
    │   └─ Back → SearchFragment
    └─ Back → BrowseFragment
```

---

## Modified Files

| File | Change |
|------|--------|
| `shield-app/app/build.gradle.kts` | Add Glide, Retrofit, Gson dependencies |
| `shield-app/app/src/main/AndroidManifest.xml` | No changes needed (voice uses system speech recognizer) |
| `shield-app/app/src/main/java/com/shieldtube/MainActivity.kt` | Launch BrowseFragment instead of PlaybackFragment |
| `shield-app/app/src/main/java/com/shieldtube/player/PlaybackFragment.kt` | Accept video ID via arguments |

## New Files

| File | Purpose |
|------|---------|
| `shield-app/app/src/main/java/com/shieldtube/api/ShieldTubeApi.kt` | Retrofit interface |
| `shield-app/app/src/main/java/com/shieldtube/api/ApiClient.kt` | Retrofit singleton |
| `shield-app/app/src/main/java/com/shieldtube/api/models.kt` | Video, FeedResponse data classes |
| `shield-app/app/src/main/java/com/shieldtube/ui/BrowseFragment.kt` | Leanback browse screen |
| `shield-app/app/src/main/java/com/shieldtube/ui/CardPresenter.kt` | Enhanced ImageCardView presenter |
| `shield-app/app/src/main/java/com/shieldtube/ui/SearchFragment.kt` | Voice + text search |

---

## New Dependencies

```kotlin
// Glide — image loading with disk cache
implementation("com.github.bumptech.glide:glide:4.16.0")

// Retrofit — typed HTTP client
implementation("com.squareup.retrofit2:retrofit:2.9.0")
implementation("com.squareup.retrofit2:converter-gson:2.9.0")

// Gson — JSON serialization
implementation("com.google.code.gson:gson:2.10.1")

// Coroutines — async API calls
implementation("org.jetbrains.kotlinx:kotlinx-coroutines-android:1.7.3")

// Lifecycle — lifecycleScope for coroutine launching in fragments
implementation("androidx.lifecycle:lifecycle-runtime-ktx:2.7.0")
```

---

## Testing Strategy

Android TV testing is primarily manual (requires Shield hardware or emulator):

- **API client:** Unit test with MockWebServer — verify request URLs, parse response JSON.
- **Data classes:** Unit test Gson deserialization of backend JSON fixtures.
- **CardPresenter:** Manual test on device — verify thumbnails load, duration formats correctly, avatar colors are deterministic.
- **BrowseFragment:** Manual test — verify headers navigate, rows populate, click launches playback.
- **SearchFragment:** Manual test — verify voice input works, results display, click launches playback.
- **PlaybackFragment:** Manual test — verify dynamic video ID works, back navigation returns to browse.

---

## Parallel Workstream Strategy

```
Task 0: Dependencies + manifest updates (sequential)
        │
        ├── Workstream A: API client + data classes (worktree)
        └── Workstream B: PlaybackFragment update (worktree)
                │
        Task 3: CardPresenter (sequential, needs API models)
        Task 4: BrowseFragment (sequential, needs CardPresenter)
        Task 5: SearchFragment (sequential, needs CardPresenter)
        Task 6: MainActivity update (sequential)
```

Components 1 (API client) and 5 (PlaybackFragment update) touch different files and can be parallel. Components 2-4 are sequential since BrowseFragment and SearchFragment both depend on CardPresenter, which depends on the API data models.

---

## What This Phase Does NOT Include

- Backend changes (Phase 2a is complete and sufficient)
- Channel avatar images (using letter placeholder, real avatars in Phase 4)
- Feed background refresh (Phase 4)
- Playback controls beyond basic play/pause (Phase 3)
- Watch history or resume position (Phase 3)
- Settings screen (Phase 4)
- Error retry UI (Phase 4 polish)
