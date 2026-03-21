# Recommendation Engine Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Build a recommendation system that uses local watch history embeddings to surface personalized video suggestions, pre-download likely videos, and fall back to SQL heuristics when the ML batch job hasn't run.

**Architecture:** Three-component system: (1) NAS backend — serves recommendations, manages throttled pre-downloads, computes watch signals in real-time, provides heuristic fallback; (2) Laptop batch job (`rec_engine/`) — embeds video metadata, builds user profile vector, scores candidates, syncs results via API; (3) Shield TV app — displays "For You" row, sends enriched progress signals, caches recommendation UI state.

**Tech Stack:** Python/FastAPI/SQLite (backend), sentence-transformers/httpx (rec-engine), Kotlin/Leanback/Retrofit (app)

**Spec:** `docs/superpowers/specs/2026-03-21-recommendation-engine-design.md`

---

## File Map

### Backend — New Files
| File | Responsibility |
|---|---|
| `backend/db/migrations/005_recommendations.sql` | Schema: recommendations, recommendation_runs, watch_signals tables + videos.cached_at |
| `backend/api/routers/recommend.py` | Endpoints: /feed/recommended, /recommendations/sync, /recommendations/status, /download/enqueue-batch, /download/bandwidth |
| `backend/services/heuristic_rec.py` | SQL-based fallback recommender (channel affinity + recency + completion) |
| `backend/services/watch_signal_aggregator.py` | Real-time computation of engagement metrics from progress events |
| `backend/services/bandwidth.py` | Configurable download rate limiting with schedule support |

### Backend — Modified Files
| File | Changes |
|---|---|
| `backend/api/routers/watch.py` | Accept optional `event`, `speed` in ProgressBody; call signal aggregator |
| `backend/api/main.py` | Register recommend router, initialize bandwidth manager |
| `backend/api/middleware.py` | No changes needed (new endpoints require API secret) |
| `backend/db/repositories.py` | Add `RecommendationRepo`, `WatchSignalRepo` |
| `backend/db/models.py` | Add `Recommendation`, `RecommendationRun`, `WatchSignal` dataclasses |

### Backend — New Tests
| File | What it tests |
|---|---|
| `backend/tests/test_watch_signals.py` | Signal aggregation from progress events |
| `backend/tests/test_heuristic_rec.py` | Heuristic recommender scoring logic |
| `backend/tests/test_recommend_endpoints.py` | /feed/recommended, /recommendations/sync, /recommendations/status endpoints |

### App — Modified Files
| File | Changes |
|---|---|
| `shield-app/.../api/models.kt` | Add `pre_cached` to Video, add `event`/`speed` to ProgressBody, add `source`/`freshness` to FeedResponse |
| `shield-app/.../api/ShieldTubeApi.kt` | Add `getFeedRecommended()` endpoint |
| `shield-app/.../ui/BrowseFragment.kt` | Add "For You" row, file-based cache for recommendations |
| `shield-app/.../player/PlaybackFragment.kt` | Send enriched progress events (event type, speed) |

### Rec-Engine — New Files (entire directory)
| File | Responsibility |
|---|---|
| `rec_engine/__main__.py` | CLI entry point: run, embed, status subcommands |
| `rec_engine/config.yaml` | Model preferences, thresholds, NAS URL |
| `rec_engine/embedder.py` | Adaptive model loading, video text embedding |
| `rec_engine/scorer.py` | User profile vector, candidate scoring |
| `rec_engine/candidates.py` | Fetch candidates via yt-dlp related videos + API |
| `rec_engine/sync.py` | HTTPS client for NAS backend (auth, sync, enqueue) |
| `rec_engine/requirements.txt` | Dependencies |
| `rec_engine/tests/test_embedder.py` | Model selection, embedding computation |
| `rec_engine/tests/test_scorer.py` | Profile building, scoring math |

---

## Task 1: Database Migration

**Files:**
- Create: `backend/db/migrations/005_recommendations.sql`

- [ ] **Step 1: Write the migration**

```sql
-- Tracks batch job runs for staleness detection and atomic swaps
CREATE TABLE IF NOT EXISTS recommendation_runs (
    run_id TEXT PRIMARY KEY,
    run_at TEXT NOT NULL DEFAULT CURRENT_TIMESTAMP,
    source TEXT NOT NULL,
    model_name TEXT,
    video_count INTEGER DEFAULT 0
);

-- Ranked recommendations, keyed by run for atomic replacement
CREATE TABLE IF NOT EXISTS recommendations (
    video_id TEXT NOT NULL,
    run_id TEXT NOT NULL,
    score REAL NOT NULL,
    source TEXT NOT NULL DEFAULT 'ml',
    reason TEXT,
    created_at TEXT DEFAULT CURRENT_TIMESTAMP,
    PRIMARY KEY (video_id, run_id),
    FOREIGN KEY (run_id) REFERENCES recommendation_runs(run_id)
);

CREATE INDEX IF NOT EXISTS idx_recommendations_score ON recommendations(run_id, score DESC);

-- Per-session watch engagement signals
CREATE TABLE IF NOT EXISTS watch_signals (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    video_id TEXT NOT NULL,
    session_start TEXT NOT NULL,
    completion_rate REAL DEFAULT 0,
    pause_count INTEGER DEFAULT 0,
    seek_forward_count INTEGER DEFAULT 0,
    avg_playback_speed REAL DEFAULT 1.0,
    time_of_day INTEGER,
    abandoned_at_pct REAL,
    updated_at TEXT DEFAULT CURRENT_TIMESTAMP
);

CREATE INDEX IF NOT EXISTS idx_watch_signals_video ON watch_signals(video_id);

-- Track when videos were pre-cached for eviction lifecycle
ALTER TABLE videos ADD COLUMN cached_at TEXT;
```

- [ ] **Step 2: Verify migration runs**

Run: `python -c "import asyncio; from backend.db.database import init_db; asyncio.run(init_db())"`
Expected: No errors, tables created

- [ ] **Step 3: Commit**

```bash
git add backend/db/migrations/005_recommendations.sql
git commit -m "feat(db): add recommendations, watch_signals tables and videos.cached_at"
```

---

## Task 2: Data Models

**Files:**
- Modify: `backend/db/models.py`

- [ ] **Step 1: Add new dataclasses**

Add after `WatchHistoryEntry`:

```python
@dataclass
class RecommendationRun:
    run_id: str
    run_at: str
    source: str
    model_name: str | None = None
    video_count: int = 0


@dataclass
class Recommendation:
    video_id: str
    run_id: str
    score: float
    source: str = "ml"
    reason: str | None = None
    created_at: str | None = None


@dataclass
class WatchSignal:
    id: int | None = None
    video_id: str = ""
    session_start: str = ""
    completion_rate: float = 0.0
    pause_count: int = 0
    seek_forward_count: int = 0
    avg_playback_speed: float = 1.0
    time_of_day: int | None = None
    abandoned_at_pct: float | None = None
    updated_at: str | None = None
```

- [ ] **Step 2: Commit**

```bash
git add backend/db/models.py
git commit -m "feat(models): add Recommendation, RecommendationRun, WatchSignal dataclasses"
```

---

## Task 3: Repositories

**Files:**
- Modify: `backend/db/repositories.py`
- Test: `backend/tests/test_repositories.py`

- [ ] **Step 1: Write failing tests for RecommendationRepo**

Create test cases in `backend/tests/test_repositories.py` (append to existing file):

```python
@pytest.mark.asyncio
async def test_recommendation_repo_upsert_run_and_get_latest(db):
    repo = RecommendationRepo(db)
    await repo.upsert_run(RecommendationRun(
        run_id="run-001", run_at="2026-03-21T00:00:00Z",
        source="ml", model_name="all-MiniLM-L6-v2", video_count=3,
    ))
    await repo.upsert_recommendations("run-001", [
        Recommendation(video_id="v1", run_id="run-001", score=0.9, reason="test"),
        Recommendation(video_id="v2", run_id="run-001", score=0.7, reason="test"),
    ])
    latest = await repo.get_latest_run()
    assert latest is not None
    assert latest.run_id == "run-001"
    recs = await repo.get_recommendations(limit=10)
    assert len(recs) == 2
    assert recs[0].score >= recs[1].score


@pytest.mark.asyncio
async def test_watch_signal_repo_upsert_and_get(db):
    repo = WatchSignalRepo(db)
    signal = WatchSignal(
        video_id="v1", session_start="2026-03-21T00:00:00Z",
        completion_rate=0.85, pause_count=2, time_of_day=14,
    )
    await repo.upsert(signal)
    signals = await repo.get_for_video("v1")
    assert len(signals) == 1
    assert signals[0].completion_rate == 0.85
    assert signals[0].pause_count == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_repositories.py::test_recommendation_repo_upsert_run_and_get_latest -v`
