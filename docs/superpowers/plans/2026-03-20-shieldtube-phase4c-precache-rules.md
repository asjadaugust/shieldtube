# Phase 4c: Pre-caching Rules Engine — Implementation Plan

> **For agentic workers:** Steps use checkbox (`- [ ]`) syntax for tracking. All backend — single agent, sequential tasks.

**Goal:** Automatically download videos from favorite channels based on JSON rules, triggered on feed refresh.

**Architecture:** Rules loader reads config/precache_rules.json. Rule matcher filters feed videos against rules. Download queue processes matches one at a time using existing DownloadManager. Feed endpoints trigger the check after each fresh fetch.

**Tech Stack:** Python 3.11+, FastAPI, asyncio.Queue, aiosqlite

---

## Execution Model

All backend, sequential (shared state between components):

```
Task 1: Rules loader + matcher + tests
Task 2: Download queue + tests
Task 3: Feed integration + lifespan init
```

---

## Task 1: Rules Loader + Matcher

**Files:**
- Create: `backend/services/precache.py`
- Create: `config/precache_rules.json`
- Create: `backend/tests/test_precache.py`

- [ ] **Step 1: Create example rules file**

```json
{
  "precache_rules": [
    {
      "type": "channel",
      "channel_id": "EXAMPLE_CHANNEL_ID",
      "max_videos": 5,
      "quality": "1080p",
      "trigger": "on_upload"
    }
  ]
}
```

- [ ] **Step 2: Write precache.py**

```python
# backend/services/precache.py
import json
import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


def load_rules(path: Path) -> list[dict]:
    """Read pre-cache rules from JSON file. Returns empty list on any error."""
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text())
        rules = data.get("precache_rules", [])
        # Validate required fields
        valid = []
        for rule in rules:
            if rule.get("type") == "channel" and rule.get("channel_id"):
                valid.append(rule)
            elif rule.get("type") == "playlist" and rule.get("playlist_id"):
                valid.append(rule)
            else:
                logger.warning(f"Invalid pre-cache rule skipped: {rule}")
        return valid
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to load pre-cache rules from {path}: {e}")
        return []


async def match_videos(
    videos: list[dict],
    rules: list[dict],
    db: aiosqlite.Connection,
) -> list[str]:
    """Match feed videos against rules. Return video IDs to queue for download."""
    if not rules or not videos:
        return []

    # Get already-cached video IDs
    video_ids = [v["id"] for v in videos]
    placeholders = ",".join("?" * len(video_ids))
    async with db.execute(
        f"SELECT id FROM videos WHERE id IN ({placeholders}) AND cache_status IN ('cached', 'downloading')",
        video_ids,
    ) as cursor:
        rows = await cursor.fetchall()
    already_cached = {row[0] for row in rows}

    to_queue = []
    for rule in rules:
        if rule["type"] != "channel":
            continue  # Playlist rules deferred

        channel_id = rule["channel_id"]
        max_videos = rule.get("max_videos", 5)

        matches = [
            v["id"] for v in videos
            if v.get("channel_id") == channel_id
            and v["id"] not in already_cached
            and v["id"] not in to_queue
        ]
        to_queue.extend(matches[:max_videos])

    return to_queue
```

- [ ] **Step 3: Write tests**

```python
# backend/tests/test_precache.py
import pytest
import json
import aiosqlite
from pathlib import Path

from backend.db.database import _run_migrations
from backend.services.precache import load_rules, match_videos

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


def test_load_rules_valid_file(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps({
        "precache_rules": [
            {"type": "channel", "channel_id": "UC123", "max_videos": 3}
        ]
    }))
    rules = load_rules(rules_file)
    assert len(rules) == 1
    assert rules[0]["channel_id"] == "UC123"


def test_load_rules_missing_file(tmp_path):
    assert load_rules(tmp_path / "nonexistent.json") == []


def test_load_rules_invalid_json(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text("not json")
    assert load_rules(rules_file) == []


def test_load_rules_filters_invalid_rules(tmp_path):
    rules_file = tmp_path / "rules.json"
    rules_file.write_text(json.dumps({
        "precache_rules": [
            {"type": "channel", "channel_id": "UC123"},
            {"type": "channel"},  # missing channel_id
            {"type": "unknown"},  # unknown type
        ]
    }))
    rules = load_rules(rules_file)
    assert len(rules) == 1


async def test_match_videos_finds_matching_channel(db):
    videos = [
        {"id": "v1", "channel_id": "UC123"},
        {"id": "v2", "channel_id": "UC456"},
        {"id": "v3", "channel_id": "UC123"},
    ]
    rules = [{"type": "channel", "channel_id": "UC123", "max_videos": 5}]
    result = await match_videos(videos, rules, db)
    assert result == ["v1", "v3"]


async def test_match_videos_respects_max_videos(db):
    videos = [
        {"id": f"v{i}", "channel_id": "UC123"} for i in range(10)
    ]
    rules = [{"type": "channel", "channel_id": "UC123", "max_videos": 3}]
    result = await match_videos(videos, rules, db)
    assert len(result) == 3


async def test_match_videos_excludes_cached(db):
    # Seed a cached video
    await db.execute(
        "INSERT INTO videos (id, title, channel_name, channel_id, cache_status) VALUES (?, ?, ?, ?, ?)",
        ("v1", "T", "C", "UC123", "cached"),
    )
    await db.commit()

    videos = [
        {"id": "v1", "channel_id": "UC123"},
        {"id": "v2", "channel_id": "UC123"},
    ]
    rules = [{"type": "channel", "channel_id": "UC123"}]
    result = await match_videos(videos, rules, db)
    assert result == ["v2"]


async def test_match_videos_empty_rules(db):
    videos = [{"id": "v1", "channel_id": "UC123"}]
    assert await match_videos(videos, [], db) == []


async def test_match_videos_no_matches(db):
    videos = [{"id": "v1", "channel_id": "UC456"}]
    rules = [{"type": "channel", "channel_id": "UC123"}]
    assert await match_videos(videos, rules, db) == []
```

