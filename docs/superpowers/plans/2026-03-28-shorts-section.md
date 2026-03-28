# Shorts Section Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add two Shorts rows ("Shorts — For You" and "Shorts — Trending") to the Shield TV browse screen, backed by yt-dlp scraping, with a portrait-mode looping player and D-pad sequential navigation.

**Architecture:** A new `shorts_feed.py` service scrapes yt-dlp for Shorts data (top-affinity channel Shorts tabs + YouTube's Shorts feed), exposed via two new FastAPI endpoints. On Android, two new rows in `BrowseFragment` use a portrait `ShortsCardPresenter`, and tapping a card launches a new `ShortsPlayerFragment` with centered portrait `PlayerView`, `REPEAT_MODE_ONE`, and D-pad up/down navigation through the list.

**Tech Stack:** Python/FastAPI, yt-dlp (Python API), aiosqlite · Kotlin, ExoPlayer (Media3), Retrofit, Leanback `BrowseSupportFragment`

---

## File Map

| Action | Path | Responsibility |
|--------|------|----------------|
| Create | `backend/services/shorts_feed.py` | yt-dlp scraping, 1-hour in-memory cache |
| Create | `backend/api/routers/shorts.py` | `/api/feed/shorts/recommended` and `/api/feed/shorts/trending` |
| Modify | `backend/api/main.py` | import + include shorts router |
| Create | `backend/tests/test_shorts_feed.py` | unit tests for cache and empty-channel path |
| Create | `shield-app/app/src/main/java/com/shieldtube/ui/ShortsCardPresenter.kt` | portrait 120×213dp card |
| Modify | `shield-app/app/src/main/java/com/shieldtube/api/ShieldTubeApi.kt` | two new API methods |
| Modify | `shield-app/app/src/main/java/com/shieldtube/ui/BrowseFragment.kt` | two new rows, adapters, click routing |
| Create | `shield-app/app/src/main/java/com/shieldtube/player/ShortsPlayerFragment.kt` | portrait player, loop, D-pad nav |

---

## Task 1: Backend — `shorts_feed.py` service (TDD)

**Files:**
- Create: `backend/services/shorts_feed.py`
- Create: `backend/tests/test_shorts_feed.py`

- [ ] **Step 1: Write failing tests**

Create `backend/tests/test_shorts_feed.py`:

```python
"""Tests for shorts_feed service."""
import time
import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


def _make_mock_db(rows):
    cursor = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=rows)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=cursor)
    return db


async def test_recommended_returns_empty_when_no_channels():
    """No watch history → no top channels → empty list."""
    from backend.services import shorts_feed
    shorts_feed._CACHE.clear()

    db = _make_mock_db([])
    result = await shorts_feed.get_recommended_shorts(db)
    assert result == []


async def test_recommended_returns_cached_result():
    """Within TTL, returns cached result without hitting DB."""
    from backend.services import shorts_feed
    shorts_feed._CACHE["recommended"] = (time.monotonic(), [{"id": "abc", "title": "Cached Short"}])

    db = _make_mock_db([])  # would return empty if called
    result = await shorts_feed.get_recommended_shorts(db)

    assert len(result) == 1
    assert result[0]["id"] == "abc"
    shorts_feed._CACHE.clear()


async def test_trending_returns_cached_result():
    """Within TTL, get_trending_shorts returns cached result without scraping."""
    from backend.services import shorts_feed
    shorts_feed._CACHE["trending"] = (time.monotonic(), [{"id": "xyz", "title": "Trending Short"}])

    result = await shorts_feed.get_trending_shorts()

    assert len(result) == 1
    assert result[0]["id"] == "xyz"
    shorts_feed._CACHE.clear()


async def test_recommended_skips_failed_channels():
    """If one channel scrape fails, result still contains others."""
    from backend.services import shorts_feed
    shorts_feed._CACHE.clear()

    rows = [
        {"channel_id": "UC_GOOD", "channel_name": "Good Channel", "watch_count": 10},
        {"channel_id": "UC_BAD", "channel_name": "Bad Channel", "watch_count": 5},
    ]
    db = _make_mock_db(rows)

    def fake_scrape(channel_id, limit=5):
        if channel_id == "UC_BAD":
            raise RuntimeError("yt-dlp failed")
        return [{"id": "v1", "title": "Short 1", "channel_name": "Good Channel",
                 "channel_id": channel_id, "duration": 30, "published_at": None,
                 "thumbnail_url": "/api/video/v1/thumbnail?res=maxres"}]

    with patch("backend.services.shorts_feed._scrape_channel_shorts", side_effect=fake_scrape):
        with patch("asyncio.to_thread", side_effect=lambda fn, *a, **kw: fn(*a, **kw)):
            result = await shorts_feed.get_recommended_shorts(db)

    assert len(result) == 1
    assert result[0]["id"] == "v1"
    shorts_feed._CACHE.clear()
```

- [ ] **Step 2: Run tests — expect ImportError (module doesn't exist yet)**

```bash
cd /home/asjad/shieldtube && python -m pytest backend/tests/test_shorts_feed.py -v 2>&1 | head -30
```

Expected: `ModuleNotFoundError: No module named 'backend.services.shorts_feed'`

- [ ] **Step 3: Implement `shorts_feed.py`**

Create `backend/services/shorts_feed.py`:

```python
"""Shorts feed — yt-dlp scraping for recommended channel Shorts and trending Shorts."""
from __future__ import annotations

import asyncio
import logging
import time

import aiosqlite
import yt_dlp

from backend.config import settings

logger = logging.getLogger(__name__)

# Module-level in-memory cache: {key: (fetched_at_monotonic, results)}
_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 3600  # 1 hour


def _ydl_opts(playlist_end: int = 5) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "playlistend": playlist_end,
    }
    if settings.ytdlp_cookies_path:
        opts["cookiefile"] = settings.ytdlp_cookies_path
    if settings.ytdlp_proxy:
        opts["proxy"] = settings.ytdlp_proxy
    return opts


def _normalize_date(upload_date: str | None) -> str | None:
    """Convert YYYYMMDD → ISO 8601, or return None."""
    if not upload_date or len(upload_date) != 8:
        return None
    try:
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}T00:00:00Z"
    except Exception:
        return None


def _scrape_channel_shorts(channel_id: str, limit: int = 5) -> list[dict]:
    """Scrape the Shorts tab of a channel. Synchronous — run via asyncio.to_thread."""
    url = f"https://www.youtube.com/channel/{channel_id}/shorts"
    with yt_dlp.YoutubeDL(_ydl_opts(limit)) as ydl:
        info = ydl.extract_info(url, download=False)
    if info is None:
        return []
    entries = info.get("entries") or []
    channel_name = info.get("channel") or info.get("uploader") or ""
    results = []
    for e in entries:
        if e is None:
            continue
        vid_id = e.get("id") or ""
        if not vid_id:
            continue
        results.append({
            "id": vid_id,
            "title": e.get("title") or "",
            "channel_name": e.get("channel") or e.get("uploader") or channel_name,
            "channel_id": channel_id,
            "duration": e.get("duration"),
            "published_at": _normalize_date(e.get("upload_date")),
            "thumbnail_url": f"/api/video/{vid_id}/thumbnail?res=maxres",
        })
    return results


def _scrape_trending_shorts(limit: int = 20) -> list[dict]:
    """Scrape YouTube's Shorts discovery feed. Synchronous — run via asyncio.to_thread."""
    url = "https://www.youtube.com/shorts"
    with yt_dlp.YoutubeDL(_ydl_opts(limit)) as ydl:
        info = ydl.extract_info(url, download=False)
    if info is None:
        return []
    entries = info.get("entries") or []
    results = []
    for e in entries:
        if e is None:
            continue
        vid_id = e.get("id") or ""
        if not vid_id:
            continue
        results.append({
            "id": vid_id,
            "title": e.get("title") or "",
            "channel_name": e.get("channel") or e.get("uploader") or "",
            "channel_id": e.get("channel_id") or "",
            "duration": e.get("duration"),
            "published_at": _normalize_date(e.get("upload_date")),
            "thumbnail_url": f"/api/video/{vid_id}/thumbnail?res=maxres",
        })
    return results


async def get_recommended_shorts(
    db: aiosqlite.Connection,
    max_channels: int = 10,
    shorts_per_channel: int = 5,
) -> list[dict]:
    """Return Shorts from the top affinity channels in watch history."""
    cache_key = "recommended"
    cached = _CACHE.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL:
        return cached[1]

    cursor = await db.execute(
        """SELECT v.channel_id, v.channel_name, COUNT(*) as watch_count
           FROM watch_history wh
           JOIN videos v ON v.id = wh.video_id
           WHERE v.channel_id IS NOT NULL AND v.channel_id != ''
           GROUP BY v.channel_id
           ORDER BY watch_count DESC
           LIMIT ?""",
        (max_channels,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return []

    all_shorts: list[dict] = []
    for row in rows:
        try:
            shorts = await asyncio.to_thread(
                _scrape_channel_shorts, row["channel_id"], shorts_per_channel
            )
            all_shorts.extend(shorts)
        except Exception as exc:
            logger.warning("Failed to scrape Shorts for channel %s: %s", row["channel_id"], exc)

    all_shorts.sort(key=lambda v: v.get("published_at") or "", reverse=True)

    _CACHE[cache_key] = (time.monotonic(), all_shorts)
    return all_shorts


async def get_trending_shorts(limit: int = 20) -> list[dict]:
    """Return Shorts from YouTube's Shorts discovery feed."""
    cache_key = "trending"
    cached = _CACHE.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        shorts = await asyncio.to_thread(_scrape_trending_shorts, limit)
    except Exception as exc:
        logger.warning("Failed to scrape trending Shorts: %s", exc)
        return []

    _CACHE[cache_key] = (time.monotonic(), shorts)
    return shorts
```

- [ ] **Step 4: Run tests — expect PASS**

```bash
cd /home/asjad/shieldtube && python -m pytest backend/tests/test_shorts_feed.py -v
```

Expected output:
```
PASSED backend/tests/test_shorts_feed.py::test_recommended_returns_empty_when_no_channels
PASSED backend/tests/test_shorts_feed.py::test_recommended_returns_cached_result
PASSED backend/tests/test_shorts_feed.py::test_trending_returns_cached_result
PASSED backend/tests/test_shorts_feed.py::test_recommended_skips_failed_channels
4 passed
```

- [ ] **Step 5: Commit**

```bash
cd /home/asjad/shieldtube
rtk git add backend/services/shorts_feed.py backend/tests/test_shorts_feed.py
rtk git commit -m "feat: add shorts_feed service with yt-dlp scraping and 1h cache"
```

---

## Task 2: Backend — Shorts router + wire into main.py

**Files:**
- Create: `backend/api/routers/shorts.py`
- Modify: `backend/api/main.py`

- [ ] **Step 1: Create `backend/api/routers/shorts.py`**

```python
"""Shorts feed endpoints."""
from fastapi import APIRouter

from backend.db.database import get_db
from backend.services.shorts_feed import get_recommended_shorts, get_trending_shorts

router = APIRouter()


@router.get("/feed/shorts/recommended")
async def shorts_recommended():
    db = await get_db()
    videos = await get_recommended_shorts(db)
    return {"feed_type": "shorts_recommended", "videos": videos, "cached_at": None, "from_cache": False}


@router.get("/feed/shorts/trending")
async def shorts_trending():
    videos = await get_trending_shorts()
    return {"feed_type": "shorts_trending", "videos": videos, "cached_at": None, "from_cache": False}
```

- [ ] **Step 2: Wire router into `backend/api/main.py`**

Find the existing router import line at line 115:
```python
from backend.api.routers import video, feed, search, auth, watch, cache, cast, dashboard, recommend, rate  # noqa: E402
```

Replace with:
```python
from backend.api.routers import video, feed, search, auth, watch, cache, cast, dashboard, recommend, rate, shorts  # noqa: E402
```

Then find the last `app.include_router` call (line 126):
```python
app.include_router(rate.router, prefix="/api")
```

Add after it:
```python
app.include_router(shorts.router, prefix="/api")
```

- [ ] **Step 3: Smoke-test the endpoints with pytest**

```bash
cd /home/asjad/shieldtube && python -m pytest backend/tests/ -v -k "shorts" 2>&1 | tail -10
```

Expected: `4 passed` (the same 4 tests from Task 1 still pass; the import chain is valid).

- [ ] **Step 4: Verify FastAPI can start without import errors**

```bash
cd /home/asjad/shieldtube && python -c "from backend.api.main import app; print('OK')"
```

Expected: `OK`

- [ ] **Step 5: Commit**

```bash
cd /home/asjad/shieldtube
rtk git add backend/api/routers/shorts.py backend/api/main.py
rtk git commit -m "feat: add /api/feed/shorts/recommended and /api/feed/shorts/trending endpoints"
```

---

## Task 3: Android — `ShortsCardPresenter.kt`

**Files:**
- Create: `shield-app/app/src/main/java/com/shieldtube/ui/ShortsCardPresenter.kt`

- [ ] **Step 1: Create `ShortsCardPresenter.kt`**

```kotlin
package com.shieldtube.ui

import android.graphics.Color
import android.graphics.drawable.ColorDrawable
import android.view.ViewGroup
import androidx.leanback.widget.ImageCardView
import androidx.leanback.widget.Presenter
import com.bumptech.glide.Glide
import com.shieldtube.api.ApiClient
import com.shieldtube.api.Video

class ShortsCardPresenter : Presenter() {

    companion object {
        private const val CARD_WIDTH_DP = 120
        private const val CARD_HEIGHT_DP = 213  // 9:16 portrait ratio
    }

    override fun onCreateViewHolder(parent: ViewGroup): ViewHolder {
        val context = parent.context
        val density = context.resources.displayMetrics.density
        val cardWidthPx = (CARD_WIDTH_DP * density).toInt()
        val cardHeightPx = (CARD_HEIGHT_DP * density).toInt()

        val cardView = ImageCardView(context).apply {
            isFocusable = true
            isFocusableInTouchMode = true
            setMainImageDimensions(cardWidthPx, cardHeightPx)
        }
        return ViewHolder(cardView)
    }

    override fun onBindViewHolder(viewHolder: ViewHolder, item: Any?) {
        val video = item as? Video ?: return
        val cardView = viewHolder.view as ImageCardView
        val context = cardView.context

        cardView.titleText = video.title
        cardView.contentText = video.channelName
        cardView.infoAreaBackground = ColorDrawable(0xFF1a1a2e.toInt())

        val thumbnailUrl = "${ApiClient.BASE_URL}${video.thumbnailUrl}"
        Glide.with(context)
            .load(thumbnailUrl)
            .centerCrop()
            .placeholder(ColorDrawable(Color.DKGRAY))
            .error(ColorDrawable(Color.DKGRAY))
            .into(cardView.mainImageView!!)
    }

    override fun onUnbindViewHolder(viewHolder: ViewHolder) {
        val cardView = viewHolder.view as ImageCardView
        cardView.badgeImage = null
        cardView.mainImage = null
    }
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd /home/asjad/shieldtube/shield-app && ./gradlew compileDebugKotlin 2>&1 | tail -5
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 3: Commit**

```bash
cd /home/asjad/shieldtube
rtk git add shield-app/app/src/main/java/com/shieldtube/ui/ShortsCardPresenter.kt
rtk git commit -m "feat: add ShortsCardPresenter for portrait 9:16 cards"
```

---

## Task 4: Android — Add Shorts API methods to `ShieldTubeApi.kt`

**Files:**
- Modify: `shield-app/app/src/main/java/com/shieldtube/api/ShieldTubeApi.kt`

- [ ] **Step 1: Add two methods to `ShieldTubeApi`**

In `ShieldTubeApi.kt`, find the last method before the closing `}` of the interface:

```kotlin
    @DELETE("/api/playback/status")
    suspend fun clearPlaybackStatus()
}
```

Replace with:

```kotlin
    @DELETE("/api/playback/status")
    suspend fun clearPlaybackStatus()

    @GET("/api/feed/shorts/recommended")
    suspend fun getShortsRecommended(): FeedResponse

    @GET("/api/feed/shorts/trending")
    suspend fun getShortsTrending(): FeedResponse
}
```

- [ ] **Step 2: Verify it compiles**

```bash
cd /home/asjad/shieldtube/shield-app && ./gradlew compileDebugKotlin 2>&1 | tail -5
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 3: Commit**

