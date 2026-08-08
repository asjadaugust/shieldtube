import asyncio
import logging
import time
import uuid
from datetime import datetime, timezone
from pathlib import Path

import aiosqlite

from backend.services.youtube_api import YouTubeAPI
from backend.services.auth_manager import AuthManager
from backend.services.thumbnail_cache import ThumbnailCache
from backend.services.precache import load_rules, match_videos
from backend.db.repositories import VideoRepo, RecommendationRepo
from backend.db.models import RecommendationRun, Recommendation

logger = logging.getLogger(__name__)

HOME_INTERVAL = 3600            # 1 hour (1 API unit per refresh)
WATCH_LATER_INTERVAL = 3600     # 1 hour
RECOMMEND_INTERVAL = 6 * 3600   # 6 hours
CHANNEL_FEED_INTERVAL = 3 * 3600  # 3 hours


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
        last_watch_later = 0.0
        last_recommend = 0.0
        last_channel_feed = 0.0

        # Wait a bit before first refresh (let the app fully start)
        await asyncio.sleep(30)

        while True:
            try:
                now = time.time()

                if now - last_home >= HOME_INTERVAL:
                    await self._refresh_home()
                    last_home = time.time()

                if now - last_watch_later >= WATCH_LATER_INTERVAL:
                    await self._refresh_watch_later()
                    last_watch_later = time.time()

                if now - last_recommend >= RECOMMEND_INTERVAL:
                    await self._refresh_recommendations()
                    last_recommend = time.time()

                if now - last_channel_feed >= CHANNEL_FEED_INTERVAL:
                    await self._refresh_channel_feed()
                    last_channel_feed = time.time()

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

    async def _refresh_watch_later(self):
        logger.info("Refreshing Watch Later feed...")
        try:
            auth = AuthManager(self._db)
            api = YouTubeAPI(auth, self._db)
            thumb = ThumbnailCache(self._db)
            video_repo = VideoRepo(self._db)

            videos, from_cache, _ = await api.get_watch_later()

            if not from_cache:
                await video_repo.upsert_many_from_dicts(videos)
                await thumb.cache_thumbnails(videos)
                logger.info(f"Watch Later feed refreshed: {len(videos)} videos")
            else:
                logger.info("Watch Later feed unchanged (ETag match)")
        except Exception as e:
            logger.error(f"Watch Later feed refresh failed: {e}")

    async def _refresh_channel_feed(self):
        """Fetch latest uploads from top watched channels."""
        logger.info("Refreshing channel feed...")
        try:
            from backend.services.channel_feed import ChannelFeedRefresher
            refresher = ChannelFeedRefresher(self._db)
            count = await refresher.refresh()
            logger.info(f"Channel feed refresh complete: {count} videos")
        except Exception as e:
            logger.error(f"Channel feed refresh failed: {e}")

    async def _refresh_recommendations(self):
        """Generate fresh heuristic recommendations and persist as a run."""
        logger.info("Refreshing heuristic recommendations...")
        try:
            from backend.services.heuristic_rec import HeuristicRecommender

            heuristic = HeuristicRecommender(self._db)
            recs = await heuristic.get_recommendations(limit=50)
            if not recs:
                logger.info("No heuristic recommendations generated (no watch history?)")
                return

            rec_repo = RecommendationRepo(self._db)
            run_id = f"heuristic-{uuid.uuid4().hex[:8]}"
            now = datetime.now(timezone.utc).isoformat()

            await rec_repo.upsert_run(RecommendationRun(
                run_id=run_id,
                run_at=now,
                source="heuristic",
                model_name=None,
                video_count=len(recs),
            ))
            await rec_repo.upsert_recommendations(run_id, [
                Recommendation(
                    video_id=r["id"],
                    run_id=run_id,
                    score=r["score"],
                    source="heuristic",
                    reason=None,
                )
                for r in recs
            ])
            logger.info(f"Heuristic recommendations refreshed: {len(recs)} videos (run={run_id})")

            # Auto-enqueue recommended videos for download (skip already cached)
            if self._download_queue:
                video_repo = VideoRepo(self._db)
                to_enqueue = []
                for r in recs:
                    existing = await video_repo.get(r["id"])
                    if existing and existing.cache_status in ("cached", "pre-cached"):
                        continue
                    to_enqueue.append(r["id"])
                if to_enqueue:
                    await self._download_queue.enqueue_many(to_enqueue)
                    logger.info(f"Auto-enqueued {len(to_enqueue)} recommended videos for download")
        except Exception as e:
            logger.error(f"Recommendation refresh failed: {e}")

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
