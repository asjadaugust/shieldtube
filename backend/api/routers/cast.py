import re
from datetime import datetime, timezone
from fastapi import APIRouter
from pydantic import BaseModel

from backend.db.database import get_db

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


# ---------------------------------------------------------------------------
# Playback remote control — command queue + status
# ---------------------------------------------------------------------------

class PlaybackCommandBody(BaseModel):
    action: str  # "pause", "resume", "toggle", "seek", "speed"
    value: str | None = None


class PlaybackStatusBody(BaseModel):
    video_id: str
    title: str
    position_ms: int
    duration_ms: int
    is_playing: bool
    speed: float = 1.0


@router.post("/playback/command")
async def post_playback_command(body: PlaybackCommandBody):
    """Phone sends a playback command for the Shield to execute."""
    db = await get_db()
    await db.execute(
        "INSERT INTO playback_commands (action, value) VALUES (?, ?)",
        (body.action, body.value),
    )
    await db.commit()
    return {"status": "queued"}


@router.get("/playback/commands")
async def get_playback_commands():
    """Shield polls for pending commands, returns and deletes them atomically."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT id, action, value FROM playback_commands ORDER BY id"
    )
    rows = await cursor.fetchall()
    commands = [{"action": row["action"], "value": row["value"]} for row in rows]
    if rows:
        ids = ",".join(str(row["id"]) for row in rows)
        await db.execute(f"DELETE FROM playback_commands WHERE id IN ({ids})")
        await db.commit()
    return {"commands": commands}


@router.put("/playback/status")
async def put_playback_status(body: PlaybackStatusBody):
    """Shield reports its current playback state every second."""
    db = await get_db()
    now = datetime.now(timezone.utc).isoformat()
    await db.execute(
        """INSERT INTO playback_status (id, video_id, title, position_ms, duration_ms, is_playing, speed, updated_at)
           VALUES (1, ?, ?, ?, ?, ?, ?, ?)
           ON CONFLICT(id) DO UPDATE SET
             video_id=excluded.video_id, title=excluded.title,
             position_ms=excluded.position_ms, duration_ms=excluded.duration_ms,
             is_playing=excluded.is_playing, speed=excluded.speed,
             updated_at=excluded.updated_at""",
        (body.video_id, body.title, body.position_ms, body.duration_ms, int(body.is_playing), body.speed, now),
    )
    await db.commit()
    return {"status": "ok"}


@router.get("/playback/status")
async def get_playback_status():
    """Phone polls to see current Shield playback state."""
    db = await get_db()
    cursor = await db.execute(
        "SELECT video_id, title, position_ms, duration_ms, is_playing, speed, updated_at FROM playback_status WHERE id = 1"
    )
    row = await cursor.fetchone()
    if not row:
        return {"video_id": None}
    return {
        "video_id": row["video_id"],
        "title": row["title"],
        "position_ms": row["position_ms"],
        "duration_ms": row["duration_ms"],
        "is_playing": bool(row["is_playing"]),
        "speed": row["speed"],
        "updated_at": row["updated_at"],
    }


@router.delete("/playback/status")
async def clear_playback_status():
    """Clear playback status when Shield stops playing."""
    db = await get_db()
    await db.execute("DELETE FROM playback_status WHERE id = 1")
    await db.commit()
    return {"status": "cleared"}
