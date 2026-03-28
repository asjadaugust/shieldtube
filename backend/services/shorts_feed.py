"""Shorts feed — yt-dlp scraping for recommended channel Shorts and trending Shorts."""
from __future__ import annotations

import asyncio
import logging
import time

import aiosqlite
import yt_dlp

from backend.config import settings

logger = logging.getLogger(__name__)

# Module-level in-memory cache: {key: (fetched_at_monotonic, results)}
_CACHE: dict[str, tuple[float, list[dict]]] = {}
_CACHE_TTL = 3600  # 1 hour


def _ydl_opts(playlist_end: int = 5) -> dict:
    opts: dict = {
        "quiet": True,
        "no_warnings": True,
        "extract_flat": "in_playlist",
        "playlistend": playlist_end,
    }
    if settings.ytdlp_cookies_path:
        opts["cookiefile"] = settings.ytdlp_cookies_path
    if settings.ytdlp_proxy:
        opts["proxy"] = settings.ytdlp_proxy
    return opts


def _normalize_date(upload_date: str | None) -> str | None:
    """Convert YYYYMMDD → ISO 8601, or return None."""
    if not upload_date or len(upload_date) != 8:
        return None
    try:
        return f"{upload_date[:4]}-{upload_date[4:6]}-{upload_date[6:8]}T00:00:00Z"
    except Exception:
        return None


def _scrape_channel_shorts(channel_id: str, limit: int = 5) -> list[dict]:
    """Scrape the Shorts tab of a channel. Synchronous — run via asyncio.to_thread."""
    url = f"https://www.youtube.com/channel/{channel_id}/shorts"
    with yt_dlp.YoutubeDL(_ydl_opts(limit)) as ydl:
        info = ydl.extract_info(url, download=False)
    if info is None:
        return []
    entries = info.get("entries") or []
    channel_name = info.get("channel") or info.get("uploader") or ""
    results = []
    for e in entries:
        if e is None:
            continue
        vid_id = e.get("id") or ""
        if not vid_id:
            continue
        results.append({
            "id": vid_id,
            "title": e.get("title") or "",
            "channel_name": e.get("channel") or e.get("uploader") or channel_name,
            "channel_id": channel_id,
            "duration": e.get("duration"),
            "published_at": _normalize_date(e.get("upload_date")),
            "thumbnail_url": f"/api/video/{vid_id}/thumbnail?res=maxres",
        })
    return results


def _scrape_trending_shorts(limit: int = 20) -> list[dict]:
    """Scrape YouTube's Shorts discovery feed. Synchronous — run via asyncio.to_thread."""
    url = "https://www.youtube.com/shorts"
    with yt_dlp.YoutubeDL(_ydl_opts(limit)) as ydl:
        info = ydl.extract_info(url, download=False)
    if info is None:
        return []
    entries = info.get("entries") or []
    results = []
    for e in entries:
        if e is None:
            continue
        vid_id = e.get("id") or ""
        if not vid_id:
            continue
        results.append({
            "id": vid_id,
            "title": e.get("title") or "",
            "channel_name": e.get("channel") or e.get("uploader") or "",
            "channel_id": e.get("channel_id") or "",
            "duration": e.get("duration"),
            "published_at": _normalize_date(e.get("upload_date")),
            "thumbnail_url": f"/api/video/{vid_id}/thumbnail?res=maxres",
        })
    return results


async def get_recommended_shorts(
    db: aiosqlite.Connection,
    max_channels: int = 10,
    shorts_per_channel: int = 5,
) -> list[dict]:
    """Return Shorts from the top affinity channels in watch history."""
    cache_key = "recommended"
    cached = _CACHE.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL:
        return cached[1]

    cursor = await db.execute(
        """SELECT v.channel_id, v.channel_name, COUNT(*) as watch_count
           FROM watch_history wh
           JOIN videos v ON v.id = wh.video_id
           WHERE v.channel_id IS NOT NULL AND v.channel_id != ''
           GROUP BY v.channel_id
           ORDER BY watch_count DESC
           LIMIT ?""",
        (max_channels,),
    )
    rows = await cursor.fetchall()
    if not rows:
        return []

    all_shorts: list[dict] = []
    for row in rows:
        try:
            shorts = await asyncio.to_thread(
                _scrape_channel_shorts, row["channel_id"], shorts_per_channel
            )
            all_shorts.extend(shorts)
        except Exception as exc:
            logger.warning("Failed to scrape Shorts for channel %s: %s", row["channel_id"], exc)

    all_shorts.sort(key=lambda v: v.get("published_at") or "", reverse=True)

    _CACHE[cache_key] = (time.monotonic(), all_shorts)
    return all_shorts


async def get_trending_shorts(limit: int = 20) -> list[dict]:
    """Return Shorts from YouTube's Shorts discovery feed."""
    cache_key = "trending"
    cached = _CACHE.get(cache_key)
    if cached and (time.monotonic() - cached[0]) < _CACHE_TTL:
        return cached[1]

    try:
        shorts = await asyncio.to_thread(_scrape_trending_shorts, limit)
    except Exception as exc:
        logger.warning("Failed to scrape trending Shorts: %s", exc)
        return []

    _CACHE[cache_key] = (time.monotonic(), shorts)
    return shorts
