"""Video rating endpoints for recommendation training."""
from fastapi import APIRouter
from pydantic import BaseModel

from backend.db.database import get_db
from backend.db.repositories import VideoRatingRepo

router = APIRouter()


class RateBody(BaseModel):
    rating: str  # "interested", "not_interested", "love"


@router.post("/video/{video_id}/rate")
async def rate_video(video_id: str, body: RateBody):
    if body.rating not in ("interested", "not_interested", "love"):
        return {"error": "Invalid rating. Use: interested, not_interested, love"}
    db = await get_db()
    repo = VideoRatingRepo(db)
    await repo.upsert(video_id, body.rating)
    return {"status": "ok", "video_id": video_id, "rating": body.rating}


@router.get("/video/{video_id}/rating")
async def get_rating(video_id: str):
    db = await get_db()
    repo = VideoRatingRepo(db)
    rating = await repo.get(video_id)
    return {"video_id": video_id, "rating": rating}


@router.get("/ratings/recent")
async def get_recent_ratings():
    db = await get_db()
    repo = VideoRatingRepo(db)
    ratings = await repo.get_recent(limit=50)
    return {"ratings": ratings}