Expected: FAIL — `RecommendationRepo` not defined

- [ ] **Step 3: Implement RecommendationRepo and WatchSignalRepo**

Add to `backend/db/repositories.py`:

```python
class RecommendationRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert_run(self, run: RecommendationRun) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO recommendation_runs (run_id, run_at, source, model_name, video_count)"
            " VALUES (?, ?, ?, ?, ?)",
            (run.run_id, run.run_at, run.source, run.model_name, run.video_count),
        )
        await self._db.commit()

    async def upsert_recommendations(self, run_id: str, recs: list[Recommendation]) -> None:
        for rec in recs:
            await self._db.execute(
                "INSERT OR REPLACE INTO recommendations (video_id, run_id, score, source, reason)"
                " VALUES (?, ?, ?, ?, ?)",
                (rec.video_id, run_id, rec.score, rec.source, rec.reason),
            )
        await self._db.commit()

    async def get_latest_run(self) -> RecommendationRun | None:
        async with self._db.execute(
            "SELECT * FROM recommendation_runs ORDER BY run_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return RecommendationRun(
            run_id=row["run_id"], run_at=row["run_at"], source=row["source"],
            model_name=row["model_name"], video_count=row["video_count"],
        )

    async def get_recommendations(self, run_id: str | None = None, limit: int = 50) -> list[Recommendation]:
        if run_id is None:
            latest = await self.get_latest_run()
            if latest is None:
                return []
            run_id = latest.run_id
        async with self._db.execute(
            "SELECT * FROM recommendations WHERE run_id = ? ORDER BY score DESC LIMIT ?",
            (run_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            Recommendation(
                video_id=r["video_id"], run_id=r["run_id"], score=r["score"],
                source=r["source"], reason=r["reason"], created_at=r["created_at"],
            )
            for r in rows
        ]


class WatchSignalRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert(self, signal: WatchSignal) -> None:
        await self._db.execute(
            """INSERT INTO watch_signals
               (video_id, session_start, completion_rate, pause_count,
                seek_forward_count, avg_playback_speed, time_of_day, abandoned_at_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (signal.video_id, signal.session_start, signal.completion_rate,
             signal.pause_count, signal.seek_forward_count, signal.avg_playback_speed,
             signal.time_of_day, signal.abandoned_at_pct),
        )
        await self._db.commit()

    async def get_for_video(self, video_id: str) -> list[WatchSignal]:
        async with self._db.execute(
            "SELECT * FROM watch_signals WHERE video_id = ? ORDER BY session_start DESC",
            (video_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            WatchSignal(
                id=r["id"], video_id=r["video_id"], session_start=r["session_start"],
                completion_rate=r["completion_rate"], pause_count=r["pause_count"],
                seek_forward_count=r["seek_forward_count"],
                avg_playback_speed=r["avg_playback_speed"],
                time_of_day=r["time_of_day"], abandoned_at_pct=r["abandoned_at_pct"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]
```

Also add imports: `from backend.db.models import Recommendation, RecommendationRun, WatchSignal`

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/test_repositories.py::test_recommendation_repo_upsert_run_and_get_latest backend/tests/test_repositories.py::test_watch_signal_repo_upsert_and_get -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/db/repositories.py backend/tests/test_repositories.py
git commit -m "feat(repos): add RecommendationRepo and WatchSignalRepo"
```

---

## Task 4: Watch Signal Aggregator

**Files:**
- Create: `backend/services/watch_signal_aggregator.py`
- Test: `backend/tests/test_watch_signals.py`

- [ ] **Step 1: Write failing test**

```python
"""Tests for watch signal aggregation from progress events."""
import pytest
import aiosqlite
from datetime import datetime, timezone

from backend.db.database import _run_migrations
from backend.services.watch_signal_aggregator import WatchSignalAggregator

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


async def test_process_playing_event_creates_session(db):
    agg = WatchSignalAggregator(db)
    await agg.process_event("v1", position_seconds=10, duration=600,
                            event="playing", speed=1.0)
    signals = await agg.get_signals("v1")
    assert len(signals) == 1
    assert signals[0].avg_playback_speed == 1.0


async def test_process_paused_increments_pause_count(db):
    agg = WatchSignalAggregator(db)
    await agg.process_event("v1", position_seconds=10, duration=600,
                            event="playing", speed=1.0)
    await agg.process_event("v1", position_seconds=30, duration=600,
                            event="paused", speed=1.0)
    signals = await agg.get_signals("v1")
    assert signals[0].pause_count == 1


async def test_process_completed_sets_completion_rate(db):
    agg = WatchSignalAggregator(db)
    await agg.process_event("v1", position_seconds=10, duration=600,
                            event="playing", speed=1.0)
    await agg.process_event("v1", position_seconds=570, duration=600,
                            event="completed", speed=1.0)
    signals = await agg.get_signals("v1")
    assert signals[0].completion_rate == pytest.approx(0.95, abs=0.01)


async def test_process_abandoned_sets_abandoned_pct(db):
    agg = WatchSignalAggregator(db)
    await agg.process_event("v1", position_seconds=10, duration=600,
                            event="playing", speed=1.0)
    await agg.process_event("v1", position_seconds=180, duration=600,
                            event="abandoned", speed=1.0)
    signals = await agg.get_signals("v1")
    assert signals[0].abandoned_at_pct == pytest.approx(0.3, abs=0.01)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_watch_signals.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement WatchSignalAggregator**

Create `backend/services/watch_signal_aggregator.py`:

```python
"""Real-time aggregation of watch engagement signals from progress events."""

from datetime import datetime, timezone

import aiosqlite


class WatchSignalAggregator:
    """Processes progress events and maintains per-session engagement metrics."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db
        # In-memory session state: video_id -> {session_start, pause_count, seek_fwd, speeds}
        self._sessions: dict[str, dict] = {}

    async def process_event(
        self,
        video_id: str,
        position_seconds: int,
        duration: int,
        event: str | None = None,
        speed: float | None = None,
    ) -> None:
        if event is None:
            event = "playing"
        if speed is None:
            speed = 1.0

        session = self._sessions.get(video_id)
        if session is None:
            session = {
                "session_start": datetime.now(timezone.utc).isoformat(),
                "pause_count": 0,
                "seek_forward_count": 0,
                "speeds": [speed],
                "last_position": position_seconds,
                "time_of_day": datetime.now(timezone.utc).hour,
            }
            self._sessions[video_id] = session

        if event == "paused":
            session["pause_count"] += 1
        elif event == "seeked":
            if position_seconds > session["last_position"]:
                session["seek_forward_count"] += 1
        elif event in ("completed", "abandoned"):
            completion_rate = position_seconds / duration if duration > 0 else 0.0
            abandoned_at_pct = (position_seconds / duration if duration > 0 else None) if event == "abandoned" else None
            avg_speed = sum(session["speeds"]) / len(session["speeds"])

            await self._db.execute(
                """INSERT INTO watch_signals
                   (video_id, session_start, completion_rate, pause_count,
                    seek_forward_count, avg_playback_speed, time_of_day, abandoned_at_pct)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
                (video_id, session["session_start"], completion_rate,
                 session["pause_count"], session["seek_forward_count"],
                 avg_speed, session["time_of_day"], abandoned_at_pct),
            )
            await self._db.commit()
            del self._sessions[video_id]
            return

        session["speeds"].append(speed)
        session["last_position"] = position_seconds

        # Persist partial signals periodically (every 5th playing event)
        # so data isn't lost if the app or backend restarts mid-playback
        session["event_count"] = session.get("event_count", 0) + 1
        if event == "playing" and session["event_count"] % 5 == 0:
            completion_rate = position_seconds / duration if duration > 0 else 0.0
            avg_speed = sum(session["speeds"]) / len(session["speeds"])
            await self._db.execute(
                """INSERT OR REPLACE INTO watch_signals
                   (video_id, session_start, completion_rate, pause_count,
                    seek_forward_count, avg_playback_speed, time_of_day, abandoned_at_pct)
                   VALUES (?, ?, ?, ?, ?, ?, ?, NULL)""",
                (video_id, session["session_start"], completion_rate,
                 session["pause_count"], session["seek_forward_count"],
                 avg_speed, session["time_of_day"]),
            )
            await self._db.commit()

    async def get_signals(self, video_id: str) -> list:
        from backend.db.repositories import WatchSignalRepo
        repo = WatchSignalRepo(self._db)
        return await repo.get_for_video(video_id)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/test_watch_signals.py -v`
