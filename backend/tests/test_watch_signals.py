"""Tests for watch signal aggregation from progress events."""
import pytest
import aiosqlite
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
    # Session exists in memory but not yet persisted (no terminal event)
    assert "v1" in agg._sessions


async def test_process_paused_increments_pause_count(db):
    agg = WatchSignalAggregator(db)
    await agg.process_event("v1", position_seconds=10, duration=600,
                            event="playing", speed=1.0)
    await agg.process_event("v1", position_seconds=30, duration=600,
                            event="paused", speed=1.0)
    assert agg._sessions["v1"]["pause_count"] == 1


async def test_process_completed_persists_signal(db):
    agg = WatchSignalAggregator(db)
    await agg.process_event("v1", position_seconds=10, duration=600,
                            event="playing", speed=1.0)
    await agg.process_event("v1", position_seconds=570, duration=600,
                            event="completed", speed=1.0)
    signals = await agg.get_signals("v1")
    assert len(signals) == 1
    assert signals[0].completion_rate == pytest.approx(0.95, abs=0.01)
    assert "v1" not in agg._sessions  # Session cleared after terminal event


async def test_process_abandoned_sets_abandoned_pct(db):
    agg = WatchSignalAggregator(db)
    await agg.process_event("v1", position_seconds=10, duration=600,
                            event="playing", speed=1.0)
    await agg.process_event("v1", position_seconds=180, duration=600,
                            event="abandoned", speed=1.0)
    signals = await agg.get_signals("v1")
    assert len(signals) == 1
    assert signals[0].abandoned_at_pct == pytest.approx(0.3, abs=0.01)


async def test_periodic_persist_on_5th_playing_event(db):
    agg = WatchSignalAggregator(db)
    for i in range(5):
        await agg.process_event("v1", position_seconds=i * 10, duration=600,
                                event="playing", speed=1.5)
    # After 5th playing event, a partial signal should be persisted
    signals = await agg.get_signals("v1")
    assert len(signals) == 1
    assert signals[0].avg_playback_speed == pytest.approx(1.5, abs=0.01)
    assert "v1" in agg._sessions  # Session still active
