"""Feed endpoints: home and subscriptions."""
import asyncio

from fastapi import APIRouter

from backend.db.database import get_db
from backend.db.repositories import VideoRepo
from backend.services.auth_manager import AuthManager
from backend.services.youtube_api import YouTubeAPI
from backend.services.thumbnail_cache import ThumbnailCache

router = APIRouter()


def _build_response(feed_type: str, videos: list[dict], from_cache: bool, cached_at) -> dict:
    """Normalise a list of video dicts into the standard feed response."""
    return {
        "feed_type": feed_type,
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
        "cached_at": cached_at,
        "from_cache": from_cache,
    }


@router.get("/feed/home")
async def get_home_feed():
    """Return the YouTube most-popular videos feed."""
    db = await get_db()
    auth_manager = AuthManager(db)
    youtube_api = YouTubeAPI(auth_manager, db)
    thumb_cache = ThumbnailCache(db)
    video_repo = VideoRepo(db)

    videos, from_cache, cached_at = await youtube_api.get_home_feed()

    if not from_cache:
        await video_repo.upsert_many_from_dicts(videos)
        asyncio.create_task(thumb_cache.cache_thumbnails(videos))

    return _build_response("home", videos, from_cache, cached_at)


@router.get("/feed/subscriptions")
async def get_subscriptions_feed():
    """Return recent uploads from the authenticated user's subscriptions."""
    db = await get_db()
    auth_manager = AuthManager(db)
    youtube_api = YouTubeAPI(auth_manager, db)
    thumb_cache = ThumbnailCache(db)
    video_repo = VideoRepo(db)

    videos, from_cache, cached_at = await youtube_api.get_subscriptions()

    if not from_cache:
        await video_repo.upsert_many_from_dicts(videos)
        asyncio.create_task(thumb_cache.cache_thumbnails(videos))

    return _build_response("subscriptions", videos, from_cache, cached_at)
