import pytest
import aiosqlite
from pathlib import Path
from unittest.mock import patch, AsyncMock

from httpx import AsyncClient, ASGITransport
from backend.api.main import app
from backend.db.database import _run_migrations

pytestmark = pytest.mark.asyncio


@pytest.fixture
async def db_and_client(tmp_path):
    """Set up in-memory DB and test client with patched cache_dir."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)

    async def mock_get_db():
        return conn

    async def mock_init_db():
        pass

    async def mock_close_db():
        pass

    with patch("backend.api.routers.cache.get_db", mock_get_db), \
         patch("backend.db.database.get_db", mock_get_db), \
         patch("backend.db.database.init_db", mock_init_db), \
         patch("backend.db.database.close_db", mock_close_db), \
         patch("backend.api.routers.cache.settings") as mock_settings, \
         patch("backend.config.settings") as mock_config_settings:
        mock_settings.cache_dir = str(tmp_path)
        mock_config_settings.cache_dir = str(tmp_path)
        mock_config_settings.youtube_access_token = ""
        mock_config_settings.download_wait_timeout = 30

        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as client:
            yield conn, client, tmp_path

    await conn.close()


async def test_cache_status_empty(db_and_client):
    conn, client, tmp_path = db_and_client
    resp = await client.get("/api/cache/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_size_bytes"] == 0
    assert data["video_count"] == 0
    assert data["videos"] == []


async def test_cache_status_with_files(db_and_client):
    conn, client, tmp_path = db_and_client
    # Create cache dir and a fake video file
    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()
    (videos_dir / "vid1.mp4").write_bytes(b"\x00" * 1024)

    # Seed video in DB
    await conn.execute(
        "INSERT INTO videos (id, title, channel_name, channel_id, cache_status) VALUES (?, ?, ?, ?, ?)",
        ("vid1", "Test Video", "Channel", "UC1", "cached"),
    )
    await conn.commit()

    resp = await client.get("/api/cache/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["total_size_bytes"] == 1024
    assert data["video_count"] == 1
    assert data["videos"][0]["id"] == "vid1"
    assert data["videos"][0]["title"] == "Test Video"


async def test_delete_cached_video(db_and_client):
    conn, client, tmp_path = db_and_client
    videos_dir = tmp_path / "videos"
    videos_dir.mkdir()
    video_file = videos_dir / "vid1.mp4"
    video_file.write_bytes(b"\x00" * 1024)

    await conn.execute(
        "INSERT INTO videos (id, title, channel_name, channel_id, cache_status, cached_video_path) VALUES (?, ?, ?, ?, ?, ?)",
        ("vid1", "Test", "Ch", "UC1", "cached", str(video_file)),
    )
    await conn.commit()

    resp = await client.delete("/api/cache/vid1")
    assert resp.status_code == 200
    assert resp.json()["status"] == "deleted"
    assert not video_file.exists()

    # Verify DB reset
    async with conn.execute("SELECT cache_status FROM videos WHERE id = 'vid1'") as cur:
        row = await cur.fetchone()
    assert row["cache_status"] == "none"


async def test_delete_not_cached_returns_404(db_and_client):
    conn, client, tmp_path = db_and_client
    resp = await client.delete("/api/cache/nonexistent")
    assert resp.status_code == 404
