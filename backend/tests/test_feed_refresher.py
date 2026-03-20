"""Tests for the FeedRefresher background service."""
import asyncio
from pathlib import Path
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from backend.services.feed_refresher import FeedRefresher

pytestmark = pytest.mark.asyncio


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_refresher(download_queue=None):
    """Return a FeedRefresher with a dummy db connection."""
    db = MagicMock()
    return FeedRefresher(db, download_queue=download_queue)


# ---------------------------------------------------------------------------
# Tests
# ---------------------------------------------------------------------------

async def test_refresher_starts_and_stops():
    """start() creates a background task; stop() cancels it cleanly."""
    refresher = _make_refresher()
    await refresher.start()

    assert refresher._task is not None
    assert not refresher._task.done()

    await refresher.stop()

    assert refresher._task.done()


async def test_refresh_home_calls_api():
    """_refresh_home() calls YouTubeAPI.get_home_feed and upserts results."""
    refresher = _make_refresher()

    videos = [{"id": "v1", "title": "T", "channel_name": "C", "channel_id": "UC1"}]

    mock_api = MagicMock()
    mock_api.get_home_feed = AsyncMock(return_value=(videos, False, None))

    mock_repo = MagicMock()
    mock_repo.upsert_many_from_dicts = AsyncMock()

    mock_thumb = MagicMock()
    mock_thumb.cache_thumbnails = AsyncMock()

    with (
        patch("backend.services.feed_refresher.YouTubeAPI", return_value=mock_api),
        patch("backend.services.feed_refresher.VideoRepo", return_value=mock_repo),
        patch("backend.services.feed_refresher.ThumbnailCache", return_value=mock_thumb),
        patch("backend.services.feed_refresher.load_rules", return_value=[]),
    ):
        await refresher._refresh_home()

    mock_api.get_home_feed.assert_called_once()
    mock_repo.upsert_many_from_dicts.assert_called_once_with(videos)
    mock_thumb.cache_thumbnails.assert_called_once_with(videos)


async def test_refresh_home_skips_cached():
    """_refresh_home() skips upsert and thumbnail caching when from_cache=True."""
    refresher = _make_refresher()

    mock_api = MagicMock()
    mock_api.get_home_feed = AsyncMock(return_value=([], True, "2024-01-01T00:00:00Z"))

    mock_repo = MagicMock()
    mock_repo.upsert_many_from_dicts = AsyncMock()

    mock_thumb = MagicMock()
    mock_thumb.cache_thumbnails = AsyncMock()

    with (
        patch("backend.services.feed_refresher.YouTubeAPI", return_value=mock_api),
        patch("backend.services.feed_refresher.VideoRepo", return_value=mock_repo),
        patch("backend.services.feed_refresher.ThumbnailCache", return_value=mock_thumb),
    ):
        await refresher._refresh_home()

    mock_repo.upsert_many_from_dicts.assert_not_called()
    mock_thumb.cache_thumbnails.assert_not_called()


async def test_refresh_subs_calls_api():
    """_refresh_subscriptions() calls YouTubeAPI.get_subscriptions and upserts results."""
    refresher = _make_refresher()

    videos = [{"id": "v2", "title": "T2", "channel_name": "C2", "channel_id": "UC2"}]

    mock_api = MagicMock()
    mock_api.get_subscriptions = AsyncMock(return_value=(videos, False, None))

    mock_repo = MagicMock()
    mock_repo.upsert_many_from_dicts = AsyncMock()

    mock_thumb = MagicMock()
    mock_thumb.cache_thumbnails = AsyncMock()

    with (
        patch("backend.services.feed_refresher.YouTubeAPI", return_value=mock_api),
        patch("backend.services.feed_refresher.VideoRepo", return_value=mock_repo),
        patch("backend.services.feed_refresher.ThumbnailCache", return_value=mock_thumb),
        patch("backend.services.feed_refresher.load_rules", return_value=[]),
    ):
        await refresher._refresh_subscriptions()

    mock_api.get_subscriptions.assert_called_once()
    mock_repo.upsert_many_from_dicts.assert_called_once_with(videos)
    mock_thumb.cache_thumbnails.assert_called_once_with(videos)


async def test_check_precache_queues_matches():
    """_check_precache() calls enqueue_many with matched video IDs."""
    mock_queue = MagicMock()
    mock_queue.enqueue_many = AsyncMock()

    refresher = _make_refresher(download_queue=mock_queue)

    videos = [{"id": "v1", "channel_id": "UC1"}, {"id": "v2", "channel_id": "UC2"}]
    rules = [{"type": "channel", "channel_id": "UC1"}]
    matched = ["v1"]

    with (
        patch("backend.services.feed_refresher.load_rules", return_value=rules),
        patch("backend.services.feed_refresher.match_videos", new=AsyncMock(return_value=matched)),
    ):
        await refresher._check_precache(videos)

    mock_queue.enqueue_many.assert_called_once_with(matched)


async def test_check_precache_no_queue():
    """_check_precache() is a no-op when download_queue is None."""
    refresher = _make_refresher(download_queue=None)

    rules = [{"type": "channel", "channel_id": "UC1"}]
    videos = [{"id": "v1", "channel_id": "UC1"}]

    with (
        patch("backend.services.feed_refresher.load_rules", return_value=rules),
        patch("backend.services.feed_refresher.match_videos", new=AsyncMock(return_value=["v1"])),
    ):
        # Should not raise even though there is no queue
        await refresher._check_precache(videos)


async def test_check_precache_no_rules():
    """_check_precache() does not call enqueue_many when there are no rules."""
    mock_queue = MagicMock()
    mock_queue.enqueue_many = AsyncMock()

    refresher = _make_refresher(download_queue=mock_queue)

    with patch("backend.services.feed_refresher.load_rules", return_value=[]):
        await refresher._check_precache([{"id": "v1", "channel_id": "UC1"}])

    mock_queue.enqueue_many.assert_not_called()
