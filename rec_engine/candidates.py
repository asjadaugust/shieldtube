"""Fetch candidate videos for recommendation scoring."""
import asyncio
import logging
import subprocess
import json

logger = logging.getLogger(__name__)


class CandidateFetcher:
    """Fetches candidate videos from subscriptions and yt-dlp related videos."""

    async def fetch(
        self, history: list[dict], subscriptions: list[dict], max_related: int = 10
    ) -> list[dict]:
        # Start with subscription videos as candidates
        candidates = {v["id"]: v for v in subscriptions}

        # Get related videos for top watched videos via yt-dlp
        watched_ids = [v["id"] for v in history[:max_related]]
        related = await self._fetch_related_batch(watched_ids)
        for v in related:
            if v["id"] not in candidates:
                candidates[v["id"]] = v

        # Exclude already-watched videos
        watched_set = {v["id"] for v in history}
        return [v for vid, v in candidates.items() if vid not in watched_set]

    async def _fetch_related_batch(self, video_ids: list[str]) -> list[dict]:
        results = []
        for vid in video_ids:
            try:
                related = await asyncio.to_thread(self._fetch_related_sync, vid)
                results.extend(related)
            except Exception as e:
                logger.warning(f"Failed to fetch related for {vid}: {e}")
        return results

    @staticmethod
    def _fetch_related_sync(video_id: str) -> list[dict]:
        cmd = [
            "yt-dlp", "--flat-playlist", "--dump-json",
            f"https://www.youtube.com/watch?v={video_id}",
            "--playlist-items", "1:10",
        ]
        try:
            result = subprocess.run(
                cmd, capture_output=True, text=True, timeout=30
            )
            videos = []
            for line in result.stdout.strip().split("\n"):
                if not line:
                    continue
                data = json.loads(line)
                videos.append({
                    "id": data.get("id", ""),
                    "title": data.get("title", ""),
                    "channel_name": data.get("channel", data.get("uploader", "")),
                    "channel_id": data.get("channel_id", ""),
                    "view_count": data.get("view_count"),
                    "duration": data.get("duration"),
                    "published_at": data.get("upload_date"),
                    "description": (data.get("description") or "")[:200],
                })
            return videos
        except (subprocess.TimeoutExpired, json.JSONDecodeError):
            return []