```bash
cd /home/asjad/shieldtube
rtk git add shield-app/app/src/main/java/com/shieldtube/api/ShieldTubeApi.kt
rtk git commit -m "feat: add getShortsRecommended and getShortsTrending to ShieldTubeApi"
```

---

## Task 5: Android — Modify `BrowseFragment.kt` to add two Shorts rows

**Files:**
- Modify: `shield-app/app/src/main/java/com/shieldtube/ui/BrowseFragment.kt`

- [ ] **Step 1: Add Shorts row constants and adapters**

Find the `companion object` block:

```kotlin
    companion object {
        private const val HEADER_HOME = 0L
        private const val HEADER_HISTORY = 2L
        private const val HEADER_FOR_YOU = 3L
        private const val HEADER_DOWNLOADS = 4L
        private const val HEADER_NEW_CHANNELS = 5L
    }
```

Replace with:

```kotlin
    companion object {
        private const val HEADER_HOME = 0L
        private const val HEADER_HISTORY = 2L
        private const val HEADER_FOR_YOU = 3L
        private const val HEADER_DOWNLOADS = 4L
        private const val HEADER_NEW_CHANNELS = 5L
        private const val HEADER_SHORTS_RECOMMENDED = 6L
        private const val HEADER_SHORTS_TRENDING = 7L
    }
```

