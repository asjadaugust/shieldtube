import asyncio
from fastapi import APIRouter, Query, Request
from fastapi.responses import FileResponse, RedirectResponse, StreamingResponse
from pathlib import Path

from backend.config import settings
from backend.db.database import get_db
from backend.services.sponsorblock import get_segments
from backend.services.thumbnail_cache import ThumbnailCache

router = APIRouter()


@router.get("/video/{video_id}/stream")
async def stream_video(video_id: str, request: Request):
    """Serve video with HTTP range-request support. Supports growing files during download."""
    dm = request.app.state.download_manager
    state = await dm.get_or_start_download(video_id)

    video_path = state.file_path
    total_size = state.expected_size

    # Wait briefly for file to start being written by FFmpeg
    if not video_path.exists():
        for _ in range(50):  # 5 seconds max
            await asyncio.sleep(0.1)
            if video_path.exists():
                break
        if not video_path.exists():
            return StreamingResponse(
                iter([b""]),
                status_code=503,
                headers={"Retry-After": "5"},
            )

    range_header = request.headers.get("range")

    if range_header:
        range_spec = range_header.replace("bytes=", "")
        parts = range_spec.split("-")
        range_start = int(parts[0]) if parts[0] else 0
        range_end = int(parts[1]) if parts[1] else total_size - 1
        content_length = range_end - range_start + 1

        return StreamingResponse(
            _iter_growing_file(video_path, range_start, range_end, state),
            status_code=206,
            headers={
                "Content-Range": f"bytes {range_start}-{range_end}/{total_size}",
                "Accept-Ranges": "bytes",
                "Content-Length": str(content_length),
                "Content-Type": "video/mp4",
            },
        )

    # Non-range request
    if state.status == "cached":
        return FileResponse(
            video_path,
            media_type="video/mp4",
            headers={"Accept-Ranges": "bytes"},
        )

    # Growing file — stream all bytes with expected Content-Length
    return StreamingResponse(
        _iter_growing_file(video_path, 0, total_size - 1, state),
        status_code=200,
        headers={
            "Accept-Ranges": "bytes",
            "Content-Length": str(total_size),
            "Content-Type": "video/mp4",
        },
    )


async def _iter_growing_file(file_path: Path, start: int, end: int, state):
    """Async generator that reads from a growing file, waiting for FFmpeg writes."""
    position = start
    target = end + 1
    timeout = settings.download_wait_timeout

    while position < target:
        file_size = file_path.stat().st_size if file_path.exists() else 0

        if position < file_size:
            # Bytes available — read and yield
            readable = min(file_size - position, target - position, 65536)
            with open(file_path, "rb") as f:
                f.seek(position)
                chunk = f.read(readable)
            if chunk:
                yield chunk
                position += len(chunk)
        elif state.status == "cached":
            # Download finished — check if more bytes available
            final_size = file_path.stat().st_size if file_path.exists() else 0
            if position < final_size:
                continue
            break
        elif state.status == "error":
            break
        else:
            # Bytes not yet available — wait for FFmpeg to write more
            waited = 0.0
            while waited < timeout:
                await asyncio.sleep(0.1)
                waited += 0.1
                new_size = file_path.stat().st_size if file_path.exists() else 0
                if new_size > position or state.status in ("cached", "error"):
                    break
            # Check if we got new bytes
            if (file_path.stat().st_size if file_path.exists() else 0) <= position:
                if state.status != "cached":
                    break  # Timeout


@router.get("/sponsorblock/{video_id}")
async def get_sponsor_segments(video_id: str):
    """Return SponsorBlock skip segments for a video."""
    db = await get_db()
    segments = await get_segments(video_id, db)
    return {
        "video_id": video_id,
        "segments": segments,
    }


# Thumbnail endpoint — unchanged
@router.get("/video/{video_id}/thumbnail")
async def get_thumbnail(video_id: str, res: str = Query(default="maxres")):
    """Return cached thumbnail (200 FileResponse) or redirect to YouTube CDN (302)."""
    db = await get_db()
    cache = ThumbnailCache(db)
    local_path = await cache.get_thumbnail_path(video_id, resolution=res)
    if local_path is not None:
        return FileResponse(local_path, media_type="image/jpeg")
    youtube_url = ThumbnailCache.get_youtube_thumbnail_url(video_id, resolution=res)
    return RedirectResponse(status_code=302, url=youtube_url)
