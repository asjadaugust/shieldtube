# Phase 2b: Shield Browse UI — Implementation Plan

> **For agentic workers:** This plan uses Ralph Loop methodology with parallel sub-agents in git worktrees. Use `superpowers:dispatching-parallel-agents` to run Workstreams A and B concurrently. Each agent iterates toward its completion promise. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Transform the Shield app into a browsable YouTube frontend with Home feed, Subscriptions, voice + text search, and click-to-play.

**Architecture:** Leanback BrowseSupportFragment with sidebar headers → Retrofit API client calls backend → Glide loads thumbnails → CardPresenter renders enhanced ImageCardView with channel avatar → click navigates to PlaybackFragment with dynamic video ID.

**Tech Stack:** Kotlin, Leanback 1.0.0, ExoPlayer/Media3 1.2.1, Glide 4.16.0, Retrofit 2.9.0, Gson, Coroutines

---

## Execution Model

```
Task 0: Dependencies update (sequential)
        │
        ├── Workstream A: API client + models (worktree)
        └── Workstream B: PlaybackFragment update (worktree)
                │
        Task 3: CardPresenter (sequential)
        Task 4: BrowseFragment (sequential)
        Task 5: SearchFragment (sequential)
        Task 6: MainActivity update + wiring (sequential)
```

**Note:** This is a Kotlin Android project. No Android SDK or emulator available in CI agents. Agents write code and verify structure; `./gradlew build` verification requires the actual device environment. Unit tests for API client/models can run with JUnit + MockWebServer.

---

## File Structure

### New Files

| File | Responsibility |
|------|---------------|
| `shield-app/app/src/main/java/com/shieldtube/api/ShieldTubeApi.kt` | Retrofit interface: getFeedHome, getFeedSubscriptions, search |
| `shield-app/app/src/main/java/com/shieldtube/api/ApiClient.kt` | Retrofit singleton with BASE_URL |
| `shield-app/app/src/main/java/com/shieldtube/api/models.kt` | Video, FeedResponse data classes |
| `shield-app/app/src/main/java/com/shieldtube/ui/CardPresenter.kt` | Enhanced ImageCardView with Glide, duration badge, channel avatar |
| `shield-app/app/src/main/java/com/shieldtube/ui/BrowseFragment.kt` | Leanback BrowseSupportFragment with Home/Subscriptions headers |
| `shield-app/app/src/main/java/com/shieldtube/ui/SearchFragment.kt` | Leanback SearchSupportFragment with voice + text |
| `shield-app/app/src/test/java/com/shieldtube/api/ModelsTest.kt` | Unit test: Gson deserialization of backend JSON |
| `shield-app/app/src/test/java/com/shieldtube/ui/CardPresenterTest.kt` | Unit test: duration formatting, channel color |

### Modified Files

| File | Changes |
|------|---------|
| `shield-app/app/build.gradle.kts` | Add Glide, Retrofit, Gson, Coroutines, Lifecycle deps |
| `shield-app/app/src/main/java/com/shieldtube/MainActivity.kt` | Launch BrowseFragment instead of PlaybackFragment |
| `shield-app/app/src/main/java/com/shieldtube/player/PlaybackFragment.kt` | Accept video ID via arguments, dynamic stream URL |

---

## Task 0: Dependencies Update (Sequential)

**Files:**
- Modify: `shield-app/app/build.gradle.kts`

- [ ] **Step 1: Add new dependencies to build.gradle.kts**

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.shieldtube"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.shieldtube"
        minSdk = 31
        targetSdk = 34
        versionCode = 1
        versionName = "0.2.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = false
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("androidx.core:core-ktx:1.12.0")
    implementation("androidx.leanback:leanback:1.0.0")

    // Media3 ExoPlayer
    implementation("androidx.media3:media3-exoplayer:1.2.1")
    implementation("androidx.media3:media3-ui:1.2.1")

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

    testImplementation("junit:junit:4.13.2")
}
```

- [ ] **Step 2: Commit**

```bash
git add shield-app/app/build.gradle.kts
git commit -m "chore: add Glide, Retrofit, Gson, Coroutines deps for Phase 2b"
```

---

## Workstream A: API Client + Models (Parallel — Worktree)

**Isolation:** Git worktree branched from Task 0 commit
**Completion Promise:** `API CLIENT COMPLETE`

### Agent Dispatch Prompt

```markdown
You are implementing the Retrofit API client and data models for ShieldTube Phase 2b.

