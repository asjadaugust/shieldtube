"""Tests for the SponsorBlock service and /api/sponsorblock/{video_id} endpoint."""
import json
from unittest.mock import AsyncMock, MagicMock, patch

import aiosqlite
import pytest
from httpx import AsyncClient, ASGITransport, Request, Response

from backend.db.database import _run_migrations
from backend.services.sponsorblock import get_segments

pytestmark = pytest.mark.asyncio

# ---------------------------------------------------------------------------
# SponsorBlock API fixture
# ---------------------------------------------------------------------------

SPONSORBLOCK_FIXTURE = [
    {
        "segment": [30.5, 60.2],
        "UUID": "abc123",
        "category": "sponsor",
        "actionType": "skip",
    },
    {
        "segment": [180.0, 195.5],
        "UUID": "def456",
        "category": "intro",
        "actionType": "skip",
    },
]


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------


_DUMMY_REQUEST = Request("GET", "https://sponsor.ajay.app/api/skipSegments")


def _make_httpx_response(status_code: int, data=None) -> Response:
    """Build an httpx.Response with a dummy request so raise_for_status() works."""
    if data is None:
        content = b""
    elif isinstance(data, (list, dict)):
        content = json.dumps(data).encode()
    else:
        content = data
    return Response(status_code=status_code, content=content, request=_DUMMY_REQUEST)


def _mock_httpx_client(response):
    """Return a patched httpx.AsyncClient context manager."""
    mock_client = AsyncMock()
    if isinstance(response, list):
        mock_client.get = AsyncMock(side_effect=response)
    else:
        mock_client.get = AsyncMock(return_value=response)

    mock_client_cls = MagicMock()
    mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)
    return mock_client_cls, mock_client


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
async def db():
    """In-memory SQLite connection with all migrations applied."""
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


@pytest.fixture
async def db_with_video(db):
    """DB with a seeded video row so UPDATE queries find a matching row."""
    await db.execute(
        "INSERT INTO videos (id, title, channel_name, channel_id) VALUES (?, ?, ?, ?)",
        ("test_video", "Test Video", "Test Channel", "ch1"),
    )
    await db.commit()
    return db


# ---------------------------------------------------------------------------
# Service tests
# ---------------------------------------------------------------------------


async def test_get_segments_returns_parsed_segments(db_with_video):
    """Happy path: API returns fixture data; service returns parsed list of dicts."""
    mock_cls, mock_client = _mock_httpx_client(
        _make_httpx_response(200, SPONSORBLOCK_FIXTURE)
    )

    with patch("backend.services.sponsorblock.httpx.AsyncClient", mock_cls):
        segments = await get_segments("test_video", db_with_video)

    assert len(segments) == 2

    assert segments[0]["start"] == 30.5
    assert segments[0]["end"] == 60.2
    assert segments[0]["category"] == "sponsor"

    assert segments[1]["start"] == 180.0
    assert segments[1]["end"] == 195.5
    assert segments[1]["category"] == "intro"


async def test_get_segments_returns_empty_on_404(db_with_video):
    """When SponsorBlock returns 404, service returns an empty list."""
    mock_cls, mock_client = _mock_httpx_client(_make_httpx_response(404))

    with patch("backend.services.sponsorblock.httpx.AsyncClient", mock_cls):
        segments = await get_segments("test_video", db_with_video)

    assert segments == []


async def test_get_segments_returns_empty_on_timeout(db_with_video):
    """When httpx raises TimeoutException, service returns an empty list."""
    from httpx import TimeoutException

    mock_client = AsyncMock()
    mock_client.get = AsyncMock(side_effect=TimeoutException("timeout"))

    mock_cls = MagicMock()
    mock_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
    mock_cls.return_value.__aexit__ = AsyncMock(return_value=False)

    with patch("backend.services.sponsorblock.httpx.AsyncClient", mock_cls):
        segments = await get_segments("test_video", db_with_video)

    assert segments == []


async def test_get_segments_caches_in_db(db_with_video):
    """Second call reads from DB cache; httpx is only called once."""
    mock_cls, mock_client = _mock_httpx_client(
        _make_httpx_response(200, SPONSORBLOCK_FIXTURE)
    )

    with patch("backend.services.sponsorblock.httpx.AsyncClient", mock_cls):
        first = await get_segments("test_video", db_with_video)
        second = await get_segments("test_video", db_with_video)

    # httpx should only have been entered once (first call fetches; second reads cache)
    assert mock_cls.call_count == 1
    assert first == second
    assert len(first) == 2


async def test_get_segments_caches_empty_list(db_with_video):
    """404 response is cached as '[]'; second call does not hit the API."""
    mock_cls, mock_client = _mock_httpx_client(_make_httpx_response(404))

    with patch("backend.services.sponsorblock.httpx.AsyncClient", mock_cls):
        first = await get_segments("test_video", db_with_video)

    # Verify DB contains "[]"
    async with db_with_video.execute(
        "SELECT sponsor_segments_json FROM videos WHERE id = ?", ("test_video",)
    ) as cursor:
        row = await cursor.fetchone()
    assert row is not None
    assert row[0] == "[]"

    # Second call should read from cache, not hit API again
    with patch("backend.services.sponsorblock.httpx.AsyncClient", mock_cls):
        second = await get_segments("test_video", db_with_video)

    # Total calls across both patches should still be 1
    assert mock_cls.call_count == 1
    assert second == []


# ---------------------------------------------------------------------------
# Endpoint tests
# ---------------------------------------------------------------------------


async def test_endpoint_returns_correct_format():
    """GET /api/sponsorblock/{video_id} returns correct JSON shape."""
    from backend.api.main import app

    async def mock_get_db():
        conn = await aiosqlite.connect(":memory:")
        conn.row_factory = aiosqlite.Row
        await _run_migrations(conn)
        # Seed a video row
        await conn.execute(
            "INSERT INTO videos (id, title, channel_name, channel_id) VALUES (?, ?, ?, ?)",
            ("test", "Test", "Channel", "ch1"),
        )
        await conn.commit()
        return conn

    mock_cls, _ = _mock_httpx_client(_make_httpx_response(200, SPONSORBLOCK_FIXTURE))

    with patch("backend.api.routers.video.get_db", side_effect=mock_get_db):
        with patch("backend.services.sponsorblock.httpx.AsyncClient", mock_cls):
            transport = ASGITransport(app=app)
            async with AsyncClient(transport=transport, base_url="http://test") as ac:
                response = await ac.get("/api/sponsorblock/test")

    assert response.status_code == 200
    body = response.json()
    assert "video_id" in body
    assert "segments" in body
    assert body["video_id"] == "test"
    assert isinstance(body["segments"], list)
    assert len(body["segments"]) == 2
    assert body["segments"][0]["start"] == 30.5
    assert body["segments"][0]["end"] == 60.2
    assert body["segments"][0]["category"] == "sponsor"
