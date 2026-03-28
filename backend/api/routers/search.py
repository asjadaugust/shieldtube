"""Search endpoint — YouTube Data API with yt-dlp fallback."""
import asyncio
import logging

from fastapi import APIRouter, Query

from backend.db.database import get_db
from backend.db.repositories import VideoRepo
from backend.services.auth_manager import AuthManager
from backend.services.youtube_api import YouTubeAPI
from backend.services.thumbnail_cache import ThumbnailCache

router = APIRouter()
logger = logging.getLogger(__name__)


def _build_response(q, videos):
    return {
        "feed_type": f"search:{q}",
        "videos": [
            {
                "id": v["id"],
                "title": v.get("title", ""),
                "channel_name": v.get("channel_name", v.get("channel", "")),
                "channel_id": v.get("channel_id", ""),
                "view_count": v.get("view_count"),
                "duration": v.get("duration"),
                "published_at": v.get("published_at"),
                "thumbnail_url": f"/api/video/{v['id']}/thumbnail?res=maxres",
            }
            for v in videos
        ],
        "cached_at": None,
        "from_cache": False,
    }


async def _ytdlp_search(query: str, max_results: int = 20) -> list[dict]:
    """Fallback search using yt-dlp scraping (no API quota)."""
    import yt_dlp

    def _do_search():
        opts = {
            "quiet": True,
            "no_warnings": True,
            "extract_flat": True,
            "playlist_items": f"1:{max_results}",
        }
        with yt_dlp.YoutubeDL(opts) as ydl:
            result = ydl.extract_info(f"ytsearch{max_results}:{query}", download=False)
            return [
                {
                    "id": e["id"],
                    "title": e.get("title", ""),
                    "channel_name": e.get("channel", e.get("uploader", "")),
                    "channel_id": e.get("channel_id", ""),
                    "view_count": e.get("view_count"),
                    "duration": int(e["duration"]) if e.get("duration") else None,
                    "published_at": e.get("upload_date"),
                }
                for e in result.get("entries", [])
                if e.get("id")
            ]

    return await asyncio.to_thread(_do_search)


@router.get("/search")
async def search_videos(q: str = Query(..., min_length=1)):
    """Search YouTube. Uses Data API first, falls back to yt-dlp on quota error."""
    db = await get_db()
    thumb_cache = ThumbnailCache(db)
    video_repo = VideoRepo(db)

    # Try YouTube Data API first
    try:
        auth_manager = AuthManager(db)
        youtube_api = YouTubeAPI(auth_manager, db)
        videos = await youtube_api.search(q)

        if videos:
            await video_repo.upsert_many_from_dicts(videos)
            asyncio.create_task(thumb_cache.cache_thumbnails(videos))

        return _build_response(q, videos)
    except Exception as api_err:
        logger.warning("YouTube API search failed, falling back to yt-dlp: %s", api_err)

    # Fallback: yt-dlp scraping (no quota)
    videos = await _ytdlp_search(q)
    return _build_response(q, videos)
