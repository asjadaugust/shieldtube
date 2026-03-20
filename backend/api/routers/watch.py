"""Watch history and playback progress endpoints."""
from datetime import datetime, timezone

from fastapi import APIRouter, Request
from fastapi.responses import JSONResponse
from pydantic import BaseModel

from backend.db.database import get_db
from backend.db.models import WatchHistoryEntry
from backend.db.repositories import WatchHistoryRepo, VideoRepo

router = APIRouter()


class ProgressBody(BaseModel):
    position_seconds: int
    duration: int


@router.post("/video/{video_id}/progress")
async def report_progress(video_id: str, body: ProgressBody):
    """Shield app reports playback position every 10 seconds."""
    db = await get_db()
    repo = WatchHistoryRepo(db)
    entry = WatchHistoryEntry(
        video_id=video_id,
        watched_at=datetime.now(timezone.utc).isoformat(),
        position_seconds=body.position_seconds,
        duration=body.duration,
    )
    await repo.upsert(entry)
    return {"status": "ok"}


@router.get("/video/{video_id}/meta")
async def get_video_meta(video_id: str):
    """Return video metadata with last watched position for resume."""
    db = await get_db()
    video_repo = VideoRepo(db)
    watch_repo = WatchHistoryRepo(db)

    video = await video_repo.get(video_id)
    if not video:
        return JSONResponse({"error": "Video not found"}, status_code=404)

    watch = await watch_repo.get(video_id)
    last_position = watch.position_seconds if watch else 0

    return {
        "id": video.id,
        "title": video.title,
        "channel_name": video.channel_name,
        "channel_id": video.channel_id,
        "duration": video.duration,
        "cache_status": video.cache_status,
        "last_position_seconds": last_position,
    }


@router.get("/feed/history")
async def feed_history():
    """Return recently watched videos ordered by watched_at desc."""
    db = await get_db()
    watch_repo = WatchHistoryRepo(db)
    video_repo = VideoRepo(db)

    entries = await watch_repo.get_recent(limit=50)
    video_ids = [e.video_id for e in entries]
    videos = await video_repo.get_many(video_ids)

    return {
        "feed_type": "history",
        "videos": [
            {
                "id": v.id,
                "title": v.title,
                "channel_name": v.channel_name,
                "channel_id": v.channel_id,
                "view_count": v.view_count,
                "duration": v.duration,
                "published_at": v.published_at,
                "thumbnail_url": f"/api/video/{v.id}/thumbnail?res=maxres",
            }
            for v in videos
        ],
        "cached_at": None,
        "from_cache": False,
    }


@router.get("/video/{video_id}/download-status")
async def download_status(video_id: str, request: Request):
    """Report download progress for active downloads."""
    # Check active download manager (will be set on app.state in Task 4)
    dm = getattr(request.app.state, "download_manager", None)
    if dm:
        status = dm.get_download_status(video_id)
        if status:
            return status

    # Fall back to DB status
    db = await get_db()
    video_repo = VideoRepo(db)
    video = await video_repo.get(video_id)
    if not video:
        return {"status": "none", "percent": 0}

    if video.cache_status == "cached":
        return {"status": "cached", "percent": 100}
    elif video.cache_status == "error":
        return {"status": "error", "percent": 0}
    else:
        return {"status": "none", "percent": 0}
