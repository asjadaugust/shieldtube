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
        patch("backend.api.middleware.SharedSecretMiddleware.dispatch",
              new=lambda self, req, call_next: call_next(req)),
    ):
        transport = ASGITransport(app=app)
        async with AsyncClient(transport=transport, base_url="http://test") as ac:
            yield ac

async def test_recommended_feed_heuristic_fallback(client):
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

async def test_recommendations_sync(client, mem_db):
    payload = {
        "run_id": "test-run-001",
        "model_name": "all-MiniLM-L6-v2",
        "videos": [
            {"id": "v1", "score": 0.9, "reason": "similar", "title": "Test Video", "channel_name": "Ch1", "channel_id": "ch1"},
            {"id": "v2", "score": 0.7, "reason": "affinity", "title": "Test 2", "channel_name": "Ch2", "channel_id": "ch2"},
        ],
    }
    resp = await client.post("/api/recommendations/sync", json=payload)
    assert resp.status_code == 200
    assert resp.json()["count"] == 2
    status = await client.get("/api/recommendations/status")
    assert status.json()["last_updated"] is not None
    assert status.json()["count"] == 2