Find the per-row adapter declarations:

```kotlin
    private val downloadsAdapter = ArrayObjectAdapter(CardPresenter())
    private val channelsAdapter = ArrayObjectAdapter(CardPresenter())
    private val forYouAdapter = ArrayObjectAdapter(CardPresenter())
    private val homeAdapter = ArrayObjectAdapter(CardPresenter())
    private val historyAdapter = ArrayObjectAdapter(CardPresenter())
```

Replace with:

```kotlin
    private val downloadsAdapter = ArrayObjectAdapter(CardPresenter())
    private val channelsAdapter = ArrayObjectAdapter(CardPresenter())
    private val forYouAdapter = ArrayObjectAdapter(CardPresenter())
    private val homeAdapter = ArrayObjectAdapter(CardPresenter())
    private val historyAdapter = ArrayObjectAdapter(CardPresenter())
    private val shortsRecommendedAdapter = ArrayObjectAdapter(ShortsCardPresenter())
    private val shortsTrendingAdapter = ArrayObjectAdapter(ShortsCardPresenter())
```

- [ ] **Step 2: Add rows to `setupHeaders()`**

Find the start of `setupHeaders()`:

```kotlin
    private fun setupHeaders() {
        rowsAdapter = ArrayObjectAdapter(ListRowPresenter())

        val downloadsHeader = HeaderItem(HEADER_DOWNLOADS, "Downloads")
        rowsAdapter.add(ListRow(downloadsHeader, downloadsAdapter))
```