Expected: PASS (4 tests)

- [ ] **Step 5: Commit**

```bash
git add backend/services/watch_signal_aggregator.py backend/tests/test_watch_signals.py
git commit -m "feat: add WatchSignalAggregator for real-time engagement metrics"
```

---

## Task 5: Enhanced Progress Endpoint

**Files:**
- Modify: `backend/api/routers/watch.py`
- Modify: `backend/api/main.py`

- [ ] **Step 1: Update ProgressBody Pydantic model in watch.py**

Find the `ProgressBody` model in `watch.py` and add optional fields:

```python
class ProgressBody(BaseModel):
    position_seconds: int
    duration: int
    event: str | None = None   # playing, paused, seeked, completed, abandoned
    speed: float | None = None  # playback speed multiplier
```

- [ ] **Step 2: Update the progress endpoint to call signal aggregator**

In the `report_progress` function, after the existing watch history upsert, add:

```python
# Aggregate watch signal if event data is present
if body.event is not None:
    aggregator = getattr(request.app.state, "signal_aggregator", None)
    if aggregator:
        await aggregator.process_event(
            video_id, body.position_seconds, body.duration,
            event=body.event, speed=body.speed,
        )
```

- [ ] **Step 3: Initialize signal aggregator in main.py lifespan**

In `backend/api/main.py`, add to the lifespan function after the feed refresher init:

```python
from backend.services.watch_signal_aggregator import WatchSignalAggregator
app.state.signal_aggregator = WatchSignalAggregator(db)
```

- [ ] **Step 4: Verify existing progress tests still pass**

Run: `pytest backend/tests/ -k "progress" -v`
Expected: existing tests PASS (new fields are optional, backwards-compatible)

- [ ] **Step 5: Commit**

```bash
git add backend/api/routers/watch.py backend/api/main.py
git commit -m "feat: enhance progress endpoint with event/speed fields for watch signals"
```

---

## Task 6: Heuristic Recommender

**Files:**
- Create: `backend/services/heuristic_rec.py`
- Test: `backend/tests/test_heuristic_rec.py`

- [ ] **Step 1: Write failing tests**

```python
"""Tests for SQL-based heuristic recommender."""
import pytest
import aiosqlite
from backend.db.database import _run_migrations
from backend.services.heuristic_rec import HeuristicRecommender

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()

async def _seed_data(db):
    """Insert watch history and subscription videos for testing."""
    # User watched 3 videos from channel A, 1 from channel B
    for vid, ch in [("w1","chA"),("w2","chA"),("w3","chA"),("w4","chB")]:
        await db.execute(
            "INSERT INTO videos (id, title, channel_name, channel_id) VALUES (?,?,?,?)",
            (vid, f"Title {vid}", f"Channel {ch}", ch))
        await db.execute(
            "INSERT INTO watch_history (video_id, watched_at, position_seconds, duration, completed)"
            " VALUES (?, datetime('now'), 500, 600, 1)", (vid,))
    # Candidate videos (not watched): 2 from channel A, 1 from channel C
    for vid, ch in [("c1","chA"),("c2","chA"),("c3","chC")]:
        await db.execute(
            "INSERT INTO videos (id, title, channel_name, channel_id, published_at) VALUES (?,?,?,?,datetime('now'))",
            (vid, f"Candidate {vid}", f"Channel {ch}", ch))
    await db.commit()

async def test_heuristic_recommends_from_top_channels(db):
    await _seed_data(db)
    rec = HeuristicRecommender(db)
    results = await rec.get_recommendations(limit=10)
    video_ids = [r["id"] for r in results]
    # Should rank channel A videos higher (3 watches vs 1 for B, 0 for C)
    assert "c1" in video_ids
    assert "c2" in video_ids
    # c1 and c2 should appear before c3
    if "c3" in video_ids:
        assert video_ids.index("c1") < video_ids.index("c3")

async def test_heuristic_excludes_watched_videos(db):
    await _seed_data(db)
    rec = HeuristicRecommender(db)
    results = await rec.get_recommendations(limit=10)
    video_ids = [r["id"] for r in results]
    for watched in ["w1", "w2", "w3", "w4"]:
        assert watched not in video_ids
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_heuristic_rec.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement HeuristicRecommender**

Create `backend/services/heuristic_rec.py`:

```python
"""SQL-based heuristic recommender — runs on NAS with zero ML dependencies."""

import aiosqlite


