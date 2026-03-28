"""Shorts feed endpoints."""
from fastapi import APIRouter

from backend.db.database import get_db
from backend.services.shorts_feed import get_recommended_shorts, get_trending_shorts

router = APIRouter()


@router.get("/feed/shorts/recommended")
async def shorts_recommended():
    db = await get_db()
    videos = await get_recommended_shorts(db)
    return {"feed_type": "shorts_recommended", "videos": videos, "cached_at": None, "from_cache": False}


@router.get("/feed/shorts/trending")
async def shorts_trending():
    videos = await get_trending_shorts()
    return {"feed_type": "shorts_trending", "videos": videos, "cached_at": None, "from_cache": False}
