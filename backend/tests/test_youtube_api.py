"""Tests for YouTubeAPI — written TDD-style (failing first, then implemented)."""
import json
import pytest
import aiosqlite
from datetime import datetime, timezone
from unittest.mock import AsyncMock, MagicMock, patch

from backend.db.database import _run_migrations
from backend.services.auth_manager import AuthManager
from backend.services.youtube_api import YouTubeAPI


# ---------------------------------------------------------------------------
# Shared DB fixture
# ---------------------------------------------------------------------------

@pytest.fixture
async def db():
    conn = await aiosqlite.connect(":memory:")
    conn.row_factory = aiosqlite.Row
    await _run_migrations(conn)
    yield conn
    await conn.close()


# ---------------------------------------------------------------------------
# Fixture factories
# ---------------------------------------------------------------------------

def _make_video_item(
    video_id: str = "dQw4w9WgXcQ",
    title: str = "Never Gonna Give You Up",
    channel_title: str = "Rick Astley",
    channel_id: str = "UCuAXFkgsw1L7xaCfnd5JJOw",
    published_at: str = "2009-10-25T06:57:33Z",
    description: str = "The official video...",
    duration: str = "PT3M33S",
    view_count: str = "1500000000",
) -> dict:
    return {
        "id": video_id,
        "snippet": {
            "title": title,
            "channelTitle": channel_title,
            "channelId": channel_id,
            "publishedAt": published_at,
            "description": description,
        },
        "contentDetails": {"duration": duration},
        "statistics": {"viewCount": view_count},
    }


def _make_videos_response(items: list[dict], etag: str = "abc123") -> dict:
    return {"etag": etag, "items": items}


def _make_mock_http_response(
    status_code: int = 200, json_body: dict | None = None, headers: dict | None = None
) -> MagicMock:
    resp = MagicMock()
    resp.status_code = status_code
    resp.json.return_value = json_body or {}
    resp.headers = headers or {}
    resp.raise_for_status = MagicMock()
    return resp


def _make_mock_auth_manager(token: str = "test-token") -> MagicMock:
    auth = MagicMock(spec=AuthManager)
    auth.get_auth_headers = AsyncMock(return_value={"Authorization": f"Bearer {token}"})
    return auth


def _make_mock_client(get_responses: list | None = None) -> AsyncMock:
    """Build a mock httpx.AsyncClient that returns responses in order."""
    mock_client = AsyncMock()
    mock_client.__aenter__ = AsyncMock(return_value=mock_client)
    mock_client.__aexit__ = AsyncMock(return_value=False)

    if get_responses:
        mock_client.get = AsyncMock(side_effect=get_responses)
    return mock_client


# ---------------------------------------------------------------------------
# _parse_duration tests (unit — no I/O)
# ---------------------------------------------------------------------------

def test_parse_duration_minutes_and_seconds():
    api = YouTubeAPI.__new__(YouTubeAPI)
    assert api._parse_duration("PT4M33S") == 273


def test_parse_duration_hours_minutes_seconds():
    api = YouTubeAPI.__new__(YouTubeAPI)
    assert api._parse_duration("PT1H2M3S") == 3723


def test_parse_duration_seconds_only():
    api = YouTubeAPI.__new__(YouTubeAPI)
    assert api._parse_duration("PT30S") == 30


def test_parse_duration_hours_only():
    api = YouTubeAPI.__new__(YouTubeAPI)
    assert api._parse_duration("PT1H") == 3600


def test_parse_duration_minutes_only():
    api = YouTubeAPI.__new__(YouTubeAPI)
    assert api._parse_duration("PT5M") == 300


def test_parse_duration_zero():
    api = YouTubeAPI.__new__(YouTubeAPI)
    assert api._parse_duration("PT0S") == 0


# ---------------------------------------------------------------------------
# get_video_details tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_video_details_parses_duration(db):
    """get_video_details correctly parses PT3M33S → 213 seconds."""
    auth = _make_mock_auth_manager()
    api = YouTubeAPI(auth, db)

    item = _make_video_item(duration="PT3M33S")
    resp = _make_mock_http_response(json_body=_make_videos_response([item]))
    mock_client = _make_mock_client(get_responses=[resp])

    with patch("backend.services.youtube_api.httpx.AsyncClient", return_value=mock_client):
        videos = await api.get_video_details(["dQw4w9WgXcQ"])

    assert len(videos) == 1
    assert videos[0]["duration"] == 213  # 3*60+33


