# Phase 4b: Chapter Markers — Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking. Backend and Shield app can be dispatched as parallel agents.

**Goal:** Display chapter markers during playback — current chapter title as overlay, D-pad long-press to jump between chapters.

**Architecture:** yt-dlp already extracts chapters during resolve_stream(). Backend stores them as chapters_json in videos table, serves via meta endpoint. Shield app fetches chapters, shows title overlay, enables chapter navigation.

**Tech Stack:** Python 3.11+, FastAPI, aiosqlite | Kotlin, ExoPlayer/Media3, Leanback

---

## Execution Model

```
Task 0: Migration (sequential)
        |
        +-- Workstream A: Backend (resolver + download_manager + meta endpoint)
        +-- Workstream B: Shield app (models + PlaybackFragment chapter UI)
```

---

## Task 0: Migration (Sequential)

- [ ] **Step 1: Create migration**

```sql
-- backend/db/migrations/004_chapters.sql
ALTER TABLE videos ADD COLUMN chapters_json TEXT;
```

- [ ] **Step 2: Commit**

```bash
git add backend/db/migrations/004_chapters.sql
git commit -m "chore: add chapters_json column migration"
```

---

## Workstream A: Backend Chapters (Parallel)

**Completion Promise:** `CHAPTERS BACKEND COMPLETE`

Agent modifies 3 files:

### 1. Update stream_resolver.py

Add `chapters` to the return dict:
```python
# After the existing return dict construction, add:
"chapters": info.get("chapters") or []
```

The `chapters` field from yt-dlp is a list of `{"title": str, "start_time": float, "end_time": float}`.

### 2. Update download_manager.py

In `_start_download()`, after resolving the stream, store chapters in DB:
```python
# After resolve_stream() call, before starting FFmpeg:
import json
chapters_json = json.dumps(stream_info.get("chapters", []))
await self._db.execute(
    "UPDATE videos SET chapters_json = ? WHERE id = ?",
    (chapters_json, video_id),
)
```

### 3. Update watch.py meta endpoint

In `get_video_meta()`, add chapters to the response:
```python
import json

# After loading video from DB:
chapters = json.loads(video.chapters_json) if hasattr(video, 'chapters_json') and video.chapters_json else []

# Add to return dict:
"chapters": chapters,
```

Also need to update the Video model to include the new column. Add `chapters_json: str | None = None` to the Video dataclass in models.py, and update `_row_to_video()` in repositories.py to include it.

### 4. Tests

`backend/tests/test_chapters.py`:
- test_resolve_stream_returns_chapters: mock yt-dlp with chapters fixture, verify chapters in return dict
- test_meta_endpoint_returns_chapters: seed video with chapters_json, GET meta, verify chapters field
- test_meta_endpoint_returns_empty_chapters: seed video without chapters_json, verify empty list

---

## Workstream B: Shield App Chapters (Parallel)

**Completion Promise:** `CHAPTERS SHIELD COMPLETE`

Agent modifies 3 files:

### 1. Add Chapter data class to models.kt

```kotlin
data class Chapter(
    val title: String,
    @SerializedName("start_time") val startTime: Double,
    @SerializedName("end_time") val endTime: Double
)
```

Update VideoMeta to include chapters:
```kotlin
data class VideoMeta(
    // ... existing fields ...
    val chapters: List<Chapter> = emptyList()
)
```

### 2. Update PlaybackFragment.kt

Add fields:
```kotlin
private var chapters: List<Chapter> = emptyList()
private var currentChapterIndex: Int = -1
private var chapterCheckJob: Job? = null
private var chapterOverlay: TextView? = null
```

In `onCreateView()`, add a chapter title overlay TextView on top of the PlayerView:
```kotlin
// After creating playerView, add overlay
chapterOverlay = TextView(requireContext()).apply {
    setTextColor(Color.WHITE)
    textSize = 16f
    setPadding(24, 12, 24, 12)
    setBackgroundColor(Color.parseColor("#88000000"))
    visibility = View.GONE
    layoutParams = FrameLayout.LayoutParams(
        FrameLayout.LayoutParams.WRAP_CONTENT,
        FrameLayout.LayoutParams.WRAP_CONTENT,
        Gravity.TOP or Gravity.START
    ).apply { setMargins(16, 16, 0, 0) }
}

// Wrap playerView and overlay in a FrameLayout
val container = FrameLayout(requireContext()).apply {
    layoutParams = ViewGroup.LayoutParams(MATCH_PARENT, MATCH_PARENT)
    addView(playerView)
    addView(chapterOverlay)
}
return container
```

