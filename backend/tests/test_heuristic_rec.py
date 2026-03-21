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
    for vid, ch in [("w1","chA"),("w2","chA"),("w3","chA"),("w4","chB")]:
        await db.execute(
            "INSERT INTO videos (id, title, channel_name, channel_id, published_at) VALUES (?,?,?,?,datetime('now'))",
            (vid, f"Title {vid}", f"Channel {ch}", ch))
        await db.execute(
            "INSERT INTO watch_history (video_id, watched_at, position_seconds, duration, completed)"
            " VALUES (?, datetime('now'), 500, 600, 1)", (vid,))
    for vid, ch, views in [("c1","chA",10000),("c2","chA",500),("c3","chC",100)]:
        await db.execute(
            "INSERT INTO videos (id, title, channel_name, channel_id, view_count, published_at) VALUES (?,?,?,?,?,datetime('now'))",
            (vid, f"Candidate {vid}", f"Channel {ch}", ch, views))
    await db.commit()

async def test_heuristic_recommends_from_top_channels(db):
    await _seed_data(db)
    rec = HeuristicRecommender(db)
    results = await rec.get_recommendations(limit=10)
    video_ids = [r["id"] for r in results]
    assert "c1" in video_ids
    assert "c2" in video_ids
    if "c3" in video_ids:
        assert video_ids.index("c1") < video_ids.index("c3")

async def test_heuristic_excludes_watched_videos(db):
    await _seed_data(db)
    rec = HeuristicRecommender(db)
    results = await rec.get_recommendations(limit=10)
    video_ids = [r["id"] for r in results]
    for watched in ["w1", "w2", "w3", "w4"]:
        assert watched not in video_ids

async def test_heuristic_returns_empty_with_no_history(db):
    rec = HeuristicRecommender(db)
    results = await rec.get_recommendations(limit=10)
    assert results == []