**Read these files first:**
- `shield-app/app/build.gradle.kts` — dependencies (Retrofit, Gson already added)
- `shield-app/app/src/main/java/com/shieldtube/player/PlaybackFragment.kt` — existing code, has BACKEND_HOST constant

**What to build:**

1. `shield-app/app/src/main/java/com/shieldtube/api/models.kt`:

```kotlin
package com.shieldtube.api

import com.google.gson.annotations.SerializedName

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

2. `shield-app/app/src/main/java/com/shieldtube/api/ShieldTubeApi.kt`:

```kotlin
package com.shieldtube.api

import retrofit2.http.GET
import retrofit2.http.Query

interface ShieldTubeApi {
    @GET("/api/feed/home")
    suspend fun getFeedHome(): FeedResponse

    @GET("/api/feed/subscriptions")
    suspend fun getFeedSubscriptions(): FeedResponse

    @GET("/api/search")
    suspend fun search(@Query("q") query: String): FeedResponse
}
```

3. `shield-app/app/src/main/java/com/shieldtube/api/ApiClient.kt`:

```kotlin
package com.shieldtube.api

import retrofit2.Retrofit
import retrofit2.converter.gson.GsonConverterFactory

object ApiClient {
    const val BASE_URL = "http://192.168.1.100:8080"

    val api: ShieldTubeApi by lazy {
        Retrofit.Builder()
            .baseUrl(BASE_URL)
            .addConverterFactory(GsonConverterFactory.create())
            .build()
            .create(ShieldTubeApi::class.java)
    }
}
```

4. `shield-app/app/src/test/java/com/shieldtube/api/ModelsTest.kt` — Unit test:

```kotlin
package com.shieldtube.api

import com.google.gson.Gson
import org.junit.Assert.*
import org.junit.Test

class ModelsTest {
    private val gson = Gson()

    @Test
    fun `deserialize Video from backend JSON`() {
        val json = """
        {
            "id": "dQw4w9WgXcQ",
            "title": "Never Gonna Give You Up",
            "channel_name": "Rick Astley",
            "channel_id": "UCuAXFkgsw1L7xaCfnd5JJOw",
            "view_count": 1500000000,
            "duration": 212,
            "published_at": "2009-10-25T06:57:33Z",
            "thumbnail_url": "/api/video/dQw4w9WgXcQ/thumbnail?res=maxres"
        }
        """.trimIndent()

        val video = gson.fromJson(json, Video::class.java)

        assertEquals("dQw4w9WgXcQ", video.id)
        assertEquals("Never Gonna Give You Up", video.title)
        assertEquals("Rick Astley", video.channelName)
        assertEquals("UCuAXFkgsw1L7xaCfnd5JJOw", video.channelId)
        assertEquals(1500000000L, video.viewCount)
        assertEquals(212, video.duration)
        assertEquals("/api/video/dQw4w9WgXcQ/thumbnail?res=maxres", video.thumbnailUrl)
    }

    @Test
    fun `deserialize FeedResponse from backend JSON`() {
        val json = """
        {
            "feed_type": "home",
            "videos": [],
            "cached_at": "2026-03-20T14:30:00Z",
            "from_cache": true
        }
        """.trimIndent()

        val response = gson.fromJson(json, FeedResponse::class.java)

        assertEquals("home", response.feedType)
        assertTrue(response.videos.isEmpty())
        assertEquals("2026-03-20T14:30:00Z", response.cachedAt)
        assertTrue(response.fromCache)
    }

    @Test
    fun `Video handles null optional fields`() {
        val json = """
        {
            "id": "test",
            "title": "Test",
            "channel_name": "Ch",
            "channel_id": "UC",
            "view_count": null,
            "duration": null,
            "published_at": null,
            "thumbnail_url": "/thumb"
        }
        """.trimIndent()

        val video = gson.fromJson(json, Video::class.java)
        assertNull(video.viewCount)
        assertNull(video.duration)
        assertNull(video.publishedAt)
    }
}
```

**Important:** Create the test directory if it doesn't exist:
`mkdir -p shield-app/app/src/test/java/com/shieldtube/api`

**Success criteria:**
- All 3 API files created with correct package declarations
- All 3 unit tests written and syntactically correct
- Imports are correct (Retrofit, Gson annotations)
- Commit after models+api, then after tests

Output <promise>API CLIENT COMPLETE</promise> when done.
```

