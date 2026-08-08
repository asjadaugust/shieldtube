"""Fetch latest uploads from the user's most-watched channels."""

import logging
from datetime import datetime, timezone
from urllib.parse import urlencode

import aiosqlite
import httpx

from backend.db.repositories import VideoRepo
from backend.services.auth_manager import AuthManager
from backend.services.retry import with_retry
from backend.services.thumbnail_cache import ThumbnailCache

logger = logging.getLogger(__name__)

_YT_API_BASE = "https://www.googleapis.com/youtube/v3"


class ChannelFeedRefresher:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get_top_channels(self, limit: int = 20) -> list[dict]:
        """Return the top N channels by watch count from history."""
        cursor = await self._db.execute(
            """SELECT v.channel_id, v.channel_name, COUNT(*) as watch_count
               FROM watch_history wh
               JOIN videos v ON v.id = wh.video_id
               WHERE v.channel_id IS NOT NULL AND v.channel_id != ''
               GROUP BY v.channel_id
               ORDER BY watch_count DESC
               LIMIT ?""",
            (limit,),
        )
        rows = await cursor.fetchall()
        return [{"channel_id": r["channel_id"], "channel_name": r["channel_name"], "watch_count": r["watch_count"]} for r in rows]

    async def fetch_latest_uploads(self, channel_id: str, max_results: int = 5) -> list[str]:
        """Fetch latest video IDs from a channel via YouTube search API."""
        auth = AuthManager(self._db)
        headers = await auth.get_auth_headers()

        async with httpx.AsyncClient() as client:
            async def _do_request():
                return await client.get(
                    f"{_YT_API_BASE}/search?"
                    + urlencode({
                        "part": "snippet",
                        "channelId": channel_id,
                        "order": "date",
                        "type": "video",
                        "maxResults": max_results,
                    }),
                    headers=headers,
                )
            resp = await with_retry(_do_request, description=f"YouTube channel search {channel_id}")
            resp.raise_for_status()

        items = resp.json().get("items", [])
        return [item["id"]["videoId"] for item in items if item.get("id", {}).get("videoId")]

    async def refresh(self) -> int:
        """Fetch latest uploads from top channels and persist them.

        Returns the number of new videos discovered.
        """
        channels = await self.get_top_channels(limit=20)
        if not channels:
            logger.info("No channels in watch history — skipping channel feed refresh")
            return 0

        auth = AuthManager(self._db)
        api_client = type("_YT", (), {})()  # We'll use YouTubeAPI for enrichment
        from backend.services.youtube_api import YouTubeAPI
        yt = YouTubeAPI(auth, self._db)

        all_video_ids: list[str] = []
        channel_map: dict[str, str] = {}  # video_id -> channel_id

        for ch in channels:
            try:
                video_ids = await self.fetch_latest_uploads(ch["channel_id"], max_results=5)
                for vid in video_ids:
                    channel_map[vid] = ch["channel_id"]
                all_video_ids.extend(video_ids)
            except Exception as e:
                logger.warning("Failed to fetch uploads for %s: %s", ch["channel_name"], e)

        if not all_video_ids:
            return 0

        # Deduplicate
        all_video_ids = list(dict.fromkeys(all_video_ids))

        # Enrich with full metadata and upsert into videos table (batch 50 at a time)
        try:
            video_repo = VideoRepo(self._db)
            thumb = ThumbnailCache(self._db)
            for i in range(0, len(all_video_ids), 50):
                batch = all_video_ids[i:i + 50]
                video_details = await yt.get_video_details(batch)
                await video_repo.upsert_many_from_dicts(video_details)
                await thumb.cache_thumbnails(video_details)
        except Exception as e:
            logger.warning("Failed to enrich channel feed videos: %s", e)

        # Upsert into channel_feed_cache
        now = datetime.now(timezone.utc).isoformat()
        for vid in all_video_ids:
            ch_id = channel_map.get(vid, "")
            await self._db.execute(
                "INSERT OR REPLACE INTO channel_feed_cache (video_id, channel_id, fetched_at) VALUES (?, ?, ?)",
                (vid, ch_id, now),
            )
        await self._db.commit()

        logger.info("Channel feed refreshed: %d videos from %d channels", len(all_video_ids), len(channels))
        return len(all_video_ids)
