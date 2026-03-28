# Shorts Section — Design Spec

**Date:** 2026-03-28
**Status:** Approved

## Overview

Add a dedicated Shorts browsing experience to ShieldTube: two new rows in `BrowseFragment` ("Shorts — Following" and "Shorts — Trending") plus a `ShortsPlayerFragment` with portrait-mode playback, auto-looping, and D-pad sequential navigation.

---

## Backend

### New Endpoints

| Method | Path | Description |
|--------|------|-------------|
| `GET` | `/api/feed/shorts/subscriptions` | Shorts from subscribed channels |
| `GET` | `/api/feed/shorts/trending` | Trending Shorts from YouTube's Shorts discovery feed |

Both return the same shape as existing feed endpoints:

```json
[
  {
    "id": "VIDEO_ID",
    "title": "...",
    "channel_name": "...",
    "thumbnail_url": "...",
    "duration": 42
  }
]
```

### Data Sourcing

**Subscriptions Shorts (`/api/feed/shorts/subscriptions`):**
- Reads subscribed channel IDs from the existing DB channels table (same source as the channel feed).
- Caps at the 10 most recently active channels to keep scrape time bounded.
- For each channel, yt-dlp scrapes `youtube.com/channel/{channel_id}/shorts` and returns the top 5 Shorts.
- Results merged into a flat list (up to 50 items) and sorted by recency.
- Cached in-memory for 1 hour.

**Trending Shorts (`/api/feed/shorts/trending`):**
- yt-dlp scrapes `https://www.youtube.com/shorts` (YouTube's Shorts discovery feed).
- Returns up to 20 videos.
- Cached in-memory for 1 hour.

### New Service: `shorts_feed.py`

A new `backend/services/shorts_feed.py` handles both scrapes, reusing yt-dlp options (cookies, proxy) from `settings`. Scraped data is normalised into the shared video metadata shape before returning.

---

## Android

### BrowseFragment — New Rows

Two new row constants added to `BrowseFragment`:

```kotlin
private val SHORTS_SUBS = 6       // "Shorts — Following"
private val SHORTS_TRENDING = 7   // "Shorts — Trending"
```

Rows are positioned above the existing content rows so Shorts appear near the top of the browse screen. Each row loads from its respective endpoint via the existing `ApiClient` pattern.

### ShortsCardPresenter

A new `ShortsCardPresenter` (alongside the existing `CardPresenter`) renders portrait-aspect cards:
- Dimensions: ~120×213dp (9:16 ratio, vs 320×180dp for landscape cards)
- Same `ImageCardView` base — title and channel name below the card
- Thumbnails fetched via the existing `/api/video/{id}/thumbnail` endpoint

### New API calls

Two new methods on `ShieldTubeApi`:

```kotlin
@GET("api/feed/shorts/subscriptions")
suspend fun getShortsSubscriptions(): List<VideoMeta>

@GET("api/feed/shorts/trending")
suspend fun getShortsTrending(): List<VideoMeta>
```

`VideoMeta` is the existing model — no new data model needed.

---

## ShortsPlayerFragment

### Entry Point

`BrowseFragment` passes two arguments when launching:
- `videoIds: ArrayList<String>` — full ordered list of video IDs from the selected row
- `startIndex: Int` — index of the tapped Short

### Layout

```
┌─────────────────────────────────────────────────┐
│  (black)   ┌──────────┐   (black)               │
│            │          │                          │
│            │  9:16    │                          │
│            │ PlayerView│                         │
│            │          │                          │
│            │[title   ]│  ← semi-transparent      │
│            │[channel ]│     overlay, fades 3s    │
│            └──────────┘                          │
└─────────────────────────────────────────────────┘
```

- `PlayerView` width = 56.25% of screen width (maintains 9:16 on 16:9 display), full height
- Black background fills remaining space

### Playback

- ExoPlayer with `repeatMode = Player.REPEAT_MODE_ONE` — each Short loops until user navigates
- Stream loaded via existing `/api/video/{id}/stream` endpoint (same as `PlaybackFragment`)
- No prefetching in initial implementation

### D-pad Navigation

| Key | Action |
|-----|--------|
| `DPAD_DOWN` | Advance to next Short (wraps to index 0 at end of list) |
| `DPAD_UP` | Go to previous Short (wraps to last at index 0) |
| `BACK` | Stop playback, return to `BrowseFragment` |

Navigation stops the current player, loads the new video ID, and restarts playback. Title/channel overlay reappears briefly on each transition.

---

## Error Handling

- If a Shorts feed endpoint returns an error, the row is hidden (same pattern as existing feed rows)
- If a Short fails to load in the player, a toast is shown and D-pad navigation remains functional to skip to the next Short
- 401 responses show a toast (consistent with the fix applied to existing feed rows — no redirect to LoginFragment)

---

## Out of Scope

- Prefetching adjacent Shorts
- Like/comment counts on Short cards
- Shorts-specific recommendations ("more like this")
- Download support for Shorts (can be added later via existing download queue)