---

## Workstream B: PlaybackFragment Update (Parallel — Worktree)

**Isolation:** Git worktree branched from Task 0 commit
**Completion Promise:** `PLAYBACK UPDATE COMPLETE`

### Agent Dispatch Prompt

```markdown
You are updating PlaybackFragment for ShieldTube Phase 2b to accept dynamic video IDs.

**Read this file:**
- `shield-app/app/src/main/java/com/shieldtube/player/PlaybackFragment.kt` — current implementation with hardcoded VIDEO_ID

**What to change:**

Update `PlaybackFragment.kt` to:

1. Remove the hardcoded `VIDEO_ID` constant from companion object
2. Keep `BACKEND_HOST` constant
3. Add a factory method `newInstance(videoId: String)` that creates the fragment with arguments
4. Read video ID from arguments in `initPlayer()`
5. Construct stream URL dynamically
6. Handle missing video ID gracefully (log error, don't crash)

**Updated file:**

```kotlin
package com.shieldtube.player

import android.net.Uri
import android.os.Bundle
import android.util.Log
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import androidx.fragment.app.Fragment
import androidx.media3.common.MediaItem
import androidx.media3.exoplayer.DefaultRenderersFactory
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.ui.PlayerView

class PlaybackFragment : Fragment() {

    companion object {
        const val BACKEND_HOST = "http://192.168.1.100:8080"
        private const val ARG_VIDEO_ID = "video_id"
        private const val TAG = "PlaybackFragment"

        fun newInstance(videoId: String): PlaybackFragment {
            return PlaybackFragment().apply {
                arguments = Bundle().apply {
                    putString(ARG_VIDEO_ID, videoId)
                }
            }
        }
    }

    private var player: ExoPlayer? = null
    private var playerView: PlayerView? = null

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        playerView = PlayerView(requireContext()).apply {
            layoutParams = ViewGroup.LayoutParams(
                ViewGroup.LayoutParams.MATCH_PARENT,
                ViewGroup.LayoutParams.MATCH_PARENT
            )
        }
        return playerView!!
    }

    override fun onStart() {
        super.onStart()
        initPlayer()
    }

    override fun onStop() {
        super.onStop()
        releasePlayer()
    }

    private fun initPlayer() {
        val videoId = arguments?.getString(ARG_VIDEO_ID)
        if (videoId == null) {
            Log.e(TAG, "No video ID provided")
            parentFragmentManager.popBackStack()
            return
        }

        val renderersFactory = DefaultRenderersFactory(requireContext())
            .setExtensionRendererMode(DefaultRenderersFactory.EXTENSION_RENDERER_MODE_ON)

        player = ExoPlayer.Builder(requireContext(), renderersFactory)
            .build()
            .also { exoPlayer ->
                playerView?.player = exoPlayer

                val streamUrl = "$BACKEND_HOST/api/video/$videoId/stream"
                val mediaItem = MediaItem.fromUri(Uri.parse(streamUrl))
                exoPlayer.setMediaItem(mediaItem)
                exoPlayer.playWhenReady = true
                exoPlayer.prepare()
            }
    }

    private fun releasePlayer() {
        player?.release()
        player = null
    }
}
```

**Success criteria:**
- `newInstance(videoId)` factory method exists
- Video ID read from arguments, not hardcoded
- Missing video ID pops back stack instead of crashing
- BACKEND_HOST constant preserved

Commit: `git commit -m "feat: update PlaybackFragment to accept dynamic video ID"`

Output <promise>PLAYBACK UPDATE COMPLETE</promise> when done.
```

---

## Task 3: CardPresenter (Sequential — After Workstreams A+B)

**Depends on:** Workstream A merged (needs Video data class)
**Files:**
- Create: `shield-app/app/src/main/java/com/shieldtube/ui/CardPresenter.kt`
- Create: `shield-app/app/src/test/java/com/shieldtube/ui/CardPresenterTest.kt`

- [ ] **Step 1: Create CardPresenter**