- [ ] **Step 4: Run tests**

Run: `python -m pytest backend/tests/test_precache.py -v`
Expected: ALL pass

- [ ] **Step 5: Commit**

```bash
git add backend/services/precache.py config/precache_rules.json backend/tests/test_precache.py
git commit -m "feat: add pre-cache rules loader and video matcher"
```

---

## Task 2: Download Queue

**Files:**
- Create: `backend/services/download_queue.py`
- Create: `backend/tests/test_download_queue.py`

- [ ] **Step 1: Write download_queue.py**

```python
# backend/services/download_queue.py
import asyncio
import logging

from backend.services.download_manager import DownloadManager

logger = logging.getLogger(__name__)


class DownloadQueue:
    """Async queue that processes pre-cache downloads one at a time."""

    def __init__(self, download_manager: DownloadManager):
        self._dm = download_manager
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def start(self):
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def enqueue(self, video_id: str):
        await self._queue.put(video_id)

    async def enqueue_many(self, video_ids: list[str]):
        for vid in video_ids:
            await self._queue.put(vid)

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    async def _worker(self):
        while True:
            video_id = await self._queue.get()
            try:
                # Wait if on-demand download is active
                while self._has_active_download():
                    await asyncio.sleep(5)

                logger.info(f"Pre-cache download starting: {video_id}")
                await self._dm.get_or_start_download(video_id)
                await self._wait_for_completion(video_id)
                logger.info(f"Pre-cache download complete: {video_id}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Pre-cache download failed for {video_id}: {e}")
            finally:
                self._queue.task_done()

    def _has_active_download(self) -> bool:
        for state in self._dm._active.values():
            if state.status == "downloading":
                return True
        return False

    async def _wait_for_completion(self, video_id: str, timeout: int = 3600):
        elapsed = 0
        while elapsed < timeout:
            state = self._dm._active.get(video_id)
            if state is None or state.status in ("cached", "error"):
                return
            await asyncio.sleep(5)
            elapsed += 5
```

- [ ] **Step 2: Write tests**

```python
# backend/tests/test_download_queue.py
import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.download_queue import DownloadQueue

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_dm():
    dm = MagicMock()
    dm._active = {}
    dm.get_or_start_download = AsyncMock()
    return dm


async def test_enqueue_and_pending_count(mock_dm):
    queue = DownloadQueue(mock_dm)
    await queue.enqueue("v1")
    await queue.enqueue("v2")
    assert queue.pending_count == 2


async def test_enqueue_many(mock_dm):
    queue = DownloadQueue(mock_dm)
    await queue.enqueue_many(["v1", "v2", "v3"])
    assert queue.pending_count == 3


async def test_worker_processes_queue(mock_dm):
    queue = DownloadQueue(mock_dm)
    await queue.enqueue("v1")
    await queue.start()
    await asyncio.sleep(0.2)  # Let worker pick up item
    await queue.stop()
    mock_dm.get_or_start_download.assert_called_with("v1")


async def test_stop_cancels_worker(mock_dm):
    queue = DownloadQueue(mock_dm)
    await queue.start()
    await queue.stop()
    assert queue._worker_task.cancelled() or queue._worker_task.done()
```

- [ ] **Step 3: Run tests**

Run: `python -m pytest backend/tests/test_download_queue.py -v`
Expected: ALL pass

- [ ] **Step 4: Commit**

```bash
git add backend/services/download_queue.py backend/tests/test_download_queue.py
git commit -m "feat: add async download queue for pre-caching"
```

---

## Task 3: Feed Integration + Lifespan

**Files:**
- Modify: `backend/api/routers/feed.py`
- Modify: `backend/api/main.py`

- [ ] **Step 1: Add pre-cache check to feed.py**

After the existing thumbnail caching background task in both `home_feed()` and `subscriptions_feed()`, add:

```python
import logging
from pathlib import Path
from backend.services.precache import load_rules, match_videos

# Add helper at module level:
async def _check_precache_rules(videos: list[dict], app):
    try:
        rules = load_rules(Path("config/precache_rules.json"))
        if not rules:
            return
        db = await get_db()
        to_cache = await match_videos(videos, rules, db)
        if to_cache:
            queue = getattr(app.state, "download_queue", None)
            if queue:
                await queue.enqueue_many(to_cache)
                logging.info(f"Pre-cache: queued {len(to_cache)} videos")
    except Exception as e:
        logging.warning(f"Pre-cache rule check failed: {e}")

# In home_feed() and subscriptions_feed(), after thumbnail caching task:
if not from_cache:
    asyncio.create_task(_check_precache_rules(videos, request.app))
```

Note: `home_feed` and `subscriptions_feed` need `request: Request` parameter added to access `request.app`.

- [ ] **Step 2: Update main.py lifespan**

After DownloadManager init, add:

```python
from backend.services.download_queue import DownloadQueue

# After: app.state.download_manager = DownloadManager(db)
queue = DownloadQueue(app.state.download_manager)
await queue.start()
app.state.download_queue = queue

# In teardown (after yield, before close_db):
if hasattr(app.state, "download_queue"):
    await app.state.download_queue.stop()
```

- [ ] **Step 3: Run all tests**

Run: `python -m pytest backend/tests/ -v`
Expected: ALL pass

- [ ] **Step 4: Commit**

```bash
git add backend/api/routers/feed.py backend/api/main.py
git commit -m "feat: integrate pre-cache rules with feed endpoints and lifespan"
```
