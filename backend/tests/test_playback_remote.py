"""Tests for playback remote control endpoints (command queue + status)."""
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
        patch("backend.api.routers.cast.get_db", new=_fake_get_db),
        patch("backend.api.middleware.SharedSecretMiddleware.dispatch",
              new=lambda self, req, call_next: call_next(req)),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac


async def test_post_and_get_commands(client):
    """Phone posts commands, Shield polls and gets them."""
    await client.post("/api/playback/command", json={"action": "pause"})
    await client.post("/api/playback/command", json={"action": "seek", "value": "30"})

    resp = await client.get("/api/playback/commands")
    assert resp.status_code == 200
    cmds = resp.json()["commands"]
    assert len(cmds) == 2
    assert cmds[0]["action"] == "pause"
    assert cmds[1]["action"] == "seek"
    assert cmds[1]["value"] == "30"


async def test_commands_cleared_after_poll(client):
    """Commands are deleted after Shield reads them."""
    await client.post("/api/playback/command", json={"action": "resume"})
    await client.get("/api/playback/commands")  # first poll drains

    resp = await client.get("/api/playback/commands")
    assert resp.json()["commands"] == []


async def test_empty_commands(client):
    """No commands returns empty list."""
    resp = await client.get("/api/playback/commands")
    assert resp.status_code == 200
    assert resp.json()["commands"] == []


async def test_put_and_get_status(client):
    """Shield reports status, phone reads it."""
    await client.put("/api/playback/status", json={
        "video_id": "abc123",
        "title": "Test Video",
        "position_ms": 5000,
        "duration_ms": 60000,
        "is_playing": True,
        "speed": 1.5,
    })

    resp = await client.get("/api/playback/status")
    assert resp.status_code == 200
    data = resp.json()
    assert data["video_id"] == "abc123"
    assert data["title"] == "Test Video"
    assert data["position_ms"] == 5000
    assert data["duration_ms"] == 60000
    assert data["is_playing"] is True
    assert data["speed"] == 1.5


async def test_status_upsert(client):
    """Second put overwrites the first (single-row table)."""
    await client.put("/api/playback/status", json={
        "video_id": "v1", "title": "First", "position_ms": 0,
        "duration_ms": 100, "is_playing": True, "speed": 1.0,
    })
    await client.put("/api/playback/status", json={
        "video_id": "v1", "title": "First", "position_ms": 5000,
        "duration_ms": 100, "is_playing": False, "speed": 2.0,
    })

    resp = await client.get("/api/playback/status")
    data = resp.json()
    assert data["position_ms"] == 5000
    assert data["is_playing"] is False
    assert data["speed"] == 2.0


async def test_empty_status(client):
    """No status returns video_id: null."""
    resp = await client.get("/api/playback/status")
    assert resp.status_code == 200
    assert resp.json()["video_id"] is None


async def test_clear_status(client):
    """DELETE clears the status row."""
    await client.put("/api/playback/status", json={
        "video_id": "v1", "title": "Test", "position_ms": 0,
        "duration_ms": 100, "is_playing": True, "speed": 1.0,
    })
    resp = await client.delete("/api/playback/status")
    assert resp.status_code == 200
    assert resp.json()["status"] == "cleared"

    resp = await client.get("/api/playback/status")
    assert resp.json()["video_id"] is None