```kotlin
// shield-app/app/src/main/java/com/shieldtube/ui/CardPresenter.kt
package com.shieldtube.ui

import android.graphics.Color
import android.graphics.drawable.GradientDrawable
import android.view.Gravity
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.TextView
import androidx.core.content.ContextCompat
import androidx.leanback.widget.ImageCardView
import androidx.leanback.widget.Presenter
import com.bumptech.glide.Glide
import com.bumptech.glide.load.engine.DiskCacheStrategy
import com.shieldtube.api.ApiClient
import com.shieldtube.api.Video

class CardPresenter : Presenter() {

    companion object {
        private const val CARD_WIDTH = 313
        private const val CARD_HEIGHT = 176

        private val CHANNEL_COLORS = intArrayOf(
            0xFFE53935.toInt(), 0xFF8E24AA.toInt(), 0xFF3949AB.toInt(), 0xFF039BE5.toInt(),
            0xFF00897B.toInt(), 0xFF7CB342.toInt(), 0xFFFB8C00.toInt(), 0xFF6D4C41.toInt()
        )

        fun formatDuration(seconds: Int?): String {
            if (seconds == null || seconds <= 0) return ""
            val h = seconds / 3600
            val m = (seconds % 3600) / 60
            val s = seconds % 60
            return if (h > 0) String.format("%d:%02d:%02d", h, m, s)
            else String.format("%d:%02d", m, s)
        }

        fun getChannelColor(channelName: String): Int {
            val index = (channelName.hashCode() and 0x7FFFFFFF) % CHANNEL_COLORS.size
            return CHANNEL_COLORS[index]
        }
    }

    override fun onCreateViewHolder(parent: ViewGroup): ViewHolder {
        val cardView = ImageCardView(parent.context).apply {
            isFocusable = true
            isFocusableInTouchMode = true
            setMainImageDimensions(
                dpToPx(parent, CARD_WIDTH),
                dpToPx(parent, CARD_HEIGHT)
            )
        }
        return ViewHolder(cardView)
    }

    override fun onBindViewHolder(viewHolder: ViewHolder, item: Any) {
        val video = item as Video
        val cardView = viewHolder.view as ImageCardView
        val context = cardView.context

        cardView.titleText = video.title
        cardView.contentText = formatViewCount(video.viewCount)

        // Load thumbnail via Glide
        val thumbnailUrl = "${ApiClient.BASE_URL}${video.thumbnailUrl}"
        Glide.with(context)
            .load(thumbnailUrl)
            .diskCacheStrategy(DiskCacheStrategy.ALL)
            .centerCrop()
            .placeholder(android.R.color.darker_gray)
            .error(android.R.color.darker_gray)
            .into(cardView.mainImageView)

        // Add overlays to the main image container
        val imageContainer = cardView.mainImageView.parent as? FrameLayout ?: return

        // Remove previous overlays (in case of view recycling)
        while (imageContainer.childCount > 1) {
            imageContainer.removeViewAt(imageContainer.childCount - 1)
        }

        // Duration badge (bottom-right)
        val durationText = formatDuration(video.duration)
        if (durationText.isNotEmpty()) {
            val badge = TextView(context).apply {
                text = durationText
                setTextColor(Color.WHITE)
                textSize = 11f
                setBackgroundColor(Color.parseColor("#CC000000"))
                setPadding(6, 2, 6, 2)
                layoutParams = FrameLayout.LayoutParams(
                    FrameLayout.LayoutParams.WRAP_CONTENT,
                    FrameLayout.LayoutParams.WRAP_CONTENT,
                    Gravity.BOTTOM or Gravity.END
                ).apply { setMargins(0, 0, 8, 8) }
            }
            imageContainer.addView(badge)
        }

        // Channel avatar placeholder (bottom-left)
        val avatarSize = dpToPx(cardView, 24)
        val avatar = TextView(context).apply {
            text = video.channelName.firstOrNull()?.uppercase() ?: "?"
            setTextColor(Color.WHITE)
            textSize = 11f
            gravity = Gravity.CENTER
            val bg = GradientDrawable().apply {
                shape = GradientDrawable.OVAL
                setColor(getChannelColor(video.channelName))
            }
            background = bg
            layoutParams = FrameLayout.LayoutParams(avatarSize, avatarSize, Gravity.BOTTOM or Gravity.START)
                .apply { setMargins(8, 0, 0, 8) }
        }
        imageContainer.addView(avatar)
    }

    override fun onUnbindViewHolder(viewHolder: ViewHolder) {
        val cardView = viewHolder.view as ImageCardView
        cardView.mainImage = null
    }

    private fun formatViewCount(count: Long?): String {
        if (count == null) return ""
        return when {
            count >= 1_000_000_000 -> String.format("%.1fB views", count / 1_000_000_000.0)
            count >= 1_000_000 -> String.format("%.1fM views", count / 1_000_000.0)
            count >= 1_000 -> String.format("%.1fK views", count / 1_000.0)
            else -> "$count views"
        }
    }

    private fun dpToPx(view: ViewGroup, dp: Int): Int {
        return (dp * view.context.resources.displayMetrics.density).toInt()
    }

    private fun dpToPx(view: ImageCardView, dp: Int): Int {
        return (dp * view.context.resources.displayMetrics.density).toInt()
    }
}
```

