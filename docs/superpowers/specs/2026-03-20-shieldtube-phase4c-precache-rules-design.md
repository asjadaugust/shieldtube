# Phase 4c: Pre-caching Rules Engine — Design Spec

**Type:** Design Spec
**Date:** 2026-03-20
**Status:** Draft
**Source:** [ShieldTube PRD](../../ShieldTube_PRD.md) — Phase 4: Polish + P1 Features
**Depends on:** Phase 3a Backend Progressive Download (complete — DownloadManager exists)

---

## Goal

Automatically download videos from favorite channels/playlists based on configurable JSON rules, triggered when feed endpoints fetch new videos.

**Success criteria:** Add a channel to `config/precache_rules.json` → refresh subscriptions feed → new videos from that channel auto-download in background. On-demand playback always preempts the queue.

---

## Components

4 components, all backend. Sequential implementation (small scope, shared state).

### Component 1: Rules Loader

**Purpose:** Read and validate pre-cache rules from a JSON config file.

**File:** `backend/services/precache.py`

**Config file:** `config/precache_rules.json`

```json
{
  "precache_rules": [
    {
      "type": "channel",
      "channel_id": "UCxxxxxx",
      "max_videos": 5,
      "quality": "1080p",
      "trigger": "on_upload"
    },
    {
      "type": "playlist",
      "playlist_id": "PLxxxxxx",
      "quality": "4K_HDR",
      "trigger": "nightly"
    }
  ]
}
```

**Behavior:**
- `load_rules(path: Path) -> list[dict]` — reads JSON file, returns list of rule dicts
- If file doesn't exist or is invalid JSON: return empty list, log warning
- Re-reads file on each call (no caching — allows live editing without restart)
- Validates each rule has required fields (`type`, `channel_id` or `playlist_id`)

### Component 2: Rule Matcher

**Purpose:** Given a list of videos from a feed response, determine which ones should be pre-cached based on active rules.

**Added to:** `backend/services/precache.py`

**Behavior:**
- `match_videos(videos: list[dict], rules: list[dict], db: aiosqlite.Connection) -> list[str]`
- For each rule:
  - If `type == "channel"`: filter videos where `channel_id` matches rule's `channel_id`
  - If `type == "playlist"`: (future — requires playlist membership check, skip for now)
- Limit matches per rule to `max_videos` (default 5)
- Exclude videos already cached (`cache_status == "cached"` or `"downloading"` in DB)
- Return list of video IDs to queue for download

### Component 3: Background Download Queue

**Purpose:** An async queue that processes pre-cache downloads one at a time, deferring to on-demand playback.

**File:** `backend/services/download_queue.py`

**Behavior:**

```python
class DownloadQueue:
    def __init__(self, download_manager: DownloadManager):
        self._dm = download_manager
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None
        self._paused = False

    async def start(self):
        """Start the background worker coroutine."""
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        """Stop the worker gracefully."""
        if self._worker_task:
            self._worker_task.cancel()

    async def enqueue(self, video_id: str):
        """Add a video ID to the pre-cache queue."""
        await self._queue.put(video_id)

    async def enqueue_many(self, video_ids: list[str]):
        """Add multiple video IDs to the queue."""
        for vid in video_ids:
            await self._queue.put(vid)

    async def _worker(self):
        """Process queue items one at a time."""
        while True:
            video_id = await self._queue.get()
            try:
                # Check if an on-demand download is active — wait for it
                while self._has_active_on_demand():
                    await asyncio.sleep(5)

                # Start pre-cache download
                await self._dm.get_or_start_download(video_id)

                # Wait for it to complete before starting next
                await self._wait_for_completion(video_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logging.warning(f"Pre-cache download failed for {video_id}: {e}")
            finally:
                self._queue.task_done()

    def _has_active_on_demand(self) -> bool:
        """Check if DownloadManager has an active non-queued download."""
        # Any active download that wasn't initiated by the queue
        for state in self._dm._active.values():
            if state.status == "downloading":
                return True
        return False

    async def _wait_for_completion(self, video_id: str, timeout: int = 3600):
        """Wait until a download finishes (cached or error)."""
        elapsed = 0
        while elapsed < timeout:
            state = self._dm._active.get(video_id)
            if state is None or state.status in ("cached", "error"):
                return
            await asyncio.sleep(5)
            elapsed += 5
```

**Design decisions:**
- Single worker coroutine — one download at a time
- On-demand preemption: worker checks for active non-queued downloads before starting
- Waits for each download to complete before starting the next
- Graceful shutdown via task cancellation in lifespan teardown
- Failed downloads logged and skipped (don't block the queue)

### Component 4: Feed Integration

**Purpose:** Trigger rule matching and queueing after feed refreshes.

**Modified file:** `backend/api/routers/feed.py`

**Changes:**
- After `get_home_feed()` or `get_subscriptions()` returns fresh data (not from cache):
  - Load rules via `load_rules()`
  - Call `match_videos(videos, rules, db)` to find qualifying videos
  - Call `download_queue.enqueue_many(matching_ids)` as a background task
- Access download queue via `request.app.state.download_queue`

```python
# In home_feed() and subscriptions_feed(), after upsert + thumbnail caching:
if not from_cache:
    asyncio.create_task(_check_precache_rules(videos, request.app))

async def _check_precache_rules(videos: list[dict], app):
    try:
        rules = load_rules(Path("config/precache_rules.json"))
        if rules:
            db = await get_db()
            to_cache = await match_videos(videos, rules, db)
            if to_cache:
                queue = app.state.download_queue
                await queue.enqueue_many(to_cache)
    except Exception as e:
        logging.warning(f"Pre-cache rule check failed: {e}")
```

---

## Lifespan Changes

**Modified file:** `backend/api/main.py`

In lifespan, after initializing DownloadManager:
```python
from backend.services.download_queue import DownloadQueue

queue = DownloadQueue(app.state.download_manager)
await queue.start()
app.state.download_queue = queue

# In teardown (after yield):
await app.state.download_queue.stop()
```

---

## New/Modified Files

| File | Change |
|------|--------|
| `backend/services/precache.py` | New: load_rules, match_videos |
| `backend/services/download_queue.py` | New: DownloadQueue with async worker |
| `backend/api/routers/feed.py` | Modify: trigger rule check after feed fetch |
| `backend/api/main.py` | Modify: init/stop DownloadQueue in lifespan |
| `config/precache_rules.json` | New: example rules file |
| `backend/tests/test_precache.py` | New: rule loading, matching tests |
| `backend/tests/test_download_queue.py` | New: queue + worker tests |

---

## Testing Strategy

- **Rules loader:** Test valid JSON parsed correctly. Test missing file returns empty. Test invalid JSON returns empty. Test missing required fields filtered out.
- **Rule matcher:** Test channel rule matches correct videos. Test max_videos limit. Test already-cached videos excluded. Test no rules returns empty.
- **Download queue:** Mock DownloadManager. Test enqueue and worker processes item. Test on-demand preemption pauses queue. Test worker handles errors gracefully.
- **Feed integration:** Mock precache functions. Test rule check triggered on fresh feed, not on cached feed.

---

## What This Phase Does NOT Include

- Playlist-based rules (requires playlist membership API — deferred)
- Web UI for rule management (edit JSON file directly)
- Download scheduling (nightly trigger — all rules trigger on feed refresh for now)
- Quality selection per rule (uses default quality — DownloadManager doesn't support quality override yet)
- Queue status API endpoint (can be added later)