Replace with:

```kotlin
    private fun setupHeaders() {
        rowsAdapter = ArrayObjectAdapter(ListRowPresenter())

        val shortsRecHeader = HeaderItem(HEADER_SHORTS_RECOMMENDED, "Shorts — For You")
        rowsAdapter.add(ListRow(shortsRecHeader, shortsRecommendedAdapter))

        val shortsTrendHeader = HeaderItem(HEADER_SHORTS_TRENDING, "Shorts — Trending")
        rowsAdapter.add(ListRow(shortsTrendHeader, shortsTrendingAdapter))

        val downloadsHeader = HeaderItem(HEADER_DOWNLOADS, "Downloads")
        rowsAdapter.add(ListRow(downloadsHeader, downloadsAdapter))
```

- [ ] **Step 3: Update `loadFeedForHeader()` to handle Shorts rows**

Find the `when` block inside `loadFeedForHeader()`:

```kotlin
                val feedResponse = when (headerId) {
                    HEADER_DOWNLOADS -> ApiClient.api.getDownloadLibrary()
                    HEADER_NEW_CHANNELS -> ApiClient.api.getFeedChannels()
                    HEADER_FOR_YOU -> ApiClient.api.getFeedRecommended()
                    HEADER_HOME -> ApiClient.api.getFeedHome()
                    HEADER_HISTORY -> ApiClient.api.getFeedHistory()
                    else -> return@launch
                }
```

