import re

import httpx
from pathlib import Path

from backend.config import settings

# Strip WebVTT position/alignment cues so subtitles render centered
_POSITION_RE = re.compile(r"\s*(align:\S+|position:\S+|line:\S+|size:\S+)")


def _strip_positioning(vtt_text: str) -> str:
    """Remove align/position/line/size cues from WebVTT timestamp lines."""
    lines = []
    for line in vtt_text.splitlines():
        if "-->" in line:
            line = _POSITION_RE.sub("", line).rstrip()
        lines.append(line)
    return "\n".join(lines)


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
            vtt_text = resp.text
            vtt_text = _strip_positioning(vtt_text)
            cache_path.write_text(vtt_text, encoding="utf-8")
        return cache_path
    except Exception:
        return None
