"""Search endpoint."""
import asyncio

from fastapi import APIRouter, Query

from backend.db.database import get_db
from backend.db.repositories import VideoRepo
from backend.services.auth_manager import AuthManager
from backend.services.youtube_api import YouTubeAPI
from backend.services.thumbnail_cache import ThumbnailCache

router = APIRouter()


@router.get("/search")
async def search_videos(q: str = Query(..., min_length=1)):
    """Search YouTube and return matching videos."""
    db = await get_db()
    auth_manager = AuthManager(db)
    youtube_api = YouTubeAPI(auth_manager, db)
    thumb_cache = ThumbnailCache(db)
    video_repo = VideoRepo(db)

    videos = await youtube_api.search(q)

    if videos:
        await video_repo.upsert_many_from_dicts(videos)
        asyncio.create_task(thumb_cache.cache_thumbnails(videos))

    return {
        "feed_type": f"search:{q}",
        "videos": [
            {
                "id": v["id"],
                "title": v.get("title", ""),
                "channel_name": v.get("channel_name", ""),
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