- [ ] **Step 2: Create unit test for pure functions**

```kotlin
// shield-app/app/src/test/java/com/shieldtube/ui/CardPresenterTest.kt
package com.shieldtube.ui

import org.junit.Assert.*
import org.junit.Test

class CardPresenterTest {

    @Test
    fun `formatDuration short video`() {
        assertEquals("3:33", CardPresenter.formatDuration(213))
    }

    @Test
    fun `formatDuration long video`() {
        assertEquals("1:02:03", CardPresenter.formatDuration(3723))
    }

    @Test
    fun `formatDuration seconds only`() {
        assertEquals("0:30", CardPresenter.formatDuration(30))
    }

    @Test
    fun `formatDuration null returns empty`() {
        assertEquals("", CardPresenter.formatDuration(null))
    }

    @Test
    fun `formatDuration zero returns empty`() {
        assertEquals("", CardPresenter.formatDuration(0))
    }

    @Test
    fun `getChannelColor is deterministic`() {
        val color1 = CardPresenter.getChannelColor("Rick Astley")
        val color2 = CardPresenter.getChannelColor("Rick Astley")
        assertEquals(color1, color2)
    }

    @Test
    fun `getChannelColor varies by name`() {
        val color1 = CardPresenter.getChannelColor("Rick Astley")
        val color2 = CardPresenter.getChannelColor("PewDiePie")
        // Different names should (usually) produce different colors
        // This isn't guaranteed but is very likely with different hash codes
        assertNotEquals(color1, color2)
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add shield-app/app/src/main/java/com/shieldtube/ui/CardPresenter.kt shield-app/app/src/test/java/com/shieldtube/ui/
git commit -m "feat: add CardPresenter with Glide thumbnails, duration badge, channel avatar"
```

---

## Task 4: BrowseFragment (Sequential)

**Depends on:** Task 3 (CardPresenter)
**Files:**
- Create: `shield-app/app/src/main/java/com/shieldtube/ui/BrowseFragment.kt`

- [ ] **Step 1: Create BrowseFragment**

