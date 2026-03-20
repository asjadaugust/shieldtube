import os
from pathlib import Path
from fastapi import APIRouter
from fastapi.responses import JSONResponse

from backend.config import settings
from backend.db.database import get_db
from backend.db.repositories import VideoRepo

router = APIRouter()


def _format_size(size_bytes: int) -> str:
    if size_bytes >= 1_073_741_824:
        return f"{size_bytes / 1_073_741_824:.1f} GB"
    elif size_bytes >= 1_048_576:
        return f"{size_bytes / 1_048_576:.1f} MB"
    elif size_bytes >= 1024:
        return f"{size_bytes / 1024:.1f} KB"
    return f"{size_bytes} B"


@router.get("/cache/status")
async def cache_status():
    """Return cache disk usage and per-video breakdown."""
    cache_dir = Path(settings.cache_dir) / "videos"
    if not cache_dir.exists():
        return {"total_size_bytes": 0, "total_size_human": "0 B", "video_count": 0, "videos": []}

    db = await get_db()
    repo = VideoRepo(db)

    video_files = []
    total_size = 0

    for f in cache_dir.glob("*.mp4"):
        video_id = f.stem
        file_size = f.stat().st_size
        total_size += file_size

        video = await repo.get(video_id)
        video_files.append({
            "id": video_id,
            "title": video.title if video else "Unknown",
            "file_size_bytes": file_size,
            "file_size_human": _format_size(file_size),
            "cache_status": video.cache_status if video else "unknown",
            "last_accessed": video.last_accessed if video else None,
        })

    # Sort by last_accessed descending (None last)
    video_files.sort(key=lambda v: v["last_accessed"] or "", reverse=True)

    return {
        "total_size_bytes": total_size,
        "total_size_human": _format_size(total_size),
        "video_count": len(video_files),
        "videos": video_files,
    }


@router.delete("/cache/{video_id}")
async def evict_cache(video_id: str):
    """Delete a cached video from disk and reset DB status."""
    cache_path = Path(settings.cache_dir) / "videos" / f"{video_id}.mp4"

    if not cache_path.exists():
        return JSONResponse({"error": "Video not cached"}, status_code=404)

    cache_path.unlink()

    db = await get_db()
    await db.execute(
        "UPDATE videos SET cache_status = 'none', cached_video_path = NULL WHERE id = ?",
        (video_id,),
    )
    await db.commit()

    return {"status": "deleted", "video_id": video_id}