Replace with:

```kotlin
                val feedResponse = when (headerId) {
                    HEADER_SHORTS_RECOMMENDED -> ApiClient.api.getShortsRecommended()
                    HEADER_SHORTS_TRENDING -> ApiClient.api.getShortsTrending()
                    HEADER_DOWNLOADS -> ApiClient.api.getDownloadLibrary()
                    HEADER_NEW_CHANNELS -> ApiClient.api.getFeedChannels()
                    HEADER_FOR_YOU -> ApiClient.api.getFeedRecommended()
                    HEADER_HOME -> ApiClient.api.getFeedHome()
                    HEADER_HISTORY -> ApiClient.api.getFeedHistory()
                    else -> return@launch
                }
```

- [ ] **Step 4: Update `refreshFeed()` to handle Shorts rows**

Find the `when` block inside `refreshFeed()`:

```kotlin
                val feedResponse = when (headerId) {
                    HEADER_DOWNLOADS -> ApiClient.api.getDownloadLibrary()
                    HEADER_NEW_CHANNELS -> ApiClient.api.getFeedChannels()
                    HEADER_HISTORY -> ApiClient.api.getFeedHistory()
                    HEADER_HOME -> ApiClient.api.getFeedHome()
                    HEADER_FOR_YOU -> ApiClient.api.getFeedRecommended()
                    else -> return@launch
                }
```

Replace with:

```kotlin
                val feedResponse = when (headerId) {
                    HEADER_SHORTS_RECOMMENDED -> ApiClient.api.getShortsRecommended()
                    HEADER_SHORTS_TRENDING -> ApiClient.api.getShortsTrending()
                    HEADER_DOWNLOADS -> ApiClient.api.getDownloadLibrary()
                    HEADER_NEW_CHANNELS -> ApiClient.api.getFeedChannels()
                    HEADER_HISTORY -> ApiClient.api.getFeedHistory()
                    HEADER_HOME -> ApiClient.api.getFeedHome()
                    HEADER_FOR_YOU -> ApiClient.api.getFeedRecommended()
                    else -> return@launch
                }
```

- [ ] **Step 5: Update `updateRowContent()` to handle Shorts rows**

Find the `when` block inside `updateRowContent()`:

