"""YouTubeAPI — wraps YouTube Data API v3 with ETag caching and auth."""

import json
import re
from datetime import datetime, timedelta, timezone
from urllib.parse import urlencode

import aiosqlite
import httpx

from backend.services.auth_manager import AuthManager
from backend.services.retry import with_retry

_YT_API_BASE = "https://www.googleapis.com/youtube/v3"


class YouTubeAPI:
    """Thin async client for YouTube Data API v3.

    All HTTP calls are authenticated via AuthManager.
    feed_cache table is used for ETag-based conditional requests.
    """

    def __init__(self, auth_manager: AuthManager, db: aiosqlite.Connection) -> None:
        self._auth = auth_manager
        self._db = db

    # ------------------------------------------------------------------
    # Public API
    # ------------------------------------------------------------------

    async def get_home_feed(
        self, max_results: int = 20
    ) -> tuple[list[dict], bool, str | None]:
        """Fetch the most-popular videos feed.

        Returns:
            (videos, from_cache, cached_at)
            - from_cache=True when the server returned 304 Not Modified.
            - cached_at is the ISO timestamp of the last fetch (304 path only).
        """
        headers = await self._auth.get_auth_headers()

        # Check DB for cached ETag
        etag_row = await (
            await self._db.execute(
                "SELECT etag, video_ids_json, fetched_at FROM feed_cache WHERE feed_type = ?",
                ("home",),
            )
        ).fetchone()

        if etag_row and etag_row["etag"]:
            headers["If-None-Match"] = etag_row["etag"]

        url = (
            f"{_YT_API_BASE}/videos?"
            + urlencode(
                {
                    "part": "snippet,contentDetails,statistics",
                    "chart": "mostPopular",
                    "regionCode": "US",
                    "maxResults": max_results,
                }
            )
        )

        async with httpx.AsyncClient() as client:
            async def _do_request():
                return await client.get(url, headers=headers)
            response = await with_retry(_do_request, description="YouTube API get_home_feed")

        if response.status_code == 304 and etag_row:
            # Cache hit — load video IDs from feed_cache, then fetch rows from videos table
            video_ids: list[str] = json.loads(etag_row["video_ids_json"])
            videos = await self._load_cached_videos(video_ids)
            return videos, True, etag_row["fetched_at"]

        # 200 — parse and store
        response.raise_for_status()
        data = response.json()
        videos = self._parse_video_items(data.get("items", []))
        new_etag = data.get("etag") or response.headers.get("ETag", "")
        fetched_at = datetime.now(timezone.utc).isoformat()
        video_ids = [v["id"] for v in videos]

        await self._db.execute(
            "INSERT OR REPLACE INTO feed_cache (feed_type, video_ids_json, etag, fetched_at)"
            " VALUES (?, ?, ?, ?)",
            ("home", json.dumps(video_ids), new_etag, fetched_at),
        )
        await self._db.commit()

        return videos, False, None

    async def get_subscriptions(
        self, max_results: int = 20
    ) -> tuple[list[dict], bool, str | None]:
        """Fetch recent uploads from the authenticated user's subscriptions.

        Returns:
            (videos, False, None)  — subscriptions don't use ETag caching.
        """
        headers = await self._auth.get_auth_headers()
        async with httpx.AsyncClient() as client:
            async def _do_subs_request():
                return await client.get(
                    f"{_YT_API_BASE}/subscriptions?"
                    + urlencode(
                        {"part": "snippet", "mine": "true", "maxResults": 50}
                    ),
                    headers=headers,
                )
            subs_resp = await with_retry(_do_subs_request, description="YouTube API get_subscriptions")
            subs_resp.raise_for_status()
            subs_data = subs_resp.json()

        channel_ids = [
            item["snippet"]["resourceId"]["channelId"]
            for item in subs_data.get("items", [])
            if item.get("snippet", {}).get("resourceId", {}).get("kind") == "youtube#channel"
        ]

        published_after = (
            datetime.now(timezone.utc) - timedelta(hours=24)
        ).strftime("%Y-%m-%dT%H:%M:%SZ")

        video_ids: list[str] = []
        async with httpx.AsyncClient() as client:
            for channel_id in channel_ids:
                act_resp = await client.get(
                    f"{_YT_API_BASE}/activities?"
                    + urlencode(
                        {
                            "part": "snippet,contentDetails",
                            "channelId": channel_id,
                            "publishedAfter": published_after,
                            "maxResults": 5,
                        }
                    ),
                    headers=headers,
                )
                if act_resp.status_code != 200:
                    continue
                for item in act_resp.json().get("items", []):
                    vid_id = (
                        item.get("contentDetails", {})
                        .get("upload", {})
                        .get("videoId")
                    )
                    if vid_id:
                        video_ids.append(vid_id)

        videos = await self.get_video_details(video_ids[:max_results]) if video_ids else []
        return videos, False, None

    async def search(
        self, query: str, max_results: int = 20
    ) -> list[dict]:
        """Search YouTube and return enriched video dicts."""
        headers = await self._auth.get_auth_headers()
        async with httpx.AsyncClient() as client:
            async def _do_search_request():
                return await client.get(
                    f"{_YT_API_BASE}/search?"
                    + urlencode(
                        {
                            "part": "snippet",
                            "q": query,
                            "type": "video",
                            "maxResults": max_results,
                        }
                    ),
                    headers=headers,
                )
            resp = await with_retry(_do_search_request, description="YouTube API search")
            resp.raise_for_status()

        items = resp.json().get("items", [])
        if not items:
            return []

        video_ids = [
            item["id"]["videoId"]
            for item in items
            if item.get("id", {}).get("videoId")
        ]
        if not video_ids:
            return []

        return await self.get_video_details(video_ids)

    async def get_watch_later(
        self, max_results: int = 50
    ) -> tuple[list[dict], bool, str | None]:
        """Fetch the user's Watch Later playlist.

        Returns:
            (videos, from_cache, cached_at)
            - from_cache=True when the server returned 304 Not Modified.
            - cached_at is the ISO timestamp of the last fetch (304 path only).
        """
        feed_type = "watch_later"

        etag_row = await (
            await self._db.execute(
                "SELECT etag, video_ids_json, fetched_at FROM feed_cache WHERE feed_type = ?",
                (feed_type,),
            )
        ).fetchone()

        headers = await self._auth.get_auth_headers()
        if etag_row and etag_row["etag"]:
            headers["If-None-Match"] = etag_row["etag"]

        async with httpx.AsyncClient() as client:
            async def _do_wl_request():
                return await client.get(
                    f"{_YT_API_BASE}/playlistItems",
                    headers=headers,
                    params={
                        "part": "snippet,contentDetails",
                        "playlistId": "WL",
                        "maxResults": max_results,
                    },
                )
            resp = await with_retry(_do_wl_request, description="YouTube API get_watch_later")

        if resp.status_code == 304 and etag_row:
            video_ids: list[str] = json.loads(etag_row["video_ids_json"])
            videos = await self._load_cached_videos(video_ids)
            return videos, True, etag_row["fetched_at"]

        resp.raise_for_status()
        data = resp.json()

        video_ids = [
            item["contentDetails"]["videoId"]
            for item in data.get("items", [])
            if "contentDetails" in item and "videoId" in item["contentDetails"]
        ]

        videos = await self.get_video_details(video_ids) if video_ids else []

        new_etag = data.get("etag") or resp.headers.get("ETag", "")
        fetched_at = datetime.now(timezone.utc).isoformat()

        await self._db.execute(
            "INSERT OR REPLACE INTO feed_cache (feed_type, video_ids_json, etag, fetched_at)"
            " VALUES (?, ?, ?, ?)",
            (feed_type, json.dumps(video_ids), new_etag, fetched_at),
        )
        await self._db.commit()

        return videos, False, None

    async def get_video_details(self, video_ids: list[str]) -> list[dict]:
        """Fetch full metadata for a list of video IDs.

        Returns a list of dicts with keys:
            id, title, channel_name, channel_id, view_count, duration,
            published_at, description
        """
        if not video_ids:
            return []

        headers = await self._auth.get_auth_headers()
        ids_param = ",".join(video_ids)
        async with httpx.AsyncClient() as client:
            async def _do_details_request():
                return await client.get(
                    f"{_YT_API_BASE}/videos?"
                    + urlencode(
                        {
                            "part": "snippet,contentDetails,statistics",
                            "id": ids_param,
                        }
                    ),
                    headers=headers,
                )
            resp = await with_retry(_do_details_request, description="YouTube API get_video_details")
            resp.raise_for_status()

        return self._parse_video_items(resp.json().get("items", []))

    # ------------------------------------------------------------------
    # Helpers
    # ------------------------------------------------------------------

    def _parse_video_items(self, items: list[dict]) -> list[dict]:
        """Convert raw YouTube API items into normalised dicts."""
        videos = []
        for item in items:
            snippet = item.get("snippet", {})
            content = item.get("contentDetails", {})
            stats = item.get("statistics", {})
            view_count_str = stats.get("viewCount")
            view_count = int(view_count_str) if view_count_str else None
            duration_str = content.get("duration", "PT0S")
            videos.append(
                {
                    "id": item["id"],
                    "title": snippet.get("title", ""),
                    "channel_name": snippet.get("channelTitle", ""),
                    "channel_id": snippet.get("channelId", ""),
                    "view_count": view_count,
                    "duration": self._parse_duration(duration_str),
                    "published_at": snippet.get("publishedAt"),
                    "description": snippet.get("description", ""),
                }
            )
        return videos

    def _parse_duration(self, iso_duration: str) -> int:
        """Parse ISO 8601 duration string (PT__H__M__S) into total seconds.

        Examples:
            PT4M33S  → 273
            PT1H2M3S → 3723
            PT30S    → 30
            PT1H     → 3600
        """
        pattern = re.compile(
            r"PT(?:(\d+)H)?(?:(\d+)M)?(?:(\d+)S)?", re.IGNORECASE
        )
        match = pattern.fullmatch(iso_duration.strip())
        if not match:
            return 0
        hours = int(match.group(1) or 0)
        minutes = int(match.group(2) or 0)
        seconds = int(match.group(3) or 0)
        return hours * 3600 + minutes * 60 + seconds

    async def _load_cached_videos(self, video_ids: list[str]) -> list[dict]:
        """Load video rows from the local videos table by ID list."""
        if not video_ids:
            return []
        placeholders = ",".join("?" * len(video_ids))
        rows = await (
            await self._db.execute(
                f"SELECT * FROM videos WHERE id IN ({placeholders})", video_ids
            )
        ).fetchall()
        # Convert aiosqlite.Row objects to plain dicts
        result = []
        for row in rows:
            result.append(dict(row))
        return result
