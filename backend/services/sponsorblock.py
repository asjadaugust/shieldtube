import json

import aiosqlite
import httpx

SPONSORBLOCK_API = "https://sponsor.ajay.app/api/skipSegments"
CATEGORIES = '["sponsor","intro","outro"]'


async def get_segments(video_id: str, db: aiosqlite.Connection) -> list[dict]:
    """Fetch sponsor skip segments, with SQLite caching."""
    # Check cache first
    async with db.execute(
        "SELECT sponsor_segments_json FROM videos WHERE id = ?", (video_id,)
    ) as cursor:
        row = await cursor.fetchone()

    if row and row[0] is not None:
        return json.loads(row[0])

    # Fetch from SponsorBlock API
    segments = await _fetch_from_api(video_id)

    # Cache result (even empty lists)
    await db.execute(
        "UPDATE videos SET sponsor_segments_json = ? WHERE id = ?",
        (json.dumps(segments), video_id),
    )
    await db.commit()

    return segments


async def _fetch_from_api(video_id: str) -> list[dict]:
    """Call SponsorBlock API with 3-second timeout."""
    try:
        async with httpx.AsyncClient(timeout=3.0) as client:
            resp = await client.get(
                SPONSORBLOCK_API,
                params={"videoID": video_id, "categories": CATEGORIES},
            )
            if resp.status_code == 404:
                return []  # No segments for this video
            resp.raise_for_status()

            data = resp.json()
            return [
                {
                    "start": seg["segment"][0],
                    "end": seg["segment"][1],
                    "category": seg["category"],
                }
                for seg in data
            ]
    except (httpx.TimeoutException, httpx.HTTPStatusError, Exception):
        return []  # Graceful degradation
