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
