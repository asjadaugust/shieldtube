from fastapi import APIRouter, Depends, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pathlib import Path

from backend.config import settings
from backend.db.database import get_db
from backend.services.stream_resolver import resolve_stream
from backend.services.muxer import mux_streams
from backend.services.thumbnail_cache import ThumbnailCache

router = APIRouter()


async def get_or_create_stream(video_id: str) -> Path:
    """Resolve, mux, and cache a video. Return path to cached MP4."""
    cache_path = Path(settings.cache_dir) / "videos" / f"{video_id}.mp4"

    if cache_path.exists():
        return cache_path

    stream_info = resolve_stream(video_id)
    mux_streams(
        video_url=stream_info["video_url"],
        audio_url=stream_info["audio_url"],
        output_path=cache_path,
    )
    return cache_path


@router.get("/video/{video_id}/stream")
async def stream_video(video_id: str, request: Request):
    """Serve video with HTTP range-request support."""
    video_path = await get_or_create_stream(video_id)
    file_size = video_path.stat().st_size

    range_header = request.headers.get("range")

    if range_header:
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")
        range_start = int(parts[0]) if parts[0] else 0
        range_end = int(parts[1]) if parts[1] else file_size - 1

        content_length = range_end - range_start + 1

        def iter_range():
            with open(video_path, "rb") as f:
                f.seek(range_start)
                remaining = content_length
                while remaining > 0:
                    chunk = f.read(min(8192, remaining))
                    if not chunk:
                        break
                    remaining -= len(chunk)
                    yield chunk

        return StreamingResponse(
            iter_range(),
            status_code=206,
            headers={
                "Content-Range": f"bytes {range_start}-{range_end}/{file_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": "video/mp4",
            },
        )

    return FileResponse(
        video_path,
        media_type="video/mp4",
        headers={"Accept-Ranges": "bytes"},
    )


@router.get("/video/{video_id}/thumbnail")
async def get_thumbnail(
    video_id: str,
    res: str = Query(default="maxres"),
):
    """Return cached thumbnail (200 FileResponse) or redirect to YouTube CDN (302)."""
    db = await get_db()
    cache = ThumbnailCache(db)
    local_path = await cache.get_thumbnail_path(video_id, resolution=res)

    if local_path is not None:
        return FileResponse(local_path, media_type="image/jpeg")

    youtube_url = ThumbnailCache.get_youtube_thumbnail_url(video_id, resolution=res)
    return RedirectResponse(status_code=302, url=youtube_url)