```kotlin
// shield-app/app/src/main/java/com/shieldtube/ui/BrowseFragment.kt
package com.shieldtube.ui

import android.os.Bundle
import android.widget.Toast
import androidx.leanback.app.BrowseSupportFragment
import androidx.leanback.widget.*
import androidx.lifecycle.lifecycleScope
import com.shieldtube.api.ApiClient
import com.shieldtube.api.FeedResponse
import com.shieldtube.api.Video
import com.shieldtube.player.PlaybackFragment
import kotlinx.coroutines.launch

class BrowseFragment : BrowseSupportFragment() {

    companion object {
        private const val HEADER_HOME = 0L
        private const val HEADER_SUBSCRIPTIONS = 1L
    }

    private val rowsAdapter = ArrayObjectAdapter(ListRowPresenter())
    private var currentHeader = HEADER_HOME

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setupUIElements()
        setupHeaders()
        setupEventListeners()
        adapter = rowsAdapter
        loadFeedForHeader(HEADER_HOME)
    }

    private fun setupUIElements() {
        title = "ShieldTube"
        headersState = HEADERS_ENABLED
        isHeadersTransitionOnBackEnabled = true
        brandColor = 0xFF1a1a2e.toInt()
        searchAffordanceColor = 0xFFe94560.toInt()
    }

    private fun setupHeaders() {
        // Create empty rows with headers — content loaded on header selection
        val cardPresenter = CardPresenter()
        val homeAdapter = ArrayObjectAdapter(cardPresenter)
        rowsAdapter.add(ListRow(HeaderItem(HEADER_HOME, "Home"), homeAdapter))

        val subsAdapter = ArrayObjectAdapter(cardPresenter)
        rowsAdapter.add(ListRow(HeaderItem(HEADER_SUBSCRIPTIONS, "Subscriptions"), subsAdapter))
    }

    private fun setupEventListeners() {
        setOnSearchClickedListener {
            requireActivity().supportFragmentManager.beginTransaction()
                .replace(android.R.id.content, SearchFragment())
                .addToBackStack("search")
                .commit()
        }

        onItemViewClickedListener = OnItemViewClickedListener { _, item, _, _ ->
            if (item is Video) {
                requireActivity().supportFragmentManager.beginTransaction()
                    .replace(android.R.id.content, PlaybackFragment.newInstance(item.id))
                    .addToBackStack("playback")
                    .commit()
            }
        }

        setOnItemViewSelectedListener { _, _, _, row ->
            if (row is ListRow) {
                val headerId = row.headerItem.id
                if (headerId != currentHeader) {
                    currentHeader = headerId
                    loadFeedForHeader(headerId)
                }
            }
        }
    }

    private fun loadFeedForHeader(headerId: Long) {
        lifecycleScope.launch {
            try {
                val response = when (headerId) {
                    HEADER_HOME -> ApiClient.api.getFeedHome()
                    HEADER_SUBSCRIPTIONS -> ApiClient.api.getFeedSubscriptions()
                    else -> return@launch
                }
                updateRowContent(headerId, response)
            } catch (e: Exception) {
                val name = if (headerId == HEADER_HOME) "Home" else "Subscriptions"
                showError("Failed to load $name: ${e.message}")
            }
        }
    }

    private fun updateRowContent(headerId: Long, response: FeedResponse) {
        // Find the row matching this header and replace its content
        for (i in 0 until rowsAdapter.size()) {
            val row = rowsAdapter.get(i) as? ListRow ?: continue
            if (row.headerItem.id == headerId) {
                val cardAdapter = row.adapter as ArrayObjectAdapter
                cardAdapter.clear()
                response.videos.forEach { cardAdapter.add(it) }
                break
            }
        }
    }

    private fun showError(message: String) {
        Toast.makeText(requireContext(), message, Toast.LENGTH_LONG).show()
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add shield-app/app/src/main/java/com/shieldtube/ui/BrowseFragment.kt
git commit -m "feat: add BrowseFragment with Home/Subscriptions feed loading"
```

---

## Task 5: SearchFragment (Sequential)

**Depends on:** Task 3 (CardPresenter)
**Files:**
- Create: `shield-app/app/src/main/java/com/shieldtube/ui/SearchFragment.kt`

- [ ] **Step 1: Create SearchFragment**

