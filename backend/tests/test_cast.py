import pytest
from httpx import AsyncClient, ASGITransport

from backend.api.main import app
import backend.api.routers.cast as cast_module


@pytest.fixture(autouse=True)
def reset_now_playing():
    """Reset the in-memory state before each test."""
    cast_module._now_playing = None
    yield
    cast_module._now_playing = None


@pytest.fixture
async def client():
    async with AsyncClient(transport=ASGITransport(app=app), base_url="http://test") as ac:
        yield ac


@pytest.mark.asyncio
async def test_cast_with_video_id(client):
    response = await client.post("/api/cast", json={"video_id": "dQw4w9WgXcQ"})
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "queued"
    assert data["video_id"] == "dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_cast_with_youtube_url(client):
    response = await client.post(
        "/api/cast", json={"url": "https://youtube.com/watch?v=dQw4w9WgXcQ"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["video_id"] == "dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_cast_with_short_url(client):
    response = await client.post(
        "/api/cast", json={"url": "https://youtu.be/dQw4w9WgXcQ"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["video_id"] == "dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_cast_invalid_url(client):
    response = await client.post("/api/cast", json={"url": "not a url"})
    assert response.status_code == 400
    data = response.json()
    assert "error" in data


@pytest.mark.asyncio
async def test_now_playing_returns_queued(client):
    await client.post("/api/cast", json={"video_id": "dQw4w9WgXcQ"})
    response = await client.get("/api/cast/now-playing")
    assert response.status_code == 200
    data = response.json()
    assert data["video_id"] == "dQw4w9WgXcQ"


@pytest.mark.asyncio
async def test_now_playing_clears_after_read(client):
    await client.post("/api/cast", json={"video_id": "dQw4w9WgXcQ"})
    # First read returns the video
    first = await client.get("/api/cast/now-playing")
    assert first.json()["video_id"] == "dQw4w9WgXcQ"
    # Second read returns null (cleared)
    second = await client.get("/api/cast/now-playing")
    assert second.json()["video_id"] is None


@pytest.mark.asyncio
async def test_now_playing_empty(client):
    response = await client.get("/api/cast/now-playing")
    assert response.status_code == 200
    data = response.json()
    assert data["video_id"] is None
