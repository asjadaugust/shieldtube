import httpx
from pathlib import Path

from backend.config import settings


async def get_or_download_subtitle(video_id: str, lang: str, url: str) -> Path | None:
    """Download and cache a subtitle file. Returns local path, or None on failure."""
    cache_path = Path(settings.cache_dir) / "subtitles" / f"{video_id}_{lang}.vtt"
    if cache_path.exists():
        return cache_path

    try:
        cache_path.parent.mkdir(parents=True, exist_ok=True)
        async with httpx.AsyncClient(timeout=10.0) as client:
            resp = await client.get(url)
            resp.raise_for_status()
            cache_path.write_bytes(resp.content)
        return cache_path
    except Exception:
        return None