```kotlin
// shield-app/app/src/main/java/com/shieldtube/ui/SearchFragment.kt
package com.shieldtube.ui

import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.widget.Toast
import androidx.leanback.app.SearchSupportFragment
import androidx.leanback.widget.*
import androidx.lifecycle.lifecycleScope
import com.shieldtube.api.ApiClient
import com.shieldtube.api.Video
import com.shieldtube.player.PlaybackFragment
import kotlinx.coroutines.Job
import kotlinx.coroutines.launch

class SearchFragment : SearchSupportFragment(), SearchSupportFragment.SearchResultProvider {

    private val rowsAdapter = ArrayObjectAdapter(ListRowPresenter())
    private val handler = Handler(Looper.getMainLooper())
    private var searchJob: Job? = null
    private var pendingQuery: String? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        setSearchResultProvider(this)
        setOnItemViewClickedListener { _, item, _, _ ->
            if (item is Video) {
                requireActivity().supportFragmentManager.beginTransaction()
                    .replace(android.R.id.content, PlaybackFragment.newInstance(item.id))
                    .addToBackStack("playback")
                    .commit()
            }
        }
    }

    override fun getResultsAdapter(): ObjectAdapter = rowsAdapter

    override fun onQueryTextChange(newQuery: String): Boolean {
        // Debounce: wait 300ms after last keystroke
        handler.removeCallbacksAndMessages(null)
        if (newQuery.isNotBlank()) {
            handler.postDelayed({ performSearch(newQuery) }, 300)
        } else {
            rowsAdapter.clear()
        }
        return true
    }

    override fun onQueryTextSubmit(query: String): Boolean {
        handler.removeCallbacksAndMessages(null)
        if (query.isNotBlank()) {
            performSearch(query)
        }
        return true
    }

    private fun performSearch(query: String) {
        searchJob?.cancel()
        searchJob = lifecycleScope.launch {
            try {
                val response = ApiClient.api.search(query)
                rowsAdapter.clear()
                if (response.videos.isNotEmpty()) {
                    val cardPresenter = CardPresenter()
                    val listRowAdapter = ArrayObjectAdapter(cardPresenter)
                    response.videos.forEach { listRowAdapter.add(it) }
                    val header = HeaderItem(0, "Results for \"$query\"")
                    rowsAdapter.add(ListRow(header, listRowAdapter))
                }
            } catch (e: Exception) {
                Toast.makeText(requireContext(), "Search failed: ${e.message}", Toast.LENGTH_SHORT).show()
            }
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add shield-app/app/src/main/java/com/shieldtube/ui/SearchFragment.kt
git commit -m "feat: add SearchFragment with voice and text input"
```

---

## Task 6: MainActivity Update + Wiring (Sequential)

**Depends on:** Tasks 4 + 5
**Files:**
- Modify: `shield-app/app/src/main/java/com/shieldtube/MainActivity.kt`

- [ ] **Step 1: Update MainActivity to launch BrowseFragment**

```kotlin
// shield-app/app/src/main/java/com/shieldtube/MainActivity.kt
package com.shieldtube

import android.os.Bundle
import androidx.fragment.app.FragmentActivity
import com.shieldtube.ui.BrowseFragment

class MainActivity : FragmentActivity() {
    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        if (savedInstanceState == null) {
            supportFragmentManager.beginTransaction()
                .replace(android.R.id.content, BrowseFragment())
                .commit()
        }
    }
}
```

- [ ] **Step 2: Commit**

```bash
git add shield-app/app/src/main/java/com/shieldtube/MainActivity.kt
git commit -m "feat: wire MainActivity to BrowseFragment for Phase 2b browse experience"
```

---

## Parallel Dispatch Summary

| Workstream | Worktree Branch | Completion Promise | Depends On |
|---|---|---|---|
| A: API Client + Models | `ws/api-client` | `API CLIENT COMPLETE` | Task 0 |
| B: PlaybackFragment Update | `ws/playback-update` | `PLAYBACK UPDATE COMPLETE` | Task 0 |
| Task 3: CardPresenter | main | N/A | A + B |
| Task 4: BrowseFragment | main | N/A | Task 3 |
| Task 5: SearchFragment | main | N/A | Task 3 |
| Task 6: MainActivity | main | N/A | Tasks 4 + 5 |

**Orchestrator flow:**
1. Execute Task 0 (deps update) on main
2. Dispatch Workstreams A and B in parallel (separate worktrees)
3. As each completes → review → merge
4. Execute Tasks 3, 4, 5, 6 sequentially on main
5. Linearize history, strip Co-Authored-By
6. Deploy and test on NVIDIA Shield TV

---

## Deployment Guide: NVIDIA Shield TV

### Prerequisites

- NVIDIA Shield TV (2019 Pro or later) connected to same LAN as backend server
- LG OLED TV connected to Shield via HDMI 2.1
- Android Studio installed on dev machine (for `adb` and `gradlew`)
- Shield TV in Developer Mode (Settings → Device Preferences → About → Build → click 7 times)
- USB Debugging enabled (Settings → Device Preferences → Developer options → USB debugging)
- Backend server running (`docker-compose up -d` or `uvicorn`)
- Shield and dev machine on same WiFi/LAN

### Step 1: Find Shield's IP Address

On the Shield TV:
```
Settings → Network & Internet → [Your WiFi network] → note the IP address
```