In `initPlayer()`, after fetching meta (which already happens for resume position), populate chapters:
```kotlin
// Already fetching meta for resume — add:
chapters = meta.chapters
if (chapters.isNotEmpty()) {
    startChapterChecking()
}
```

Add chapter checking coroutine:
```kotlin
private fun startChapterChecking() {
    chapterCheckJob = lifecycleScope.launch {
        while (isActive) {
            delay(1000)
            player?.let { p ->
                val positionSec = p.currentPosition / 1000.0
                val newIndex = chapters.indexOfLast { positionSec >= it.startTime }
                if (newIndex != currentChapterIndex && newIndex >= 0) {
                    currentChapterIndex = newIndex
                    showChapterTitle(chapters[newIndex].title)
                }
            }
        }
    }
}

private fun showChapterTitle(title: String) {
    chapterOverlay?.apply {
        text = title
        visibility = View.VISIBLE
        // Fade out after 3 seconds
        handler?.removeCallbacksAndMessages(null)
        handler?.postDelayed({
            animate().alpha(0f).setDuration(500).withEndAction {
                visibility = View.GONE
                alpha = 1f
            }
        }, 3000)
    }
}
```

Add chapter navigation via key events. Override in the fragment or add to the container:
```kotlin
// In onCreateView, add to container:
container.isFocusable = true
container.setOnKeyListener { _, keyCode, event ->
    if (event.action == KeyEvent.ACTION_DOWN && event.isLongPress) {
        when (keyCode) {
            KeyEvent.KEYCODE_DPAD_RIGHT -> {
                jumpToNextChapter()
                true
            }
            KeyEvent.KEYCODE_DPAD_LEFT -> {
                jumpToPreviousChapter()
                true
            }
            else -> false
        }
    } else false
}
```

```kotlin
private fun jumpToNextChapter() {
    if (chapters.isEmpty() || currentChapterIndex >= chapters.size - 1) return
    val next = chapters[currentChapterIndex + 1]
    player?.seekTo((next.startTime * 1000).toLong())
}

private fun jumpToPreviousChapter() {
    if (chapters.isEmpty() || currentChapterIndex <= 0) return
    val prev = chapters[currentChapterIndex - 1]
    player?.seekTo((prev.startTime * 1000).toLong())
}
```

In `releasePlayer()`:
```kotlin
chapterCheckJob?.cancel()
chapterCheckJob = null
chapters = emptyList()
currentChapterIndex = -1
```

### 3. Add tests to ModelsTest.kt

```kotlin
@Test
fun `deserialize Chapter from JSON`() {
    val json = """{"title": "Intro", "start_time": 0.0, "end_time": 150.0}"""
    val chapter = gson.fromJson(json, Chapter::class.java)
    assertEquals("Intro", chapter.title)
    assertEquals(0.0, chapter.startTime, 0.01)
    assertEquals(150.0, chapter.endTime, 0.01)
}

@Test
fun `deserialize VideoMeta with chapters`() {
    val json = """
    {
        "id": "test", "title": "Test", "channel_name": "Ch", "channel_id": "UC",
        "duration": 600, "cache_status": "cached", "last_position_seconds": 0,
        "chapters": [
            {"title": "Intro", "start_time": 0.0, "end_time": 150.0},
            {"title": "Main", "start_time": 150.0, "end_time": 600.0}
        ]
    }
    """.trimIndent()
    val meta = gson.fromJson(json, VideoMeta::class.java)
    assertEquals(2, meta.chapters.size)
    assertEquals("Intro", meta.chapters[0].title)
}

@Test
fun `deserialize VideoMeta without chapters defaults to empty`() {
    val json = """
    {
        "id": "test", "title": "Test", "channel_name": "Ch", "channel_id": "UC",
        "duration": 600, "cache_status": "cached", "last_position_seconds": 0
    }
    """.trimIndent()
    val meta = gson.fromJson(json, VideoMeta::class.java)
    assertTrue(meta.chapters.isEmpty())
}
```

---

## Parallel Dispatch Summary

| Workstream | Completion Promise | Files |
|---|---|---|
| A: Backend | `CHAPTERS BACKEND COMPLETE` | stream_resolver.py, download_manager.py, watch.py, models.py, repositories.py, test_chapters.py |
| B: Shield App | `CHAPTERS SHIELD COMPLETE` | models.kt, PlaybackFragment.kt, ModelsTest.kt |
