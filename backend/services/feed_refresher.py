import asyncio
import logging
import time
from pathlib import Path

import aiosqlite

from backend.services.youtube_api import YouTubeAPI
from backend.services.auth_manager import AuthManager
from backend.services.thumbnail_cache import ThumbnailCache
from backend.services.precache import load_rules, match_videos
from backend.db.repositories import VideoRepo

logger = logging.getLogger(__name__)

HOME_INTERVAL = 900    # 15 minutes
SUBS_INTERVAL = 300    # 5 minutes


class FeedRefresher:
    def __init__(self, db: aiosqlite.Connection, download_queue=None):
        self._db = db
        self._download_queue = download_queue
        self._task: asyncio.Task | None = None

    async def start(self):
        self._task = asyncio.create_task(self._refresh_loop())
        logger.info("Feed refresher started")

    async def stop(self):
        if self._task:
            self._task.cancel()
            try:
                await self._task
            except asyncio.CancelledError:
                pass
        logger.info("Feed refresher stopped")

    async def _refresh_loop(self):
        last_home = 0.0
        last_subs = 0.0

        # Wait a bit before first refresh (let the app fully start)
        await asyncio.sleep(30)

        while True:
            try:
                now = time.time()

                if now - last_home >= HOME_INTERVAL:
                    await self._refresh_home()
                    last_home = time.time()

                if now - last_subs >= SUBS_INTERVAL:
                    await self._refresh_subscriptions()
                    last_subs = time.time()

            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.error(f"Feed refresh error: {e}")

            await asyncio.sleep(60)  # Check every minute

    async def _refresh_home(self):
        logger.info("Refreshing home feed...")
        try:
            auth = AuthManager(self._db)
            api = YouTubeAPI(auth, self._db)
            thumb = ThumbnailCache(self._db)
            video_repo = VideoRepo(self._db)

            videos, from_cache, _ = await api.get_home_feed()

            if not from_cache:
                await video_repo.upsert_many_from_dicts(videos)
                await thumb.cache_thumbnails(videos)
                await self._check_precache(videos)
                logger.info(f"Home feed refreshed: {len(videos)} videos")
            else:
                logger.info("Home feed unchanged (ETag match)")
        except Exception as e:
            logger.error(f"Home feed refresh failed: {e}")

    async def _refresh_subscriptions(self):
        logger.info("Refreshing subscriptions feed...")
        try:
            auth = AuthManager(self._db)
            api = YouTubeAPI(auth, self._db)
            thumb = ThumbnailCache(self._db)
            video_repo = VideoRepo(self._db)

            videos, from_cache, _ = await api.get_subscriptions()

            if not from_cache:
                await video_repo.upsert_many_from_dicts(videos)
                await thumb.cache_thumbnails(videos)
                await self._check_precache(videos)
                logger.info(f"Subscriptions refreshed: {len(videos)} videos")
            else:
                logger.info("Subscriptions unchanged (ETag match)")
        except Exception as e:
            logger.error(f"Subscriptions refresh failed: {e}")

    async def _check_precache(self, videos: list[dict]):
        try:
            rules = load_rules(Path("config/precache_rules.json"))
            if rules and self._download_queue:
                to_cache = await match_videos(videos, rules, self._db)
                if to_cache:
                    await self._download_queue.enqueue_many(to_cache)
                    logger.info(f"Pre-cache: queued {len(to_cache)} videos")
        except Exception as e:
            logger.warning(f"Pre-cache check failed: {e}")