Or from dev machine:
```bash
# If Shield is connected via USB
adb devices
# If connecting over WiFi (need USB first time)
adb connect <shield-ip>:5555
```

### Step 2: Enable ADB over WiFi (if not using USB)

First connect via USB, then:
```bash
adb tcpip 5555
adb connect <shield-ip>:5555
# Disconnect USB cable — ADB works over WiFi now
```

### Step 3: Verify Backend is Reachable from Shield

On your dev machine, verify the backend is running and accessible:
```bash
# From any machine on the LAN
curl http://<backend-ip>:8080/api/feed/home
# Should return JSON with video data
```

**Important:** The `BACKEND_HOST` constant in `ApiClient.kt` must match your backend server's LAN IP. If your backend is at `192.168.1.50:8080`, update:
- `shield-app/app/src/main/java/com/shieldtube/api/ApiClient.kt` → `BASE_URL = "http://192.168.1.50:8080"`
- `shield-app/app/src/main/java/com/shieldtube/player/PlaybackFragment.kt` → `BACKEND_HOST = "http://192.168.1.50:8080"`

### Step 4: Build the APK

```bash
cd shield-app

# Debug build (no signing required)
./gradlew assembleDebug

# APK location:
# shield-app/app/build/outputs/apk/debug/app-debug.apk
```

If build fails, check:
- JDK 17 installed (`java -version`)
- Android SDK installed with API 34 (`sdkmanager --list`)
- `ANDROID_HOME` environment variable set

### Step 5: Install on Shield TV

```bash
# Install via ADB (USB or WiFi)
cd shield-app
./gradlew installDebug

# Or manually:
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

If you get `INSTALL_FAILED_UPDATE_INCOMPATIBLE`:
```bash
adb uninstall com.shieldtube
adb install app/build/outputs/apk/debug/app-debug.apk
```

### Step 6: Launch the App

```bash
# Via ADB
adb shell am start -n com.shieldtube/.MainActivity

# Or: navigate on Shield TV
# Home → Apps → ShieldTube
```

### Step 7: Verify End-to-End

1. **App launches** → BrowseFragment with "ShieldTube" title appears
2. **Home feed loads** → Card rows with real YouTube thumbnails populate
3. **Thumbnails load** → Glide loads images from backend's thumbnail cache
4. **Navigate sidebar** → D-pad left, select "Subscriptions", feed loads
5. **Search** → Select search icon, speak or type query, results appear
6. **Play video** → Select any card → video plays on LG OLED
7. **HDR passthrough** → TV should switch to HDR mode for HDR content
8. **Back navigation** → Back button returns to BrowseFragment from playback
9. **Voice search** → Press mic button on Shield remote, speak query

### Step 8: Verify HDR Passthrough

On your LG OLED, check:
- Picture mode switches to HDR/Dolby Vision when playing HDR content
- `Settings → Picture → HDR Effect` shows "HDR" indicator
- Shield display settings: Match content color space = ON

### Troubleshooting

| Symptom | Cause | Fix |
|---------|-------|-----|
| App installs but crashes on launch | Missing dependency or API level | Check `adb logcat -s ShieldTube` for errors |
| Feed loads but thumbnails are blank | Wrong BACKEND_HOST IP | Verify `curl http://<ip>:8080/api/video/<id>/thumbnail` works from Shield's network |
| "Failed to load Home feed" toast | Backend not reachable | Check backend is running, firewall allows port 8080, IPs match |
| Video doesn't play | yt-dlp or FFmpeg issue on backend | Check backend logs: `docker-compose logs -f` |
| No HDR on LG OLED | Shield display settings | Enable "Match content color space" in Shield settings |
| Voice search doesn't work | No speech recognizer on Shield | Install Google app if missing: `adb install com.google.android.katniss` |
| App not visible in launcher | Missing LEANBACK_LAUNCHER | Check AndroidManifest.xml has `LEANBACK_LAUNCHER` category |

### Quick Iteration Cycle

For rapid development:
```bash
# One-liner: build + install + launch
cd shield-app && ./gradlew installDebug && adb shell am start -n com.shieldtube/.MainActivity

# View logs in real-time
adb logcat -s ShieldTube PlaybackFragment BrowseFragment CardPresenter
```
