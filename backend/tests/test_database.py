"""Tests for database initialization and migrations."""
from __future__ import annotations

import pytest
import aiosqlite

from backend.db.database import _run_migrations


@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


async def _get_tables(conn: aiosqlite.Connection) -> set[str]:
    async with conn.execute(
        "SELECT name FROM sqlite_master WHERE type='table'"
    ) as cursor:
        rows = await cursor.fetchall()
    return {row["name"] for row in rows}


async def test_init_db_creates_all_tables(db):
    """All 4 expected tables must exist after migration."""
    tables = await _get_tables(db)
    assert "videos" in tables
    assert "feed_cache" in tables
    assert "thumbnails" in tables
    assert "auth_tokens" in tables


async def test_migrations_are_idempotent(db):
    """Running migrations a second time must not raise an error."""
    await _run_migrations(db)
    tables = await _get_tables(db)
    assert len(tables) >= 4


async def test_videos_table_columns(db):
    """Verify expected columns exist on the videos table."""
    async with db.execute("PRAGMA table_info(videos)") as cursor:
        rows = await cursor.fetchall()
    columns = {row["name"] for row in rows}
    expected = {
        "id", "title", "channel_name", "channel_id", "view_count",
        "duration", "published_at", "description", "thumbnail_path",
        "cached_video_path", "cache_status", "last_accessed",
        "created_at", "updated_at",
    }
    assert expected.issubset(columns)


async def test_auth_tokens_table_columns(db):
    """Verify expected columns exist on auth_tokens table."""
    async with db.execute("PRAGMA table_info(auth_tokens)") as cursor:
        rows = await cursor.fetchall()
    columns = {row["name"] for row in rows}
    expected = {
        "id", "access_token", "refresh_token", "token_type",
        "expires_at", "scopes", "created_at", "updated_at",
    }
    assert expected.issubset(columns)


async def test_feed_cache_table_columns(db):
    """Verify expected columns exist on feed_cache table."""
    async with db.execute("PRAGMA table_info(feed_cache)") as cursor:
        rows = await cursor.fetchall()
    columns = {row["name"] for row in rows}
    expected = {"feed_type", "video_ids_json", "etag", "fetched_at"}
    assert expected.issubset(columns)


async def test_thumbnails_table_columns(db):
    """Verify expected columns exist on thumbnails table."""
    async with db.execute("PRAGMA table_info(thumbnails)") as cursor:
        rows = await cursor.fetchall()
    columns = {row["name"] for row in rows}
    expected = {"video_id", "resolution", "local_path", "fetched_at", "content_hash"}
    assert expected.issubset(columns)