@pytest.mark.asyncio
async def test_get_video_details_parses_fields(db):
    """get_video_details returns dict with expected keys."""
    auth = _make_mock_auth_manager()
    api = YouTubeAPI(auth, db)

    item = _make_video_item()
    resp = _make_mock_http_response(json_body=_make_videos_response([item]))
    mock_client = _make_mock_client(get_responses=[resp])

    with patch("backend.services.youtube_api.httpx.AsyncClient", return_value=mock_client):
        videos = await api.get_video_details(["dQw4w9WgXcQ"])

    v = videos[0]
    assert v["id"] == "dQw4w9WgXcQ"
    assert v["title"] == "Never Gonna Give You Up"
    assert v["channel_name"] == "Rick Astley"
    assert v["channel_id"] == "UCuAXFkgsw1L7xaCfnd5JJOw"
    assert v["view_count"] == 1500000000
    assert v["published_at"] == "2009-10-25T06:57:33Z"
    assert v["description"] == "The official video..."


# ---------------------------------------------------------------------------
# get_home_feed tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_get_home_feed_200_returns_parsed_videos(db):
    """On first fetch (200), returns (videos, False, None) and stores ETag."""
    auth = _make_mock_auth_manager()
    api = YouTubeAPI(auth, db)

    item = _make_video_item()
    resp = _make_mock_http_response(
        json_body=_make_videos_response([item], etag="etag-v1"),
        headers={"ETag": "etag-v1"},
    )
    mock_client = _make_mock_client(get_responses=[resp])

    with patch("backend.services.youtube_api.httpx.AsyncClient", return_value=mock_client):
        videos, from_cache, cached_at = await api.get_home_feed(max_results=1)

    assert from_cache is False
    assert cached_at is None
    assert len(videos) == 1
    assert videos[0]["id"] == "dQw4w9WgXcQ"

    # ETag should be stored in DB
    row = await (
        await db.execute("SELECT etag FROM feed_cache WHERE feed_type = 'home'")
    ).fetchone()
    assert row is not None
    assert row["etag"] == "etag-v1"


@pytest.mark.asyncio
async def test_get_home_feed_304_returns_cached(db):
    """On cache hit (304), loads video IDs from feed_cache, returns (videos, True, fetched_at)."""
    # Pre-populate feed_cache
    fetched_at = "2026-03-20T12:00:00+00:00"
    video_ids = ["dQw4w9WgXcQ"]
    await db.execute(
        "INSERT INTO feed_cache (feed_type, video_ids_json, etag, fetched_at) VALUES (?, ?, ?, ?)",
        ("home", json.dumps(video_ids), "etag-v1", fetched_at),
    )
    # Pre-populate videos table
    await db.execute(
        """INSERT INTO videos (id, title, channel_name, channel_id, view_count, duration, published_at)
           VALUES (?, ?, ?, ?, ?, ?, ?)""",
        ("dQw4w9WgXcQ", "Never Gonna Give You Up", "Rick Astley",
         "UCuAXFkgsw1L7xaCfnd5JJOw", 1500000000, 213, "2009-10-25T06:57:33Z"),
    )
    await db.commit()

    auth = _make_mock_auth_manager()
    api = YouTubeAPI(auth, db)

    resp_304 = _make_mock_http_response(status_code=304)
    mock_client = _make_mock_client(get_responses=[resp_304])

    with patch("backend.services.youtube_api.httpx.AsyncClient", return_value=mock_client):
        videos, from_cache, returned_cached_at = await api.get_home_feed()

    assert from_cache is True
    assert returned_cached_at == fetched_at
    assert len(videos) == 1
    assert videos[0]["id"] == "dQw4w9WgXcQ"


# ---------------------------------------------------------------------------
# search tests
# ---------------------------------------------------------------------------

@pytest.mark.asyncio
async def test_search_enriches_with_video_details(db):
    """search() calls get_video_details() to enrich sparse search results."""
    auth = _make_mock_auth_manager()
    api = YouTubeAPI(auth, db)

    search_response = {
        "items": [
            {
                "id": {"videoId": "dQw4w9WgXcQ"},
                "snippet": {"title": "Never Gonna Give You Up"},
            }
        ]
    }
    detail_item = _make_video_item()
    detail_response = _make_mock_http_response(
        json_body=_make_videos_response([detail_item])
    )
    search_resp = _make_mock_http_response(json_body=search_response)

    mock_client = _make_mock_client(get_responses=[search_resp, detail_response])

    with patch("backend.services.youtube_api.httpx.AsyncClient", return_value=mock_client):
        results = await api.search("never gonna give you up", max_results=1)

    assert len(results) == 1
    assert results[0]["id"] == "dQw4w9WgXcQ"
    assert results[0]["title"] == "Never Gonna Give You Up"
    assert results[0]["duration"] == 213


@pytest.mark.asyncio
async def test_search_returns_empty_for_no_results(db):
    """search() handles empty items list gracefully."""
    auth = _make_mock_auth_manager()
    api = YouTubeAPI(auth, db)

    search_response = {"items": []}
    search_resp = _make_mock_http_response(json_body=search_response)
    mock_client = _make_mock_client(get_responses=[search_resp])

    with patch("backend.services.youtube_api.httpx.AsyncClient", return_value=mock_client):
        results = await api.search("xyzzy-no-results", max_results=5)

    assert results == []
