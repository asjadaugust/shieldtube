import pytest
import aiosqlite
from datetime import datetime, timezone

from backend.db.database import _run_migrations
from backend.db.models import WatchHistoryEntry
from backend.db.repositories import WatchHistoryRepo

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


async def test_upsert_and_get(db):
    repo = WatchHistoryRepo(db)
    entry = WatchHistoryEntry(
        video_id="vid1",
        watched_at=datetime.now(timezone.utc).isoformat(),
        position_seconds=120,
        duration=600,
    )
    await repo.upsert(entry)
    result = await repo.get("vid1")
    assert result is not None
    assert result.position_seconds == 120
    assert result.completed == 0


async def test_upsert_marks_completed_at_90_percent(db):
    repo = WatchHistoryRepo(db)
    entry = WatchHistoryEntry(
        video_id="vid1",
        watched_at=datetime.now(timezone.utc).isoformat(),
        position_seconds=550,
        duration=600,
    )
    await repo.upsert(entry)
    result = await repo.get("vid1")
    assert result.completed == 1


async def test_upsert_updates_existing(db):
    repo = WatchHistoryRepo(db)
    now = datetime.now(timezone.utc).isoformat()
    await repo.upsert(WatchHistoryEntry(video_id="vid1", watched_at=now, position_seconds=60, duration=600))
    await repo.upsert(WatchHistoryEntry(video_id="vid1", watched_at=now, position_seconds=300, duration=600))
    result = await repo.get("vid1")
    assert result.position_seconds == 300


async def test_get_returns_none_for_missing(db):
    repo = WatchHistoryRepo(db)
    assert await repo.get("nonexistent") is None


async def test_get_recent_ordering(db):
    repo = WatchHistoryRepo(db)
    await repo.upsert(WatchHistoryEntry(video_id="old", watched_at="2026-01-01T00:00:00Z", position_seconds=10))
    await repo.upsert(WatchHistoryEntry(video_id="new", watched_at="2026-03-20T00:00:00Z", position_seconds=20))
    results = await repo.get_recent(limit=10)
    assert results[0].video_id == "new"
    assert results[1].video_id == "old"


async def test_get_recent_respects_limit(db):
    repo = WatchHistoryRepo(db)
    for i in range(5):
        await repo.upsert(WatchHistoryEntry(video_id=f"v{i}", watched_at=f"2026-03-{20+i:02d}T00:00:00Z"))
    results = await repo.get_recent(limit=3)
    assert len(results) == 3