```kotlin
        val targetAdapter = when (headerId) {
            HEADER_DOWNLOADS -> downloadsAdapter
            HEADER_NEW_CHANNELS -> channelsAdapter
            HEADER_FOR_YOU -> forYouAdapter
            HEADER_HOME -> homeAdapter
            HEADER_HISTORY -> historyAdapter
            else -> return
        }
```

Replace with:

```kotlin
        val targetAdapter = when (headerId) {
            HEADER_SHORTS_RECOMMENDED -> shortsRecommendedAdapter
            HEADER_SHORTS_TRENDING -> shortsTrendingAdapter
            HEADER_DOWNLOADS -> downloadsAdapter
            HEADER_NEW_CHANNELS -> channelsAdapter
            HEADER_FOR_YOU -> forYouAdapter
            HEADER_HOME -> homeAdapter
            HEADER_HISTORY -> historyAdapter
            else -> return
        }
```

- [ ] **Step 6: Load Shorts rows on startup in `onCreate()`**

Find in `onCreate()`:

```kotlin
        loadFeedForHeader(HEADER_DOWNLOADS)
        loadFeedForHeader(HEADER_NEW_CHANNELS)
```

Replace with:

```kotlin
        loadFeedForHeader(HEADER_SHORTS_RECOMMENDED)
        loadFeedForHeader(HEADER_SHORTS_TRENDING)
        loadFeedForHeader(HEADER_DOWNLOADS)
        loadFeedForHeader(HEADER_NEW_CHANNELS)
```

- [ ] **Step 7: Refresh Shorts rows on `onResume()`**

Find in `onResume()`:

```kotlin
        refreshFeed(HEADER_DOWNLOADS)
        refreshFeed(HEADER_NEW_CHANNELS)
```

Replace with:

```kotlin
        refreshFeed(HEADER_SHORTS_RECOMMENDED)
        refreshFeed(HEADER_SHORTS_TRENDING)
        refreshFeed(HEADER_DOWNLOADS)
        refreshFeed(HEADER_NEW_CHANNELS)
```

- [ ] **Step 8: Route Shorts card clicks to `ShortsPlayerFragment`**

Find the item click listener in `setupListeners()`:

```kotlin
        setOnItemViewClickedListener { _, item, _, _ ->
            val video = item as? Video ?: return@setOnItemViewClickedListener
            val fragment = PlaybackFragment.newInstance(video.id)
            parentFragmentManager.beginTransaction()
                .replace(android.R.id.content, fragment)
                .addToBackStack("playback")
                .commit()
        }
```

Replace with:

```kotlin
        setOnItemViewClickedListener { _, item, _, row ->
            val video = item as? Video ?: return@setOnItemViewClickedListener
            val listRow = row as? androidx.leanback.widget.ListRow
            val headerId = listRow?.headerItem?.id

            if (headerId == HEADER_SHORTS_RECOMMENDED || headerId == HEADER_SHORTS_TRENDING) {
                val adapter = if (headerId == HEADER_SHORTS_RECOMMENDED) shortsRecommendedAdapter else shortsTrendingAdapter
                val videoIds = ArrayList((0 until adapter.size()).map { (adapter.get(it) as Video).id })
                val startIndex = videoIds.indexOf(video.id).coerceAtLeast(0)
                val fragment = com.shieldtube.player.ShortsPlayerFragment.newInstance(videoIds, startIndex)
                parentFragmentManager.beginTransaction()
                    .replace(android.R.id.content, fragment)
                    .addToBackStack("shorts")
                    .commit()
            } else {
                val fragment = PlaybackFragment.newInstance(video.id)
                parentFragmentManager.beginTransaction()
                    .replace(android.R.id.content, fragment)
                    .addToBackStack("playback")
                    .commit()
            }
        }
```

- [ ] **Step 9: Verify it compiles**

```bash
cd /home/asjad/shieldtube/shield-app && ./gradlew compileDebugKotlin 2>&1 | tail -5
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 10: Commit**

```bash
cd /home/asjad/shieldtube
rtk git add shield-app/app/src/main/java/com/shieldtube/ui/BrowseFragment.kt
rtk git commit -m "feat: add Shorts rows to BrowseFragment with ShortsCardPresenter and click routing"
```

---

## Task 6: Android — `ShortsPlayerFragment.kt`

**Files:**
- Create: `shield-app/app/src/main/java/com/shieldtube/player/ShortsPlayerFragment.kt`

- [ ] **Step 1: Create `ShortsPlayerFragment.kt`**

```kotlin
package com.shieldtube.player

