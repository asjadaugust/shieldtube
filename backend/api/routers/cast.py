import re
from fastapi import APIRouter
from pydantic import BaseModel

router = APIRouter()

# Simple in-memory state — single user, single video
_now_playing: dict | None = None


class CastRequest(BaseModel):
    url: str | None = None
    video_id: str | None = None


def _extract_video_id(url: str) -> str | None:
    """Extract YouTube video ID from various URL formats."""
    patterns = [
        r'(?:youtube\.com/watch\?v=|youtu\.be/|youtube\.com/embed/)([a-zA-Z0-9_-]{11})',
        r'^([a-zA-Z0-9_-]{11})$',
    ]
    for pattern in patterns:
        match = re.search(pattern, url)
        if match:
            return match.group(1)
    return None


@router.post("/cast")
async def cast_video(body: CastRequest):
    """Queue a video for playback on Shield TV."""
    global _now_playing

    video_id = body.video_id
    if not video_id and body.url:
        video_id = _extract_video_id(body.url)

    if not video_id:
        from fastapi.responses import JSONResponse
        return JSONResponse({"error": "Could not extract video ID"}, status_code=400)

    _now_playing = {"video_id": video_id}
    return {"status": "queued", "video_id": video_id}


@router.get("/cast/now-playing")
async def now_playing():
    """Check if there's a video queued for playback."""
    global _now_playing
    if _now_playing:
        result = _now_playing
        _now_playing = None  # Clear after reading (single-use)
        return result
    return {"video_id": None}