class HeuristicRecommender:
    """Ranks candidate videos using channel affinity, freshness, and completion history."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get_recommendations(self, limit: int = 50) -> list[dict]:
        query = """
        WITH channel_stats AS (
            SELECT
                v.channel_id,
                COUNT(*) as watch_count,
                AVG(wh.completed) as avg_completion
            FROM watch_history wh
            JOIN videos v ON v.id = wh.video_id
            GROUP BY v.channel_id
        ),
        candidates AS (
            SELECT v.*
            FROM videos v
            WHERE v.id NOT IN (SELECT video_id FROM watch_history)
              AND v.published_at IS NOT NULL
        )
        SELECT
            c.id, c.title, c.channel_name, c.channel_id,
            c.view_count, c.duration, c.published_at,
            COALESCE(cs.watch_count, 0) as channel_watches,
            COALESCE(cs.avg_completion, 0) as channel_completion,
            -- Channel affinity: 0-1 normalized
            COALESCE(cs.watch_count * 1.0 / (SELECT MAX(watch_count) FROM channel_stats), 0) as channel_affinity,
            -- Freshness: linear decay over 48 hours
            CASE
                WHEN c.published_at IS NOT NULL THEN
                    MAX(0, 1.0 - (julianday('now') - julianday(c.published_at)) / 2.0)
                ELSE 0
            END as freshness
        FROM candidates c
        LEFT JOIN channel_stats cs ON c.channel_id = cs.channel_id
        """
        async with self._db.execute(query) as cursor:
            rows = await cursor.fetchall()

        import math
        results = []
        for r in rows:
            ch_affinity = r["channel_affinity"] or 0
            freshness = r["freshness"] or 0
            views = r["view_count"] or 0
            # Popularity: log-scaled in Python (SQLite has no LOG function)
            popularity = min(1.0, math.log(views + 1) / 20.0) if views > 0 else 0.0
            score = (0.5 * ch_affinity) + (0.3 * freshness) + (0.2 * popularity)
            results.append({
                "id": r["id"],
                "title": r["title"],
                "channel_name": r["channel_name"],
                "channel_id": r["channel_id"],
                "view_count": r["view_count"],
                "duration": r["duration"],
                "published_at": r["published_at"],
                "score": score,
            })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `pytest backend/tests/test_heuristic_rec.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add backend/services/heuristic_rec.py backend/tests/test_heuristic_rec.py
git commit -m "feat: add SQL-based heuristic recommender for NAS fallback"
```

---

## Task 7: Recommendation API Endpoints

**Files:**
- Create: `backend/api/routers/recommend.py`
- Test: `backend/tests/test_recommend_endpoints.py`

- [ ] **Step 1: Write failing endpoint tests**

```python
"""Tests for recommendation API endpoints."""
from __future__ import annotations
import pytest
import aiosqlite
from httpx import AsyncClient, ASGITransport
from unittest.mock import AsyncMock, patch
from backend.db.database import _run_migrations

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def mem_db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()

@pytest.fixture
async def client(mem_db):
    from backend.api.main import app
    async def _fake_get_db():
        return mem_db
    with (
        patch("backend.db.database.init_db", new_callable=AsyncMock),
        patch("backend.db.database.close_db", new_callable=AsyncMock),
        patch("backend.api.routers.recommend.get_db", new=_fake_get_db),
        patch("backend.services.heuristic_rec.get_db", side_effect=_fake_get_db),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

async def test_recommended_feed_returns_heuristic_when_no_ml(client, mem_db):
    """With no ML recommendations, falls back to heuristic."""
    resp = await client.get("/api/feed/recommended")
    assert resp.status_code == 200
    data = resp.json()
    assert data["feed_type"] == "recommended"
    assert data["source"] in ("heuristic", "ml", "blended")

async def test_recommendations_status_empty(client):
    resp = await client.get("/api/recommendations/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["last_updated"] is None
    assert data["source"] is None

async def test_recommendations_sync_stores_results(client, mem_db):
    payload = {
        "run_id": "test-run-001",
        "model_name": "all-MiniLM-L6-v2",
        "videos": [
            {"id": "v1", "score": 0.9, "reason": "similar content"},
            {"id": "v2", "score": 0.7, "reason": "channel affinity"},
        ],
    }
    resp = await client.post("/api/recommendations/sync", json=payload)
    assert resp.status_code == 200
    # Verify stored
    status = await client.get("/api/recommendations/status")
    assert status.json()["last_updated"] is not None
    assert status.json()["count"] == 2
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `pytest backend/tests/test_recommend_endpoints.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement recommend.py router**

Create `backend/api/routers/recommend.py`:

```python
"""Recommendation endpoints: serve, sync, and status."""
from datetime import datetime, timezone, timedelta
from fastapi import APIRouter, Request
from pydantic import BaseModel

from backend.db.database import get_db
from backend.db.repositories import RecommendationRepo, VideoRepo
from backend.db.models import Recommendation, RecommendationRun
from backend.services.heuristic_rec import HeuristicRecommender

router = APIRouter()

STALENESS_ML_ONLY = timedelta(hours=3)
STALENESS_BLENDED = timedelta(hours=5)


class SyncVideoItem(BaseModel):
    id: str
    score: float
    reason: str | None = None
    title: str = ""
    channel_name: str = ""
    channel_id: str = ""
    view_count: int | None = None
    duration: int | None = None
    published_at: str | None = None


class SyncPayload(BaseModel):
    run_id: str
    model_name: str | None = None
    videos: list[SyncVideoItem]


@router.get("/feed/recommended")
async def get_recommended_feed():
    db = await get_db()
    rec_repo = RecommendationRepo(db)
    latest_run = await rec_repo.get_latest_run()

    now = datetime.now(timezone.utc)
    ml_recs = []
    source = "heuristic"

    if latest_run:
        run_at = datetime.fromisoformat(latest_run.run_at)
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        age = now - run_at

        if age < STALENESS_ML_ONLY:
            ml_recs = await rec_repo.get_recommendations(limit=50)
            source = "ml"
        elif age < STALENESS_BLENDED:
            ml_recs = await rec_repo.get_recommendations(limit=35)
            source = "blended"

    heuristic_recs = []
    if source in ("heuristic", "blended"):
        heuristic = HeuristicRecommender(db)
        limit = 50 if source == "heuristic" else 15
        heuristic_recs = await heuristic.get_recommendations(limit=limit)

    # Merge: ML first, then heuristic (deduplicated)
    seen_ids = set()
    videos = []
    for rec in ml_recs:
        seen_ids.add(rec.video_id)
        videos.append({
            "id": rec.video_id, "title": "", "channel_name": "", "channel_id": "",
            "view_count": None, "duration": None, "published_at": None,
            "thumbnail_url": f"/api/video/{rec.video_id}/thumbnail?res=maxres",
            "score": rec.score, "pre_cached": False,
        })
    for rec in heuristic_recs:
        if rec["id"] not in seen_ids:
            seen_ids.add(rec["id"])
            videos.append({
                "id": rec["id"], "title": rec["title"],
                "channel_name": rec["channel_name"], "channel_id": rec["channel_id"],
                "view_count": rec["view_count"], "duration": rec["duration"],
                "published_at": rec["published_at"],
                "thumbnail_url": f"/api/video/{rec['id']}/thumbnail?res=maxres",
                "score": rec.get("score", 0), "pre_cached": False,
            })

    # Enrich ML recs with video metadata from DB
    if ml_recs:
        video_repo = VideoRepo(db)
        ml_ids = [r.video_id for r in ml_recs]
        db_videos = await video_repo.get_many(ml_ids)
        db_map = {v.id: v for v in db_videos}
        for v in videos:
            if v["id"] in db_map:
                dbv = db_map[v["id"]]
                v["title"] = dbv.title
                v["channel_name"] = dbv.channel_name
                v["channel_id"] = dbv.channel_id
                v["view_count"] = dbv.view_count
                v["duration"] = dbv.duration
                v["published_at"] = dbv.published_at
                v["pre_cached"] = dbv.cache_status == "pre-cached"

    freshness = None
    if latest_run:
        run_at = datetime.fromisoformat(latest_run.run_at)
        if run_at.tzinfo is None:
            run_at = run_at.replace(tzinfo=timezone.utc)
        delta = now - run_at
        hours = int(delta.total_seconds() // 3600)
        freshness = f"{hours}h ago" if hours > 0 else "just now"

    return {
        "feed_type": "recommended",
        "videos": videos,
        "source": source,
        "freshness": freshness,
        "from_cache": False,
    }


@router.get("/recommendations/status")
async def get_recommendations_status():
    db = await get_db()
    rec_repo = RecommendationRepo(db)
    latest_run = await rec_repo.get_latest_run()
    if latest_run is None:
        return {"last_updated": None, "source": None, "count": 0, "model": None}
    return {
        "last_updated": latest_run.run_at,
        "source": latest_run.source,
        "count": latest_run.video_count,
        "model": latest_run.model_name,
    }


@router.post("/recommendations/sync")
async def sync_recommendations(payload: SyncPayload):
    db = await get_db()
    rec_repo = RecommendationRepo(db)

    run = RecommendationRun(
        run_id=payload.run_id,
        run_at=datetime.now(timezone.utc).isoformat(),
        source="ml",
        model_name=payload.model_name,
        video_count=len(payload.videos),
    )
    await rec_repo.upsert_run(run)

    recs = [
        Recommendation(
            video_id=v.id, run_id=payload.run_id,
            score=v.score, source="ml", reason=v.reason,
        )
        for v in payload.videos
    ]
    await rec_repo.upsert_recommendations(payload.run_id, recs)

    # Persist video metadata so the feed endpoint can serve full cards
    video_repo = VideoRepo(db)
    for v in payload.videos:
        if v.title:  # Only persist if metadata is provided
            from backend.db.models import Video
            await video_repo.upsert(Video(
                id=v.id, title=v.title, channel_name=v.channel_name,
                channel_id=v.channel_id, view_count=v.view_count,
                duration=v.duration, published_at=v.published_at,
            ))

    return {"status": "ok", "count": len(recs)}
```

- [ ] **Step 4: Register router in main.py**

In `backend/api/main.py`, add:

```python
from backend.api.routers import recommend
app.include_router(recommend.router, prefix="/api")
```

- [ ] **Step 5: Run tests to verify they pass**

Run: `pytest backend/tests/test_recommend_endpoints.py -v`
Expected: PASS

- [ ] **Step 6: Commit**

```bash
git add backend/api/routers/recommend.py backend/tests/test_recommend_endpoints.py backend/api/main.py
git commit -m "feat: add recommendation API endpoints (feed, sync, status)"
```

---

## Task 8: Bandwidth Manager & Batch Download Endpoint

**Files:**
- Create: `backend/services/bandwidth.py`
- Modify: `backend/api/routers/recommend.py` (add download endpoints)

- [ ] **Step 1: Implement BandwidthManager**

Create `backend/services/bandwidth.py`:

```python
"""Configurable download rate limiting."""

import asyncio
import time


class BandwidthManager:
    """Token-bucket rate limiter for pre-cache downloads."""

    def __init__(self, rate_mbps: float = 10.0) -> None:
        self._rate_mbps = rate_mbps
        self._throttled = False

    @property
    def rate_mbps(self) -> float:
        return self._rate_mbps

    @rate_mbps.setter
    def rate_mbps(self, value: float) -> None:
        self._rate_mbps = max(0.5, value)

    @property
    def throttled(self) -> bool:
        return self._throttled

    def status(self) -> dict:
        return {
            "rate_mbps": self._rate_mbps,
            "throttled": self._throttled,
        }
```

- [ ] **Step 2: Add bandwidth and batch download endpoints to recommend.py**

Append to `backend/api/routers/recommend.py`:

```python
class EnqueueBatchPayload(BaseModel):
    videos: list[SyncVideoItem]
    threshold: float = 0.7


@router.post("/download/enqueue-batch")
async def enqueue_batch_download(payload: EnqueueBatchPayload, request: Request):
    queue = getattr(request.app.state, "download_queue", None)
    if queue is None:
        return {"status": "error", "message": "Download queue not available"}

    above_threshold = [v for v in payload.videos if v.score >= payload.threshold]
    above_threshold.sort(key=lambda v: v.score, reverse=True)

    # Skip already-cached videos
    db = await get_db()
    video_repo = VideoRepo(db)
    enqueued = []
    for v in above_threshold:
        existing = await video_repo.get(v.id)
        if existing and existing.cache_status in ("cached", "pre-cached"):
            continue
        await queue.enqueue(v.id)
        enqueued.append(v.id)

    return {"status": "ok", "enqueued": len(enqueued), "video_ids": enqueued}


@router.get("/download/bandwidth")
async def get_bandwidth(request: Request):
    bw = getattr(request.app.state, "bandwidth_manager", None)
    if bw is None:
        return {"rate_mbps": 0, "throttled": False}
    return bw.status()


class BandwidthUpdate(BaseModel):
    rate_mbps: float


@router.put("/download/bandwidth")
async def set_bandwidth(body: BandwidthUpdate, request: Request):
    bw = getattr(request.app.state, "bandwidth_manager", None)
    if bw is None:
        return {"status": "error", "message": "Bandwidth manager not available"}
    bw.rate_mbps = body.rate_mbps
    return {"status": "ok", "rate_mbps": bw.rate_mbps}
```

- [ ] **Step 3: Initialize bandwidth manager in main.py**

```python
from backend.services.bandwidth import BandwidthManager
app.state.bandwidth_manager = BandwidthManager()
```

- [ ] **Step 4: Commit**

```bash
git add backend/services/bandwidth.py backend/api/routers/recommend.py backend/api/main.py
git commit -m "feat: add bandwidth manager and batch download endpoint"
```

---

## Task 9: App Model Updates

**Files:**
- Modify: `shield-app/.../api/models.kt`
- Modify: `shield-app/.../api/ShieldTubeApi.kt`

- [ ] **Step 1: Update ProgressBody with optional event/speed**

In `models.kt`, change:

```kotlin
data class ProgressBody(
    @SerializedName("position_seconds") val positionSeconds: Int,
    val duration: Int,
    val event: String? = null,
    val speed: Float? = null
)
```

- [ ] **Step 2: Add pre_cached to Video**

```kotlin
data class Video(
    val id: String,
    val title: String,
    @SerializedName("channel_name") val channelName: String,
    @SerializedName("channel_id") val channelId: String,
    @SerializedName("view_count") val viewCount: Long?,
    val duration: Int?,
    @SerializedName("published_at") val publishedAt: String?,
    @SerializedName("thumbnail_url") val thumbnailUrl: String,
    @SerializedName("pre_cached") val preCached: Boolean = false
)
```

- [ ] **Step 3: Add source/freshness to FeedResponse**

```kotlin
data class FeedResponse(
    @SerializedName("feed_type") val feedType: String,
    val videos: List<Video>,
    @SerializedName("cached_at") val cachedAt: String?,
    @SerializedName("from_cache") val fromCache: Boolean,
    val source: String? = null,
    val freshness: String? = null
)
```

- [ ] **Step 4: Add getFeedRecommended to ShieldTubeApi.kt**

```kotlin
@GET("/api/feed/recommended")
suspend fun getFeedRecommended(): FeedResponse
```

- [ ] **Step 5: Build to verify compilation**

Run: `cd shield-app && ./gradlew assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 6: Commit**

```bash
git add shield-app/app/src/main/java/com/shieldtube/api/models.kt
git add shield-app/app/src/main/java/com/shieldtube/api/ShieldTubeApi.kt
git commit -m "feat(app): add recommendation models, pre_cached field, enriched progress body"
```

---

## Task 10: "For You" Row in BrowseFragment

**Files:**
- Modify: `shield-app/.../ui/BrowseFragment.kt`

- [ ] **Step 1: Add "For You" header and adapter**

Add to companion object:
```kotlin
private const val HEADER_FOR_YOU = 3L
```

Add to class body:
```kotlin
private val forYouAdapter = ArrayObjectAdapter(CardPresenter())
```

- [ ] **Step 2: Add "For You" row as first header in setupHeaders()**

Insert before the Home row:
```kotlin
val forYouHeader = HeaderItem(HEADER_FOR_YOU, "For You")
rowsAdapter.add(ListRow(forYouHeader, forYouAdapter))
```

- [ ] **Step 3: Add feed loading for "For You"**

In the `when` block inside `loadFeedForHeader`:
```kotlin
HEADER_FOR_YOU -> ApiClient.api.getFeedRecommended()
```

In `updateRowContent`:
```kotlin
HEADER_FOR_YOU -> forYouAdapter
```

Add to `onCreate`:
```kotlin
loadFeedForHeader(HEADER_FOR_YOU)
```

- [ ] **Step 4: Add file-based recommendation cache**

Add to class:
```kotlin
private fun cacheRecommendations(videos: List<Video>) {
    try {
        val json = com.google.gson.Gson().toJson(videos)
        java.io.File(requireContext().filesDir, "recommended_cache.json").writeText(json)
    } catch (e: Exception) {
        android.util.Log.w("ShieldTube", "Failed to cache recommendations: ${e.message}")
    }
}

private fun loadCachedRecommendations(): List<Video> {
    return try {
        val file = java.io.File(requireContext().filesDir, "recommended_cache.json")
        if (file.exists()) {
            val type = object : com.google.gson.reflect.TypeToken<List<Video>>() {}.type
            com.google.gson.Gson().fromJson(file.readText(), type)
        } else emptyList()
    } catch (e: Exception) {
        emptyList()
    }
}
```

In `onCreate`, before `loadFeedForHeader(HEADER_FOR_YOU)`:
```kotlin
// Load cached recommendations immediately for instant UI
val cached = loadCachedRecommendations()
if (cached.isNotEmpty()) {
    forYouAdapter.addAll(0, cached)
}
```

In `updateRowContent`, after setting the adapter, add for "For You":
```kotlin
if (headerId == HEADER_FOR_YOU) cacheRecommendations(videos)
```

- [ ] **Step 5: Build and install**

Run: `cd shield-app && ./gradlew assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 6: Commit**

```bash
git add shield-app/app/src/main/java/com/shieldtube/ui/BrowseFragment.kt
git commit -m "feat(app): add 'For You' row with file-based cache for recommendations"
```

---

## Task 11: Enriched Progress Reporting from App

**Files:**
- Modify: `shield-app/.../player/PlaybackFragment.kt`

- [ ] **Step 1: Update progress reporting to include event and speed**

In `startProgressReporting`, change the `reportProgress` call:
```kotlin
ApiClient.api.reportProgress(
    videoId,
    ProgressBody(
        positionSeconds = (exoPlayer.currentPosition / 1000).toInt(),
        duration = (exoPlayer.duration / 1000).toInt(),
        event = "playing",
        speed = currentSpeed
    )
)
```

- [ ] **Step 2: Send "paused" event when player pauses**

Add a `Player.Listener` in `initPlayer` that sends pause/complete events:

```kotlin
exoPlayer.addListener(object : Player.Listener {
    override fun onIsPlayingChanged(isPlaying: Boolean) {
        val vid = videoId ?: return
        lifecycleScope.launch {
            try {
                ApiClient.api.reportProgress(vid, ProgressBody(
                    positionSeconds = (exoPlayer.currentPosition / 1000).toInt(),
                    duration = (exoPlayer.duration / 1000).toInt(),
                    event = if (isPlaying) "playing" else "paused",
                    speed = currentSpeed
                ))
            } catch (_: Exception) {}
        }
    }

    override fun onPlaybackStateChanged(playbackState: Int) {
        if (playbackState == Player.STATE_ENDED) {
            val vid = videoId ?: return
            lifecycleScope.launch {
                try {
                    ApiClient.api.reportProgress(vid, ProgressBody(
                        positionSeconds = (exoPlayer.duration / 1000).toInt(),
                        duration = (exoPlayer.duration / 1000).toInt(),
                        event = "completed",
                        speed = currentSpeed
                    ))
                } catch (_: Exception) {}
            }
        }
    }
})
```

- [ ] **Step 3: Send "abandoned" on releasePlayer**

In `releasePlayer`, change the final progress report:
```kotlin
ApiClient.api.reportProgress(
    vid,
    ProgressBody(
        positionSeconds = (p.currentPosition / 1000).toInt(),
        duration = (p.duration / 1000).toInt(),
        event = "abandoned",
        speed = currentSpeed
    )
)
```

- [ ] **Step 4: Build to verify**

Run: `cd shield-app && ./gradlew assembleDebug`
Expected: BUILD SUCCESSFUL

- [ ] **Step 5: Commit**

```bash
git add shield-app/app/src/main/java/com/shieldtube/player/PlaybackFragment.kt
git commit -m "feat(app): send enriched progress events (playing, paused, completed, abandoned)"
```

---

## Task 12: Rec-Engine — Project Scaffold

**Files:**
- Create: `rec_engine/__main__.py`
- Create: `rec_engine/config.yaml`
- Create: `rec_engine/requirements.txt`
- Create: `rec_engine/sync.py`

- [ ] **Step 1: Create package files**

Create `rec_engine/__init__.py` (empty) and `rec_engine/tests/__init__.py` (empty).

Also add `rec_engine/embeddings.db` to the project `.gitignore`.

- [ ] **Step 2: Create requirements.txt**

```
sentence-transformers>=2.2.0
httpx>=0.25.0
pyyaml>=6.0
yt-dlp>=2024.0.0
psutil>=5.9.0
```

- [ ] **Step 2: Create config.yaml**

```yaml
models:
  preferred: "all-mpnet-base-v2"
  fallback:
    - "all-MiniLM-L12-v2"
    - "all-MiniLM-L6-v2"
  auto_fallback: true

ram_threshold_mb: 500
download_threshold: 0.7
candidate_count: 200
output_count: 100
```

- [ ] **Step 3: Create sync.py (NAS API client)**

```python
"""HTTPS client for communicating with the NAS backend."""
import os
import httpx


class NASClient:
    def __init__(self, nas_url: str, api_secret: str | None = None):
        self.nas_url = nas_url.rstrip("/")
        self.api_secret = api_secret or os.environ.get("SHIELDTUBE_API_SECRET", "")
        self._headers = {}
        if self.api_secret:
            self._headers["X-ShieldTube-Secret"] = self.api_secret

    async def get_watch_history(self) -> list[dict]:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(
                f"{self.nas_url}/api/feed/history",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json().get("videos", [])

    async def get_subscriptions(self) -> list[dict]:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(
                f"{self.nas_url}/api/feed/subscriptions",
                headers=self._headers, timeout=120,
            )
            resp.raise_for_status()
            return resp.json().get("videos", [])

    async def sync_recommendations(
        self, run_id: str, model_name: str, videos: list[dict]
    ) -> dict:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{self.nas_url}/api/recommendations/sync",
                headers=self._headers,
                json={
                    "run_id": run_id,
                    "model_name": model_name,
                    "videos": videos,
                },
            )
            resp.raise_for_status()
            return resp.json()

    async def enqueue_downloads(
        self, videos: list[dict], threshold: float = 0.7
    ) -> dict:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{self.nas_url}/api/download/enqueue-batch",
                headers=self._headers,
                json={"videos": videos, "threshold": threshold},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_status(self) -> dict:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(
                f"{self.nas_url}/api/recommendations/status",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()
```

- [ ] **Step 4: Create __main__.py (CLI entry point)**

```python
"""Recommendation engine CLI."""
import argparse
import asyncio
import sys

from rec_engine.sync import NASClient


async def cmd_status(args):
    client = NASClient(args.nas_url, args.api_secret)
    status = await client.get_status()
    print(f"Last updated: {status.get('last_updated', 'never')}")
    print(f"Source: {status.get('source', 'none')}")
    print(f"Count: {status.get('count', 0)}")
    print(f"Model: {status.get('model', 'none')}")


async def cmd_run(args):
    from rec_engine.embedder import Embedder
    from rec_engine.scorer import Scorer
    from rec_engine.candidates import CandidateFetcher
    import uuid, yaml
    from pathlib import Path

    config_path = Path(__file__).parent / "config.yaml"
    with open(config_path) as f:
        config = yaml.safe_load(f)

    client = NASClient(args.nas_url, args.api_secret)
    model_name = args.model or config["models"]["preferred"]

    print(f"[1/5] Loading model: {model_name}")
    embedder = Embedder(config, model_override=model_name)

    print("[2/5] Fetching watch history and candidates...")
    history = await client.get_watch_history()
    subs = await client.get_subscriptions()
    fetcher = CandidateFetcher()
    candidates = await fetcher.fetch(history, subs)
    print(f"  {len(history)} watched, {len(candidates)} candidates")

    print("[3/5] Computing embeddings...")
    history_embeddings = embedder.embed_videos(history)
    candidate_embeddings = embedder.embed_videos(candidates)

    print("[4/5] Scoring candidates...")
    scorer = Scorer()
    profile = scorer.build_profile(history, history_embeddings)
    scored = scorer.score_candidates(
        candidates, candidate_embeddings, profile, history,
        limit=config.get("output_count", 100),
    )
    print(f"  Top score: {scored[0]['score']:.3f}, Bottom: {scored[-1]['score']:.3f}")

    print("[5/5] Syncing to NAS...")
    run_id = f"run-{uuid.uuid4().hex[:12]}"
    result = await client.sync_recommendations(
        run_id, embedder.model_name,
        [{"id": v["id"], "score": v["score"], "reason": v.get("reason")} for v in scored],
    )
    print(f"  Synced {result['count']} recommendations")

    dl_result = await client.enqueue_downloads(
        [{"id": v["id"], "score": v["score"]} for v in scored],
        threshold=config.get("download_threshold", 0.7),
    )
    print(f"  Enqueued {dl_result['enqueued']} downloads")


def main():
    parser = argparse.ArgumentParser(prog="rec_engine", description="ShieldTube Recommendation Engine")
    parser.add_argument("--nas-url", required=True, help="NAS backend URL")
    parser.add_argument("--api-secret", default=None, help="API secret (or set SHIELDTUBE_API_SECRET)")
    sub = parser.add_subparsers(dest="command")

    sub.add_parser("status", help="Check recommendation status on NAS")

    run_parser = sub.add_parser("run", help="Full recommendation run")
    run_parser.add_argument("--model", default=None, help="Override model name")

    sub.add_parser("embed", help="Embed only (no scoring/sync)")

    args = parser.parse_args()
    if args.command is None:
        parser.print_help()
        sys.exit(1)

    if args.command == "status":
        asyncio.run(cmd_status(args))
    elif args.command == "run":
        asyncio.run(cmd_run(args))
    elif args.command == "embed":
        print("Embed-only mode not yet implemented")


if __name__ == "__main__":
    main()
```

- [ ] **Step 5: Commit**

```bash
git add rec_engine/
git commit -m "feat: scaffold rec-engine CLI with NAS sync client"
```

---

## Task 13: Rec-Engine — Embedder

**Files:**
- Create: `rec_engine/embedder.py`
- Test: `rec_engine/tests/test_embedder.py`

- [ ] **Step 1: Write failing test**

```python
"""Tests for adaptive embedding model selection and video embedding."""
import pytest
from unittest.mock import patch, MagicMock
import numpy as np

def test_model_selection_picks_preferred_when_ram_available():
    from rec_engine.embedder import Embedder
    config = {
        "models": {
            "preferred": "all-mpnet-base-v2",
            "fallback": ["all-MiniLM-L6-v2"],
            "auto_fallback": True,
        },
        "ram_threshold_mb": 500,
    }
    with patch("rec_engine.embedder.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value = MagicMock(available=4_000_000_000)
        with patch("rec_engine.embedder.SentenceTransformer") as mock_st:
            mock_st.return_value = MagicMock()
            embedder = Embedder(config)
            assert embedder.model_name == "all-mpnet-base-v2"

def test_model_selection_falls_back_when_ram_low():
    from rec_engine.embedder import Embedder
    config = {
        "models": {
            "preferred": "all-mpnet-base-v2",
            "fallback": ["all-MiniLM-L6-v2"],
            "auto_fallback": True,
        },
        "ram_threshold_mb": 500,
    }
    with patch("rec_engine.embedder.psutil") as mock_psutil:
        # Only 600MB free — after threshold (500MB), only 100MB for model
        mock_psutil.virtual_memory.return_value = MagicMock(available=600_000_000)
        with patch("rec_engine.embedder.SentenceTransformer") as mock_st:
            # First call (preferred) raises, second (fallback) succeeds
            mock_st.side_effect = [RuntimeError("OOM"), MagicMock()]
            embedder = Embedder(config)
            assert embedder.model_name == "all-MiniLM-L6-v2"

def test_embed_videos_returns_array():
    from rec_engine.embedder import Embedder
    config = {
        "models": {"preferred": "all-MiniLM-L6-v2", "fallback": [], "auto_fallback": True},
        "ram_threshold_mb": 100,
    }
    with patch("rec_engine.embedder.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value = MagicMock(available=4_000_000_000)
        with patch("rec_engine.embedder.SentenceTransformer") as mock_st:
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
            mock_st.return_value = mock_model
            embedder = Embedder(config)
            videos = [
                {"title": "Test Video 1", "channel_name": "Ch1"},
                {"title": "Test Video 2", "channel_name": "Ch2"},
            ]
            result = embedder.embed_videos(videos)
            assert result.shape == (2, 3)
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd rec-engine && python -m pytest tests/test_embedder.py -v`
Expected: FAIL — module not found

- [ ] **Step 3: Implement Embedder**

Create `rec_engine/embedder.py`:

```python
"""Adaptive model loading and video text embedding."""
import logging

import numpy as np
import psutil
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

# Approximate model sizes in MB for RAM checks
MODEL_SIZES_MB = {
    "all-mpnet-base-v2": 420,
    "all-MiniLM-L12-v2": 120,
    "all-MiniLM-L6-v2": 80,
}


class Embedder:
    def __init__(self, config: dict, model_override: str | None = None):
        self.config = config
        self.model_name = model_override or config["models"]["preferred"]
        self._model = self._load_model()

    def _load_model(self) -> SentenceTransformer:
        models_to_try = [self.model_name] + self.config["models"].get("fallback", [])
        threshold_mb = self.config.get("ram_threshold_mb", 500)
        available_mb = psutil.virtual_memory().available / (1024 * 1024)
        budget_mb = available_mb - threshold_mb

        for name in models_to_try:
            model_size = MODEL_SIZES_MB.get(name, 200)
            if budget_mb < model_size and self.config["models"].get("auto_fallback"):
                logger.info(f"Skipping {name} ({model_size}MB) — only {budget_mb:.0f}MB available")
                continue
            try:
                model = SentenceTransformer(name)
                self.model_name = name
                logger.info(f"Loaded model: {name}")
                return model
            except Exception as e:
                logger.warning(f"Failed to load {name}: {e}")
                if not self.config["models"].get("auto_fallback"):
                    raise

        raise RuntimeError("No embedding model could be loaded")

    def embed_videos(self, videos: list[dict]) -> np.ndarray:
        texts = [self._video_to_text(v) for v in videos]
        return self._model.encode(texts, show_progress_bar=len(texts) > 50)

    @staticmethod
    def _video_to_text(video: dict) -> str:
        title = video.get("title", "")
        channel = video.get("channel_name", "")
        desc = (video.get("description") or "")[:200]
        parts = [p for p in [title, channel, desc] if p]
        return " | ".join(parts)
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd rec-engine && python -m pytest tests/test_embedder.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rec_engine/embedder.py rec_engine/tests/test_embedder.py
git commit -m "feat(rec-engine): adaptive embedding model with RAM-based selection"
```

---

## Task 14: Rec-Engine — Scorer

**Files:**
- Create: `rec_engine/scorer.py`
- Test: `rec_engine/tests/test_scorer.py`

- [ ] **Step 1: Write failing test**

```python
"""Tests for user profile building and candidate scoring."""
import numpy as np
import pytest
from datetime import datetime, timedelta, timezone


def test_build_profile_returns_weighted_average():
    from rec_engine.scorer import Scorer
    scorer = Scorer()
    history = [
        {"id": "v1", "watched_at": datetime.now(timezone.utc).isoformat(), "completed": 1},
        {"id": "v2", "watched_at": datetime.now(timezone.utc).isoformat(), "completed": 0},
    ]
    embeddings = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    profile = scorer.build_profile(history, embeddings)
    assert profile.shape == (3,)
    # Completed video should have more weight
    assert profile[0] > profile[1]


def test_score_candidates_returns_sorted_list():
    from rec_engine.scorer import Scorer
    scorer = Scorer()
    profile = np.array([1.0, 0.0, 0.0])
    candidates = [
        {"id": "c1", "channel_id": "ch1", "view_count": 1000,
         "published_at": datetime.now(timezone.utc).isoformat()},
        {"id": "c2", "channel_id": "ch2", "view_count": 500,
         "published_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()},
    ]
    # c1 embedding is closer to profile
    embeddings = np.array([[0.9, 0.1, 0.0], [0.1, 0.9, 0.0]])
    history = [{"channel_id": "ch1", "completed": 1}]
    scored = scorer.score_candidates(candidates, embeddings, profile, history, limit=10)
    assert len(scored) == 2
    assert scored[0]["id"] == "c1"
    assert scored[0]["score"] > scored[1]["score"]
```

- [ ] **Step 2: Run tests to verify they fail**

Run: `cd rec-engine && python -m pytest tests/test_scorer.py -v`
Expected: FAIL

- [ ] **Step 3: Implement Scorer**

Create `rec_engine/scorer.py`:

```python
"""User profile vector construction and candidate scoring."""
import math
from datetime import datetime, timedelta, timezone

import numpy as np


class Scorer:
    RECENCY_HALF_LIFE_DAYS = 7
    FRESHNESS_HALF_LIFE_HOURS = 48

    def build_profile(
        self, history: list[dict], embeddings: np.ndarray
    ) -> np.ndarray:
        now = datetime.now(timezone.utc)
        weights = []
        for video in history:
            w = 1.0
            # Completion weight
            if video.get("completed"):
                w *= 1.0
            else:
                w *= 0.4
            # Recency decay
            watched_at = video.get("watched_at")
            if watched_at:
                try:
                    dt = datetime.fromisoformat(watched_at)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    days_ago = (now - dt).total_seconds() / 86400
                    w *= math.exp(-0.693 * days_ago / self.RECENCY_HALF_LIFE_DAYS)
                except (ValueError, TypeError):
                    pass
            weights.append(w)

        weights = np.array(weights, dtype=np.float32)
        if weights.sum() == 0:
            return np.zeros(embeddings.shape[1])
        profile = (embeddings.T @ weights) / weights.sum()
        return profile / (np.linalg.norm(profile) + 1e-8)

    def score_candidates(
        self,
        candidates: list[dict],
        embeddings: np.ndarray,
        profile: np.ndarray,
        history: list[dict],
        limit: int = 100,
    ) -> list[dict]:
        now = datetime.now(timezone.utc)

        # Compute channel affinity from history
        channel_counts: dict[str, int] = {}
        for v in history:
            ch = v.get("channel_id", "")
            channel_counts[ch] = channel_counts.get(ch, 0) + 1
        max_count = max(channel_counts.values()) if channel_counts else 1

        # Cosine similarities
        norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8
        normalized = embeddings / norms
        similarities = normalized @ profile

        scored = []
        for i, candidate in enumerate(candidates):
            sim = float(similarities[i])
            ch_id = candidate.get("channel_id", "")
            ch_affinity = channel_counts.get(ch_id, 0) / max_count

            freshness = 0.0
            pub = candidate.get("published_at")
            if pub:
                try:
                    dt = datetime.fromisoformat(pub)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    hours_ago = (now - dt).total_seconds() / 3600
                    freshness = max(0, math.exp(-0.693 * hours_ago / self.FRESHNESS_HALF_LIFE_HOURS))
                except (ValueError, TypeError):
                    pass

            views = candidate.get("view_count") or 0
            popularity = min(1.0, math.log(views + 1) / 20.0) if views > 0 else 0.0

            score = (0.6 * sim) + (0.2 * ch_affinity) + (0.1 * freshness) + (0.1 * popularity)

            reason = []
            if ch_affinity > 0.5:
                reason.append("channel you watch")
            if sim > 0.7:
                reason.append("similar content")
            if freshness > 0.8:
                reason.append("recently published")

            scored.append({
                **candidate,
                "score": score,
                "reason": ", ".join(reason) if reason else "recommended",
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]
```

- [ ] **Step 4: Run tests to verify they pass**

Run: `cd rec-engine && python -m pytest tests/test_scorer.py -v`
Expected: PASS

- [ ] **Step 5: Commit**

```bash
git add rec_engine/scorer.py rec_engine/tests/test_scorer.py
git commit -m "feat(rec-engine): user profile builder and candidate scorer"
```

---

## Task 15: Rec-Engine — Candidate Fetcher

**Files:**
- Create: `rec_engine/candidates.py`

- [ ] **Step 1: Implement CandidateFetcher**

```python
"""Fetch candidate videos for recommendation scoring."""
import asyncio
import logging
import subprocess
import json

logger = logging.getLogger(__name__)


class CandidateFetcher:
    """Fetches candidate videos from subscriptions and yt-dlp related videos."""

    async def fetch(
        self, history: list[dict], subscriptions: list[dict], max_related: int = 10
    ) -> list[dict]:
        # Start with subscription videos as candidates
        candidates = {v["id"]: v for v in subscriptions}

        # Get related videos for top watched videos via yt-dlp
        watched_ids = [v["id"] for v in history[:max_related]]
        related = await self._fetch_related_batch(watched_ids)
        for v in related:
            if v["id"] not in candidates:
                candidates[v["id"]] = v

        # Exclude already-watched videos
        watched_set = {v["id"] for v in history}
        return [v for vid, v in candidates.items() if vid not in watched_set]

    async def _fetch_related_batch(self, video_ids: list[str]) -> list[dict]:
        results = []
        for vid in video_ids:
            try:
                related = await asyncio.to_thread(self._fetch_related_sync, vid)
                results.extend(related)
            except Exception as e:
                logger.warning(f"Failed to fetch related for {vid}: {e}")
        return results

    @staticmethod
    def _fetch_related_sync(video_id: str) -> list[dict]:
        cmd = [
            "yt-dlp", "--flat-playlist", "--dump-json",
            f"https://www.youtube.com/watch?v={video_id}",
            "--playlist-items", "1:10",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            videos = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                data = json.loads(line)
                videos.append({
                    "id": data.get("id", ""),
                    "title": data.get("title", ""),
                    "channel_name": data.get("channel", data.get("uploader", "")),
                    "channel_id": data.get("channel_id", ""),
                    "view_count": data.get("view_count"),
                    "duration": data.get("duration"),
                    "published_at": data.get("upload_date"),
                    "description": (data.get("description") or "")[:200],
                })
            return videos
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            return []
```

- [ ] **Step 2: Commit**

```bash
git add rec_engine/candidates.py
git commit -m "feat(rec-engine): candidate fetcher using subscriptions and yt-dlp related videos"
```

---

## Task 16: Integration Test & Docker Rebuild

- [ ] **Step 1: Rebuild Docker image with new backend code**

```bash
cd /home/asjad/shieldtube
docker compose down
docker compose build --no-cache
docker compose up -d
```

After startup, fix yt-dlp in container:
```bash
docker exec shieldtube-shieldtube-api-1 bash -c \
  "pip install --force-reinstall yt-dlp && \
   find /usr/local/lib/python3.11/site-packages/yt_dlp -name '*.pyc' -delete"
```

- [ ] **Step 2: Verify new endpoints work**

```bash
# Status (should return empty)
curl -sk https://192.168.0.26:9443/api/recommendations/status

# Recommended feed (should return heuristic fallback)
curl -sk https://192.168.0.26:9443/api/feed/recommended \
  -H "X-ShieldTube-Secret: $API_SECRET"

# Sync test recommendations
curl -sk -X POST https://192.168.0.26:9443/api/recommendations/sync \
  -H "X-ShieldTube-Secret: $API_SECRET" \
  -H "Content-Type: application/json" \
  -d '{"run_id":"test-001","model_name":"test","videos":[{"id":"dQw4w9WgXcQ","score":0.95}]}'
```

- [ ] **Step 3: Build and install app**

```bash
cd shield-app && ./gradlew assembleDebug
adb -s 192.168.0.46:5555 install -r app/build/outputs/apk/debug/app-debug.apk
```

- [ ] **Step 4: Verify "For You" row appears on Shield TV**

Take screenshot: `adb shell screencap -p /sdcard/verify.png && adb pull /sdcard/verify.png`
Expected: "For You" row at top of BrowseFragment

- [ ] **Step 5: Install rec-engine on laptop**

```bash
cd rec-engine
pip install -r requirements.txt
python -m rec_engine --nas-url https://192.168.0.26:9443 status
```

Expected: `Last updated: never`

- [ ] **Step 6: Run full recommendation pipeline**

```bash
python -m rec_engine --nas-url https://192.168.0.26:9443 --api-secret "$API_SECRET" run
```

Expected: Embeddings computed, scored, synced, downloads enqueued

- [ ] **Step 7: Verify "For You" row populates**

Restart app, take screenshot, verify "For You" shows ML-scored videos.

- [ ] **Step 8: Commit any fixes**

```bash
git add -A
git commit -m "feat: complete recommendation engine integration"
```

---

## Task 17: Update PRD

- [ ] **Step 1: Update the non-goal in PRD**

In `docs/ShieldTube_PRD.md`, find the line about "Not a recommendation engine replacement" and update:

```markdown
~~Not a recommendation engine replacement. We consume YouTube's recommendation API.~~
**Local recommendation engine** supplements YouTube's feeds using watch history embeddings.
ML inference runs on the laptop, not the NAS. See `docs/superpowers/specs/2026-03-21-recommendation-engine-design.md`.
```

- [ ] **Step 2: Commit**

```bash
git add docs/ShieldTube_PRD.md
git commit -m "docs: update PRD to reflect recommendation engine scope change"
```

---

## Task 18: NVIDIA Shield-Inspired Theme & App Icon

**Files:**
- Modify: `shield-app/app/src/main/java/com/shieldtube/ui/BrowseFragment.kt`
- Modify: `shield-app/app/src/main/java/com/shieldtube/ui/LoginFragment.kt`
- Create: `shield-app/app/src/main/res/mipmap-xxxhdpi/ic_launcher.png` (320x180 Android TV banner)
- Create: `shield-app/app/src/main/res/drawable/ic_launcher_foreground.xml`
- Create: `shield-app/app/src/main/res/values/colors.xml`
- Create: `shield-app/app/src/main/res/values/styles.xml`

- [ ] **Step 1: Define NVIDIA-inspired color palette**

Create `shield-app/app/src/main/res/values/colors.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <!-- NVIDIA Shield-inspired palette -->
    <color name="nvidia_green">#FF76B900</color>
    <color name="nvidia_green_dark">#FF5A8C00</color>
    <color name="nvidia_green_light">#FF8ED100</color>
    <color name="background_dark">#FF121212</color>
    <color name="background_card">#FF1E1E1E</color>
    <color name="surface_dark">#FF1A1A1A</color>
    <color name="text_primary">#FFFFFFFF</color>
    <color name="text_secondary">#FFB0B0B0</color>
    <color name="accent_red">#FFE94560</color>
</resources>
```

- [ ] **Step 2: Create app theme**

Create `shield-app/app/src/main/res/values/styles.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<resources>
    <style name="ShieldTubeTheme" parent="@style/Theme.Leanback">
        <item name="android:colorPrimary">@color/nvidia_green</item>
        <item name="android:colorPrimaryDark">@color/nvidia_green_dark</item>
        <item name="android:colorAccent">@color/nvidia_green</item>
        <item name="android:windowBackground">@color/background_dark</item>
        <item name="brandColor">@color/background_dark</item>
        <item name="searchOrbColor">@color/nvidia_green</item>
    </style>
</resources>
```

- [ ] **Step 3: Apply theme in AndroidManifest.xml**

In `shield-app/app/src/main/AndroidManifest.xml`, set:

```xml
<application
    android:theme="@style/ShieldTubeTheme"
    ...>
```

- [ ] **Step 4: Update BrowseFragment colors to use NVIDIA green**

Replace hardcoded color values:

```kotlin
// Change from:
brandColor = 0xFF1a1a2e.toInt()
searchAffordanceColor = 0xFFe94560.toInt()

// To:
brandColor = resources.getColor(R.color.background_dark, null)
searchAffordanceColor = resources.getColor(R.color.nvidia_green, null)
```

- [ ] **Step 5: Update LoginFragment colors**

Replace hardcoded colors:

```kotlin
// Background
setBackgroundColor(resources.getColor(R.color.background_dark, null))

// User code highlight
setTextColor(resources.getColor(R.color.nvidia_green, null))  // was 0xFFe94560 (red)
```

- [ ] **Step 6: Create app icon**

Android TV requires a 320x180px banner image. Create a vector drawable for the foreground:

`shield-app/app/src/main/res/drawable/ic_launcher_foreground.xml`:

```xml
<?xml version="1.0" encoding="utf-8"?>
<vector xmlns:android="http://schemas.android.com/apk/res/android"
    android:width="320dp"
    android:height="180dp"
    android:viewportWidth="320"
    android:viewportHeight="180">
    <!-- Dark background with NVIDIA green shield icon -->
    <path
        android:fillColor="#FF121212"
        android:pathData="M0,0h320v180H0z"/>
    <!-- Shield shape -->
    <path
        android:fillColor="#FF76B900"
        android:pathData="M160,30 L120,50 L120,100 Q120,130 160,150 Q200,130 200,100 L200,50 Z"/>
    <!-- Play triangle inside shield -->
    <path
        android:fillColor="#FF121212"
        android:pathData="M150,70 L150,120 L185,95 Z"/>
</vector>
```

Set as the TV banner in `AndroidManifest.xml`:

```xml
<application
    android:banner="@drawable/ic_launcher_foreground"
    ...>
```

- [ ] **Step 7: Build and verify**

Run: `cd shield-app && ./gradlew assembleDebug`
Expected: BUILD SUCCESSFUL

Install and verify the green theme appears on the Shield TV:
```bash
adb install -r app/build/outputs/apk/debug/app-debug.apk
```

- [ ] **Step 8: Commit**

```bash
git add shield-app/app/src/main/res/
git add shield-app/app/src/main/AndroidManifest.xml
git add shield-app/app/src/main/java/com/shieldtube/ui/BrowseFragment.kt
git add shield-app/app/src/main/java/com/shieldtube/ui/LoginFragment.kt
git commit -m "feat(app): NVIDIA Shield-inspired dark theme with green accents and TV banner icon"
```