import android.graphics.Color
import android.net.Uri
import android.os.Bundle
import android.view.Gravity
import android.view.KeyEvent
import android.view.LayoutInflater
import android.view.View
import android.view.ViewGroup
import android.widget.FrameLayout
import android.widget.LinearLayout
import android.widget.TextView
import android.widget.Toast
import androidx.fragment.app.Fragment
import androidx.lifecycle.lifecycleScope
import androidx.media3.common.MediaItem
import androidx.media3.common.PlaybackException
import androidx.media3.common.Player
import androidx.media3.datasource.DefaultHttpDataSource
import androidx.media3.exoplayer.ExoPlayer
import androidx.media3.exoplayer.source.ProgressiveMediaSource
import androidx.media3.extractor.DefaultExtractorsFactory
import androidx.media3.ui.PlayerView
import com.shieldtube.api.ApiClient
import kotlinx.coroutines.Job
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch

class ShortsPlayerFragment : Fragment() {

    companion object {
        private const val ARG_VIDEO_IDS = "video_ids"
        private const val ARG_START_INDEX = "start_index"

        fun newInstance(videoIds: ArrayList<String>, startIndex: Int): ShortsPlayerFragment {
            return ShortsPlayerFragment().apply {
                arguments = Bundle().apply {
                    putStringArrayList(ARG_VIDEO_IDS, videoIds)
                    putInt(ARG_START_INDEX, startIndex)
                }
            }
        }
    }

    private var player: ExoPlayer? = null
    private var playerView: PlayerView? = null
    private var videoIds: List<String> = emptyList()
    private var currentIndex: Int = 0
    private var titleView: TextView? = null
    private var channelView: TextView? = null
    private var overlayView: View? = null
    private var overlayHideJob: Job? = null

    override fun onCreate(savedInstanceState: Bundle?) {
        super.onCreate(savedInstanceState)
        videoIds = arguments?.getStringArrayList(ARG_VIDEO_IDS) ?: emptyList()
        currentIndex = arguments?.getInt(ARG_START_INDEX, 0) ?: 0
    }

    override fun onCreateView(
        inflater: LayoutInflater,
        container: ViewGroup?,
        savedInstanceState: Bundle?
    ): View {
        val context = requireContext()
        val dm = context.resources.displayMetrics
        val screenHeight = dm.heightPixels
        val screenWidth = dm.widthPixels
        // Portrait: width = height × (9/16) to maintain 9:16 ratio on a 16:9 display
        val playerWidth = (screenHeight * 9.0 / 16.0).toInt()
        val sideMargin = (screenWidth - playerWidth) / 2

        playerView = PlayerView(context).apply {
            useController = false
        }

        val titleText = TextView(context).apply {
            textSize = 16f
            setTextColor(Color.WHITE)
        }
        val channelText = TextView(context).apply {
            textSize = 13f
            setTextColor(Color.LTGRAY)
            setPadding(0, 4, 0, 0)
        }
        titleView = titleText
        channelView = channelText

        val overlay = LinearLayout(context).apply {
            orientation = LinearLayout.VERTICAL
            setBackgroundColor(Color.parseColor("#99000000"))
            setPadding(24, 16, 24, 16)
            addView(titleText)
            addView(channelText)
            layoutParams = FrameLayout.LayoutParams(
                playerWidth, FrameLayout.LayoutParams.WRAP_CONTENT, Gravity.BOTTOM or Gravity.START
            ).apply { leftMargin = sideMargin }
            visibility = View.GONE
        }
        overlayView = overlay

        val playerFrame = FrameLayout(context).apply {
            layoutParams = FrameLayout.LayoutParams(
                playerWidth, FrameLayout.LayoutParams.MATCH_PARENT
            ).apply { leftMargin = sideMargin }
            addView(playerView!!, FrameLayout.LayoutParams(
                FrameLayout.LayoutParams.MATCH_PARENT,
                FrameLayout.LayoutParams.MATCH_PARENT
            ))
        }

        val root = object : FrameLayout(context) {
            override fun dispatchKeyEvent(event: KeyEvent): Boolean {
                if (event.action == KeyEvent.ACTION_DOWN) {
                    when (event.keyCode) {
                        KeyEvent.KEYCODE_DPAD_DOWN -> { navigateToNext(); return true }
                        KeyEvent.KEYCODE_DPAD_UP -> { navigateToPrev(); return true }
                    }
                }
                return super.dispatchKeyEvent(event)
            }
        }.apply {
            setBackgroundColor(Color.BLACK)
            isFocusable = true
            isFocusableInTouchMode = true
            addView(playerFrame)
            addView(overlay)
        }

        return root
    }

    override fun onViewCreated(view: View, savedInstanceState: Bundle?) {
        super.onViewCreated(view, savedInstanceState)
        initPlayer()
        if (videoIds.isNotEmpty()) loadShort(currentIndex)
    }

