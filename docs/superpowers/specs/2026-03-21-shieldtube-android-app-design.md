# ShieldTube Android Phone App — V1 Design Spec

## Purpose

Replace the mobile PWA with a native Android app. The PWA suffers from unreliable video playback (service worker corruption, slow buffering), no background downloads, and a web-app feel. A native app with ExoPlayer, WorkManager, and Compose gives reliable playback, true background downloads (to phone storage), native cast, and a polished experience.

## V1 Scope

- Browse feeds (For You, Home, History)
- Search videos (YouTube API + yt-dlp fallback)
- Play videos (stream from backend, LAN auto-detect)
- Download to phone (offline viewing)
- Download to server (NAS queue)
- Cast to Shield TV
- SponsorBlock auto-skip
- NVIDIA dark theme (#121212 / #76B900)

**Not in V1:** Subtitles, chapters UI, swipe-to-rate training, watch later, recommendations settings, widgets, notifications.

## Tech Stack

| Component | Library | Purpose |
|-----------|---------|---------|
| UI | Jetpack Compose + Material 3 | Declarative UI with dark theme |
| Video | Media3 ExoPlayer | VP9/Opus/HDR, range requests, cast |
| Networking | Retrofit + OkHttp + Moshi | API calls, auth header interceptor |
| Background downloads | WorkManager | Phone downloads survive app kill |
| Local DB | Room | Download queue, watch history, feed cache |
| DI | Hilt | Dependency injection |
| Navigation | Compose Navigation | Screen routing |
| Image loading | Coil | Thumbnail loading with caching |
| Cast | MediaRouter + Cast SDK | Cast to Shield TV |

## Architecture

```
┌─────────────────────────────────────────────┐
│  UI Layer (Compose)                         │
│  HomeScreen · SearchScreen · PlayerScreen   │
│  DownloadsScreen · SettingsSheet            │
│                                             │
│  ViewModels (StateFlow)                     │
│  HomeVM · SearchVM · PlayerVM · DownloadsVM │
├─────────────────────────────────────────────┤
│  Domain Layer                               │
│  FeedRepository · VideoRepository           │
│  DownloadRepository · SettingsRepository    │
├─────────────────────────────────────────────┤
│  Data Layer                                 │
│  ShieldTubeApi (Retrofit)                   │
│  AppDatabase (Room)                         │
│  DownloadWorker (WorkManager)               │
│  LanDetector                                │
│  SponsorBlockApi                            │
└─────────────────────────────────────────────┘
```

**MVVM pattern:** Each screen has a ViewModel that exposes `StateFlow<UiState>`. The UI observes and reacts. No business logic in Composables.

## Screens

### 1. Home Screen

- Bottom navigation: Home, Search, Downloads, Settings
- Home tab has sub-tabs: For You, Home, History (horizontal chips)
- Pull-to-refresh on each feed
- Video cards: thumbnail (Coil), title, channel, duration badge, download icon overlay
- Tap card → navigate to Player
- Long-press card → bottom sheet (Play, Cast, Download to Phone, Download to Server)

### 2. Search Screen

- Search bar at top with keyboard auto-focus
- Results as vertical grid of video cards (same component as Home)
- Debounced search (300ms delay)
- Empty state: "Search YouTube"

### 3. Player Screen

- Full-screen ExoPlayer with system UI hidden
- Stream URL: `{streamBaseUrl}/api/video/{id}/stream`
- `streamBaseUrl` = LAN if available, tunnel otherwise
- Controls: play/pause, seek bar, 10s skip, fullscreen lock
- SponsorBlock: fetch segments from `/api/sponsorblock/{id}`, auto-skip with toast
- Cast button in top-right: sends video URL to Shield TV via `/api/cast`
- Reports playback progress every 10s to `/api/video/{id}/progress`
- On back press: confirm exit if video is playing

### 4. Downloads Screen

- Two sections with tabs: "On Phone" and "On Server"
- **On Phone:** videos downloaded to phone storage via WorkManager
  - Shows: thumbnail, title, channel, file size, progress bar (if downloading)
  - Tap to play (from local file, no network needed)
  - Swipe to delete
- **On Server:** videos cached on NAS (from `/api/download/library`)
  - Shows: thumbnail, title, channel, file size
  - Tap to stream (via LAN or tunnel)

### 5. Settings (Bottom Sheet)

- Backend URL + API Secret (setup)
- LAN URL (optional, for auto-detect)
- LAN status indicator (green dot = connected)
- Cache status (server disk usage from `/api/cache/status`)
- About / version

## Data Flow

### API Client

```kotlin
interface ShieldTubeApi {
    @GET("api/feed/{type}")
    suspend fun getFeed(@Path("type") type: String): FeedResponse

    @GET("api/search")
    suspend fun search(@Query("q") query: String): FeedResponse

    @GET("api/video/{id}/stream")
    suspend fun getStreamUrl(@Path("id") videoId: String): ResponseBody

    @GET("api/sponsorblock/{id}")
    suspend fun getSponsorSegments(@Path("id") videoId: String): SponsorResponse

    @POST("api/video/{id}/progress")
    suspend fun reportProgress(@Path("id") videoId: String, @Body body: ProgressBody): Unit

    @POST("api/download/enqueue")
    suspend fun enqueueServerDownload(@Body body: EnqueueBody): EnqueueResponse

    @GET("api/download/active")
    suspend fun getActiveDownloads(): ActiveDownloadsResponse

    @GET("api/download/library")
    suspend fun getDownloadLibrary(): LibraryResponse

    @POST("api/cast")
    suspend fun castToShield(@Body body: CastBody): Unit

    @GET("api/auth/status")
    suspend fun authStatus(): AuthStatusResponse
}
```

OkHttp interceptor adds `X-ShieldTube-Secret` header to all requests.

### LAN Auto-Detect

```kotlin
class LanDetector(private val lanUrl: String) {
    private val _isAvailable = MutableStateFlow(false)
    val isAvailable: StateFlow<Boolean> = _isAvailable

    suspend fun probe() {
        try {
            withTimeout(1000) {
                val resp = httpClient.get("$lanUrl/api/auth/status")
                _isAvailable.value = resp.isSuccessful
            }
        } catch {
            _isAvailable.value = false
        }
    }

    val streamBaseUrl: String
        get() = if (_isAvailable.value) lanUrl else tunnelUrl
}
```

Probed on app start and every 60 seconds.

### Phone Downloads (WorkManager)

```kotlin
class VideoDownloadWorker(ctx: Context, params: WorkerParameters) : CoroutineWorker(ctx, params) {
    override suspend fun doWork(): Result {
        val videoId = inputData.getString("video_id") ?: return Result.failure()
        val streamUrl = "$baseUrl/api/video/$videoId/stream"

        // Download to app-specific storage
        val file = File(context.getExternalFilesDir("videos"), "$videoId.mp4")
        httpClient.downloadToFile(streamUrl, file) { progress ->
            setProgress(workDataOf("percent" to progress))
        }

        // Update Room DB
        downloadDao.markComplete(videoId, file.absolutePath)
        return Result.success()
    }
}
```

- Uses `setForeground()` with notification for long downloads
- Progress reported via `setProgress()`, observed by UI via `WorkManager.getWorkInfoByIdFlow()`
- Downloads from LAN when available (fast), tunnel as fallback
- Files stored in `getExternalFilesDir("videos")` — app-private, no media scanner

### Room Database

```kotlin
@Entity
data class LocalDownload(
    @PrimaryKey val videoId: String,
    val title: String,
    val channelName: String,
    val duration: Int?,
    val filePath: String?,
    val fileSize: Long = 0,
    val status: String = "pending", // pending, downloading, complete, error
    val progress: Int = 0,
    val createdAt: Long = System.currentTimeMillis()
)

@Entity
data class CachedFeed(
    @PrimaryKey val feedType: String,
    val videosJson: String,
    val fetchedAt: Long
)
```

## Project Structure

```
shieldtube-phone/
├── app/
│   ├── src/main/java/com/shieldtube/phone/
│   │   ├── ShieldTubeApp.kt              # Application + Hilt
│   │   ├── MainActivity.kt               # Single activity
│   │   ├── di/
│   │   │   └── AppModule.kt              # Hilt providers
│   │   ├── data/
│   │   │   ├── api/
│   │   │   │   ├── ShieldTubeApi.kt      # Retrofit interface
│   │   │   │   ├── AuthInterceptor.kt    # X-ShieldTube-Secret
│   │   │   │   └── Models.kt            # API response models
│   │   │   ├── db/
│   │   │   │   ├── AppDatabase.kt        # Room DB
│   │   │   │   ├── DownloadDao.kt
│   │   │   │   └── FeedCacheDao.kt
│   │   │   └── repository/
│   │   │       ├── FeedRepository.kt
│   │   │       ├── VideoRepository.kt
│   │   │       └── DownloadRepository.kt
│   │   ├── service/
│   │   │   ├── LanDetector.kt
│   │   │   ├── VideoDownloadWorker.kt
│   │   │   └── SponsorBlockService.kt
│   │   └── ui/
│   │       ├── theme/
│   │       │   └── Theme.kt              # NVIDIA dark + green
│   │       ├── components/
│   │       │   ├── VideoCard.kt
│   │       │   ├── BottomSheet.kt
│   │       │   └── ProgressRing.kt
│   │       ├── home/
│   │       │   ├── HomeScreen.kt
│   │       │   └── HomeViewModel.kt
│   │       ├── search/
│   │       │   ├── SearchScreen.kt
│   │       │   └── SearchViewModel.kt
│   │       ├── player/
│   │       │   ├── PlayerScreen.kt
│   │       │   └── PlayerViewModel.kt
│   │       ├── downloads/
│   │       │   ├── DownloadsScreen.kt
│   │       │   └── DownloadsViewModel.kt
│   │       └── settings/
│   │           └── SettingsSheet.kt
│   ├── src/main/res/
│   │   ├── mipmap-*/ic_launcher.png      # Reuse existing shield icon
│   │   └── values/
│   │       ├── strings.xml
│   │       └── themes.xml
│   └── build.gradle.kts
├── gradle/
└── build.gradle.kts
```

## Theme

```kotlin
val NvidiaGreen = Color(0xFF76B900)
val DarkBackground = Color(0xFF121212)
val DarkSurface = Color(0xFF1E1E1E)
val DarkCard = Color(0xFF2A2A2A)

@Composable
fun ShieldTubeTheme(content: @Composable () -> Unit) {
    MaterialTheme(
        colorScheme = darkColorScheme(
            primary = NvidiaGreen,
            background = DarkBackground,
            surface = DarkSurface,
            onPrimary = DarkBackground,
            onBackground = Color.White,
            onSurface = Color.White,
        ),
        content = content
    )
}
```

## Backend Compatibility

The app uses the exact same API as the PWA — no backend changes needed. All endpoints are already built:

- `GET /api/feed/{home|recommended|history}` — feeds
- `GET /api/search?q=` — search (with yt-dlp fallback)
- `GET /api/video/{id}/stream` — video streaming with range support
- `GET /api/video/{id}/thumbnail` — thumbnails (exempt from auth)
- `GET /api/sponsorblock/{id}` — sponsor segments
- `POST /api/video/{id}/progress` — playback progress
- `POST /api/download/enqueue` — server download queue
- `GET /api/download/active` — active downloads
- `GET /api/download/library` — cached videos on server
- `POST /api/cast` — cast to Shield TV
- `GET /api/auth/status` — auth check
- `GET /api/cache/status` — server cache usage

## Testing Strategy

- **Unit tests:** ViewModels with fake repositories, Repository with mock API
- **UI tests:** Compose test rules for each screen
- **Manual:** Install on phone, test LAN vs tunnel playback, background downloads, cast
