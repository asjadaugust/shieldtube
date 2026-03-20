import asyncio
import hashlib
from datetime import datetime, UTC
from pathlib import Path

import aiosqlite
import httpx

from backend.config import settings


class ThumbnailCache:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def cache_thumbnails(self, videos: list[dict]) -> None:
        """Download and cache thumbnails for a list of video dicts (with at least an 'id' key)."""
        if not videos:
            return

        video_ids = [v["id"] for v in videos]

        # Find which video IDs already have cached thumbnails
        placeholders = ",".join("?" * len(video_ids))
        async with self._db.execute(
            f"SELECT video_id FROM thumbnails WHERE video_id IN ({placeholders}) AND resolution = 'maxres'",
            video_ids,
        ) as cursor:
            cached_rows = await cursor.fetchall()
        cached_ids = {row[0] for row in cached_rows}

        uncached = [v for v in videos if v["id"] not in cached_ids]
        if not uncached:
            return

        # Prepare thumbnail directory
        thumb_dir = Path(settings.cache_dir) / "thumbnails"
        thumb_dir.mkdir(parents=True, exist_ok=True)

        semaphore = asyncio.Semaphore(settings.thumbnail_concurrency)

        async with httpx.AsyncClient() as client:
            tasks = [
                self._download_and_store(client, semaphore, v, thumb_dir)
                for v in uncached
            ]
            await asyncio.gather(*tasks)

    async def _download_and_store(
        self,
        client: httpx.AsyncClient,
        semaphore: asyncio.Semaphore,
        video: dict,
        thumb_dir: Path,
    ) -> None:
        video_id = video["id"]
        async with semaphore:
            # Try maxres first
            maxres_url = f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
            response = await client.get(maxres_url)

            if response.status_code == 404:
                # Fall back to hqdefault
                hq_url = f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
                response = await client.get(hq_url)

            if response.status_code not in (200, 201):
                raise httpx.HTTPStatusError(
                    f"HTTP {response.status_code}",
                    request=None,  # type: ignore[arg-type]
                    response=response,
                )
            content = response.content

        local_path = str(thumb_dir / f"{video_id}_maxres.jpg")
        Path(local_path).write_bytes(content)

        content_hash = hashlib.md5(content).hexdigest()
        fetched_at = datetime.now(UTC).isoformat()

        await self._db.execute(
            "INSERT OR REPLACE INTO thumbnails (video_id, resolution, local_path, fetched_at, content_hash) "
            "VALUES (?, ?, ?, ?, ?)",
            (video_id, "maxres", local_path, fetched_at, content_hash),
        )
        await self._db.execute(
            "UPDATE videos SET thumbnail_path = ? WHERE id = ?",
            (local_path, video_id),
        )
        await self._db.commit()

    async def get_thumbnail_path(self, video_id: str, resolution: str = "maxres") -> str | None:
        """Return the local path if cached and the file exists on disk, else None."""
        async with self._db.execute(
            "SELECT local_path FROM thumbnails WHERE video_id = ? AND resolution = ?",
            (video_id, resolution),
        ) as cursor:
            row = await cursor.fetchone()

        if row is None:
            return None

        local_path = row[0]
        if not Path(local_path).exists():
            return None

        return local_path

    @staticmethod
    def get_youtube_thumbnail_url(video_id: str, resolution: str = "maxres") -> str:
        """Return the YouTube CDN URL for a thumbnail."""
        if resolution == "high":
            return f"https://i.ytimg.com/vi/{video_id}/hqdefault.jpg"
        return f"https://i.ytimg.com/vi/{video_id}/maxresdefault.jpg"
