"""Tests for shorts_feed service."""
import time
import pytest
from unittest.mock import AsyncMock, patch

pytestmark = pytest.mark.asyncio


def _make_mock_db(rows):
    cursor = AsyncMock()
    cursor.fetchall = AsyncMock(return_value=rows)
    db = AsyncMock()
    db.execute = AsyncMock(return_value=cursor)
    return db


async def test_recommended_returns_empty_when_no_channels():
    """No watch history → no top channels → empty list."""
    from backend.services import shorts_feed
    shorts_feed._CACHE.clear()

    db = _make_mock_db([])
    result = await shorts_feed.get_recommended_shorts(db)
    assert result == []


async def test_recommended_returns_cached_result():
    """Within TTL, returns cached result without hitting DB."""
    from backend.services import shorts_feed
    shorts_feed._CACHE["recommended"] = (time.monotonic(), [{"id": "abc", "title": "Cached Short"}])

    db = _make_mock_db([])  # would return empty if called
    result = await shorts_feed.get_recommended_shorts(db)

    assert len(result) == 1
    assert result[0]["id"] == "abc"
    shorts_feed._CACHE.clear()


async def test_trending_returns_cached_result():
    """Within TTL, get_trending_shorts returns cached result without scraping."""
    from backend.services import shorts_feed
    shorts_feed._CACHE["trending"] = (time.monotonic(), [{"id": "xyz", "title": "Trending Short"}])

    result = await shorts_feed.get_trending_shorts()

    assert len(result) == 1
    assert result[0]["id"] == "xyz"
    shorts_feed._CACHE.clear()


async def test_recommended_skips_failed_channels():
    """If one channel scrape fails, result still contains others."""
    from backend.services import shorts_feed
    shorts_feed._CACHE.clear()

    rows = [
        {"channel_id": "UC_GOOD", "channel_name": "Good Channel", "watch_count": 10},
        {"channel_id": "UC_BAD", "channel_name": "Bad Channel", "watch_count": 5},
    ]
    db = _make_mock_db(rows)

    def fake_scrape(channel_id, limit=5):
        if channel_id == "UC_BAD":
            raise RuntimeError("yt-dlp failed")
        return [{"id": "v1", "title": "Short 1", "channel_name": "Good Channel",
                 "channel_id": channel_id, "duration": 30, "published_at": None,
                 "thumbnail_url": "/api/video/v1/thumbnail?res=maxres"}]

    with patch("backend.services.shorts_feed._scrape_channel_shorts", side_effect=fake_scrape):
        with patch("asyncio.to_thread", side_effect=lambda fn, *a, **kw: fn(*a, **kw)):
            result = await shorts_feed.get_recommended_shorts(db)

    assert len(result) == 1
    assert result[0]["id"] == "v1"
    shorts_feed._CACHE.clear()