    private fun initPlayer() {
        val exoPlayer = ExoPlayer.Builder(requireContext()).build().apply {
            repeatMode = Player.REPEAT_MODE_ONE
            playWhenReady = true
            addListener(object : Player.Listener {
                override fun onPlayerError(error: PlaybackException) {
                    if (isAdded) {
                        Toast.makeText(requireContext(), "Couldn't load Short. Press ↓ to skip.", Toast.LENGTH_SHORT).show()
                    }
                }
            })
        }
        player = exoPlayer
        playerView?.player = exoPlayer
    }

    private fun loadShort(index: Int) {
        val videoId = videoIds.getOrNull(index) ?: return
        val streamUrl = "${ApiClient.BASE_URL}/api/video/$videoId/stream"
        val mediaItem = MediaItem.fromUri(Uri.parse(streamUrl))
        val dataSourceFactory = DefaultHttpDataSource.Factory()
            .setDefaultRequestProperties(mapOf(
                "X-ShieldTube-Secret" to com.shieldtube.BuildConfig.API_SECRET
            ))
        val extractorsFactory = DefaultExtractorsFactory()
            .setConstantBitrateSeekingEnabled(true)
        val mediaSource = ProgressiveMediaSource.Factory(dataSourceFactory, extractorsFactory)
            .createMediaSource(mediaItem)

        player?.let { p ->
            p.stop()
            p.setMediaSource(mediaSource)
            p.prepare()
        }

        // Fetch title/channel asynchronously — show overlay once available
        lifecycleScope.launch {
            try {
                val meta = ApiClient.api.getVideoMeta(videoId)
                titleView?.text = meta.title
                channelView?.text = meta.channelName
                showOverlay()
            } catch (_: Exception) {
                // Overlay stays hidden if metadata unavailable
            }
        }
    }

    private fun navigateToNext() {
        if (videoIds.isEmpty()) return
        currentIndex = (currentIndex + 1) % videoIds.size
        loadShort(currentIndex)
    }

    private fun navigateToPrev() {
        if (videoIds.isEmpty()) return
        currentIndex = if (currentIndex == 0) videoIds.size - 1 else currentIndex - 1
        loadShort(currentIndex)
    }

    private fun showOverlay() {
        overlayHideJob?.cancel()
        overlayView?.visibility = View.VISIBLE
        overlayHideJob = lifecycleScope.launch {
            delay(3000)
            overlayView?.visibility = View.GONE
        }
    }

    override fun onDestroyView() {
        super.onDestroyView()
        overlayHideJob?.cancel()
        player?.release()
        player = null
        playerView?.player = null
    }
}
```

- [ ] **Step 2: Verify full build**

```bash
cd /home/asjad/shieldtube/shield-app && ./gradlew assembleDebug 2>&1 | tail -5
```

Expected: `BUILD SUCCESSFUL`

- [ ] **Step 3: Commit**

```bash
cd /home/asjad/shieldtube
rtk git add shield-app/app/src/main/java/com/shieldtube/player/ShortsPlayerFragment.kt
rtk git commit -m "feat: add ShortsPlayerFragment with portrait layout, auto-loop, and D-pad navigation"
```

---

## Task 7: Deploy and verify

- [ ] **Step 1: Rebuild and deploy the backend**

```bash
cd /home/asjad/shieldtube && docker compose up -d --build shieldtube-api
```

Wait ~10 seconds for startup, then verify the new endpoints respond:

```bash
curl -sk -H "X-ShieldTube-Secret: $(grep API_SECRET .env | cut -d= -f2)" \
  https://192.168.0.26:9443/api/feed/shorts/trending | python3 -m json.tool | head -20
```

Expected: `{"feed_type": "shorts_trending", "videos": [...], ...}` (may be empty `[]` if yt-dlp scrape is slow or cache warming needed — that's OK).

- [ ] **Step 2: Install Android app on Shield TV**

```bash
cd /home/asjad/shieldtube/shield-app && ./gradlew installDebug
```

Expected: `BUILD SUCCESSFUL` and `Installed on 1 device`

- [ ] **Step 3: Verify via logcat**

```bash
adb logcat -s ShieldTube:D 2>&1 | grep -E "shorts|SHORTS|Shorts" &
```

After launching the app:
- Expected in logcat: `loadFeed: launching coroutine for header=6` and `header=7`
- Expected: `loadFeed: got N videos for header=6` (N ≥ 0)

- [ ] **Step 4: Functional check on device**

1. Navigate to "Shorts — For You" or "Shorts — Trending" row
2. Tap a Short card
3. Verify: portrait-aspect black-bar video plays, loops automatically
4. Press D-pad down — verify next Short loads
5. Press D-pad up — verify previous Short loads
6. Press Back — verify return to `BrowseFragment`
