"""Tests for RecommendationRepo and WatchSignalRepo."""
import pytest
import aiosqlite
from backend.db.database import _run_migrations
from backend.db.models import RecommendationRun, Recommendation, WatchSignal

pytestmark = pytest.mark.asyncio

@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


async def test_recommendation_repo_upsert_run_and_get_latest(db):
    from backend.db.repositories import RecommendationRepo
    repo = RecommendationRepo(db)
    await repo.upsert_run(RecommendationRun(
        run_id="run-001", run_at="2026-03-21T00:00:00Z",
        source="ml", model_name="all-MiniLM-L6-v2", video_count=3,
    ))
    latest = await repo.get_latest_run()
    assert latest is not None
    assert latest.run_id == "run-001"
    assert latest.source == "ml"


async def test_recommendation_repo_upsert_and_get_recommendations(db):
    from backend.db.repositories import RecommendationRepo
    repo = RecommendationRepo(db)
    await repo.upsert_run(RecommendationRun(
        run_id="run-001", run_at="2026-03-21T00:00:00Z",
        source="ml", video_count=2,
    ))
    await repo.upsert_recommendations("run-001", [
        Recommendation(video_id="v1", run_id="run-001", score=0.9, reason="test"),
        Recommendation(video_id="v2", run_id="run-001", score=0.7, reason="test"),
    ])
    recs = await repo.get_recommendations(limit=10)
    assert len(recs) == 2
    assert recs[0].score >= recs[1].score  # sorted by score DESC


async def test_watch_signal_repo_upsert_and_get(db):
    from backend.db.repositories import WatchSignalRepo
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


async def test_watch_signal_multiple_sessions(db):
    from backend.db.repositories import WatchSignalRepo
    repo = WatchSignalRepo(db)
    for i in range(3):
        await repo.upsert(WatchSignal(
            video_id="v1", session_start=f"2026-03-21T0{i}:00:00Z",
            completion_rate=0.5 + i * 0.1,
        ))
    signals = await repo.get_for_video("v1")
    assert len(signals) == 3  # Each session is a separate row
