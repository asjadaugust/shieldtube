"""Async repository classes for all database tables."""
from __future__ import annotations

import aiosqlite

from backend.db.models import Video, FeedCache, Thumbnail, AuthToken, WatchHistoryEntry, RecommendationRun, Recommendation, WatchSignal, VideoRating
from backend.services.token_crypto import encrypt_token, decrypt_token


def _row_to_video(row: aiosqlite.Row) -> Video:
    return Video(
        id=row["id"],
        title=row["title"],
        channel_name=row["channel_name"],
        channel_id=row["channel_id"],
        view_count=row["view_count"],
        duration=row["duration"],
        published_at=row["published_at"],
        description=row["description"],
        thumbnail_path=row["thumbnail_path"],
        cached_video_path=row["cached_video_path"],
        cache_status=row["cache_status"],
        last_accessed=row["last_accessed"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
        cached_at=row["cached_at"] if "cached_at" in row.keys() else None,
        download_source=row["download_source"] if "download_source" in row.keys() else None,
        chapters_json=row["chapters_json"] if "chapters_json" in row.keys() else None,
    )


def _row_to_feed_cache(row: aiosqlite.Row) -> FeedCache:
    return FeedCache(
        feed_type=row["feed_type"],
        video_ids_json=row["video_ids_json"],
        fetched_at=row["fetched_at"],
        etag=row["etag"],
    )


def _row_to_thumbnail(row: aiosqlite.Row) -> Thumbnail:
    return Thumbnail(
        video_id=row["video_id"],
        resolution=row["resolution"],
        local_path=row["local_path"],
        fetched_at=row["fetched_at"],
        content_hash=row["content_hash"],
    )


def _row_to_auth_token(row: aiosqlite.Row) -> AuthToken:
    return AuthToken(
        id=row["id"],
        access_token=decrypt_token(row["access_token"]),
        refresh_token=decrypt_token(row["refresh_token"]) if row["refresh_token"] else None,
        token_type=row["token_type"],
        expires_at=row["expires_at"],
        scopes=row["scopes"],
        created_at=row["created_at"],
        updated_at=row["updated_at"],
    )


class VideoRepo:
    """Repository for the `videos` table."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert(self, video: Video) -> None:
        """Insert or replace a single video record."""
        await self._db.execute(
            """
            INSERT OR REPLACE INTO videos (
                id, title, channel_name, channel_id, view_count, duration,
                published_at, description, thumbnail_path, cached_video_path,
                cache_status, last_accessed, created_at, updated_at
            ) VALUES (
                :id, :title, :channel_name, :channel_id, :view_count, :duration,
                :published_at, :description, :thumbnail_path, :cached_video_path,
                :cache_status, :last_accessed,
                COALESCE(:created_at, CURRENT_TIMESTAMP),
                CURRENT_TIMESTAMP
            )
            """,
            {
                "id": video.id,
                "title": video.title,
                "channel_name": video.channel_name,
                "channel_id": video.channel_id,
                "view_count": video.view_count,
                "duration": video.duration,
                "published_at": video.published_at,
                "description": video.description,
                "thumbnail_path": video.thumbnail_path,
                "cached_video_path": video.cached_video_path,
                "cache_status": video.cache_status,
                "last_accessed": video.last_accessed,
                "created_at": video.created_at,
            },
        )
        await self._db.commit()

    async def upsert_many(self, videos: list[Video]) -> None:
        """Batch upsert a list of Video objects.

        Uses a write lock to prevent 'cannot start a transaction within a
        transaction' errors when the feed refresher and API handlers run
        concurrently on the shared DB connection.
        """
        if not videos:
            return
        from backend.db.database import get_db_write_lock
        async with get_db_write_lock():
            try:
                for video in videos:
                    await self._db.execute(
                        """
                        INSERT OR REPLACE INTO videos (
                            id, title, channel_name, channel_id, view_count, duration,
                            published_at, description, thumbnail_path, cached_video_path,
                            cache_status, last_accessed, created_at, updated_at
                        ) VALUES (
                            :id, :title, :channel_name, :channel_id, :view_count, :duration,
                            :published_at, :description, :thumbnail_path, :cached_video_path,
                            :cache_status, :last_accessed,
                            COALESCE(:created_at, CURRENT_TIMESTAMP),
                            CURRENT_TIMESTAMP
                        )
                        """,
                        {
                            "id": video.id,
                            "title": video.title,
                            "channel_name": video.channel_name,
                            "channel_id": video.channel_id,
                            "view_count": video.view_count,
                            "duration": video.duration,
                            "published_at": video.published_at,
                            "description": video.description,
                            "thumbnail_path": video.thumbnail_path,
                            "cached_video_path": video.cached_video_path,
                            "cache_status": video.cache_status,
                            "last_accessed": video.last_accessed,
                            "created_at": video.created_at,
                        },
                    )
                await self._db.commit()
            except Exception:
                await self._db.rollback()
                raise

    async def upsert_many_from_dicts(self, videos: list[dict]) -> None:
        """Convert dicts to Video objects and batch upsert.

        Dict keys match Video fields: id, title, channel_name, channel_id,
        view_count, duration, published_at, description (all others optional).
        """
        video_objects = [
            Video(
                id=v["id"],
                title=v["title"],
                channel_name=v["channel_name"],
                channel_id=v["channel_id"],
                view_count=v.get("view_count"),
                duration=v.get("duration"),
                published_at=v.get("published_at"),
                description=v.get("description"),
            )
            for v in videos
        ]
        await self.upsert_many(video_objects)

    async def get(self, video_id: str) -> Video | None:
        """Fetch a single video by ID, or None if not found."""
        async with self._db.execute(
            "SELECT * FROM videos WHERE id = ?", (video_id,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_video(row)

    async def get_many(self, video_ids: list[str]) -> list[Video]:
        """Fetch multiple videos, preserving the order of the input IDs.

        IDs that do not exist in the database are silently omitted.
        """
        if not video_ids:
            return []

        placeholders = ", ".join("?" * len(video_ids))
        async with self._db.execute(
            f"SELECT * FROM videos WHERE id IN ({placeholders})", video_ids
        ) as cursor:
            rows = await cursor.fetchall()

        by_id = {row["id"]: _row_to_video(row) for row in rows}
        return [by_id[vid] for vid in video_ids if vid in by_id]


class FeedCacheRepo:
    """Repository for the `feed_cache` table."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get(self, feed_type: str) -> FeedCache | None:
        """Fetch the cached feed entry, or None if not found."""
        async with self._db.execute(
            "SELECT * FROM feed_cache WHERE feed_type = ?", (feed_type,)
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_feed_cache(row)

    async def upsert(self, feed_cache: FeedCache) -> None:
        """Insert or replace a feed cache record."""
        await self._db.execute(
            """
            INSERT OR REPLACE INTO feed_cache (feed_type, video_ids_json, etag, fetched_at)
            VALUES (:feed_type, :video_ids_json, :etag, :fetched_at)
            """,
            {
                "feed_type": feed_cache.feed_type,
                "video_ids_json": feed_cache.video_ids_json,
                "etag": feed_cache.etag,
                "fetched_at": feed_cache.fetched_at,
            },
        )
        await self._db.commit()


class ThumbnailRepo:
    """Repository for the `thumbnails` table."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get(self, video_id: str, resolution: str) -> Thumbnail | None:
        """Fetch a thumbnail record, or None if not found."""
        async with self._db.execute(
            "SELECT * FROM thumbnails WHERE video_id = ? AND resolution = ?",
            (video_id, resolution),
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_thumbnail(row)

    async def upsert(self, thumbnail: Thumbnail) -> None:
        """Insert or replace a thumbnail record."""
        await self._db.execute(
            """
            INSERT OR REPLACE INTO thumbnails
                (video_id, resolution, local_path, fetched_at, content_hash)
            VALUES (:video_id, :resolution, :local_path, :fetched_at, :content_hash)
            """,
            {
                "video_id": thumbnail.video_id,
                "resolution": thumbnail.resolution,
                "local_path": thumbnail.local_path,
                "fetched_at": thumbnail.fetched_at,
                "content_hash": thumbnail.content_hash,
            },
        )
        await self._db.commit()

    async def get_cached_ids(
        self, video_ids: list[str], resolution: str
    ) -> set[str]:
        """Return the subset of video_ids that already have cached thumbnails.

        Only checks for thumbnails matching the given resolution.
        """
        if not video_ids:
            return set()

        placeholders = ", ".join("?" * len(video_ids))
        async with self._db.execute(
            f"""
            SELECT video_id FROM thumbnails
            WHERE video_id IN ({placeholders}) AND resolution = ?
            """,
            [*video_ids, resolution],
        ) as cursor:
            rows = await cursor.fetchall()

        return {row["video_id"] for row in rows}


class AuthTokenRepo:
    """Repository for the `auth_tokens` table.

    Always operates on the single row with id=1 (single-user system).
    """

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get(self) -> AuthToken | None:
        """Fetch the stored auth token, or None if none exists."""
        async with self._db.execute(
            "SELECT * FROM auth_tokens WHERE id = 1"
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return _row_to_auth_token(row)

    async def upsert(self, token: AuthToken) -> None:
        """Insert or replace the auth token (always id=1)."""
        await self._db.execute(
            """
            INSERT OR REPLACE INTO auth_tokens
                (id, access_token, refresh_token, token_type, expires_at, scopes,
                 created_at, updated_at)
            VALUES (
                1, :access_token, :refresh_token, :token_type, :expires_at, :scopes,
                COALESCE(
                    (SELECT created_at FROM auth_tokens WHERE id = 1),
                    CURRENT_TIMESTAMP
                ),
                CURRENT_TIMESTAMP
            )
            """,
            {
                "access_token": encrypt_token(token.access_token),
                "refresh_token": encrypt_token(token.refresh_token) if token.refresh_token else None,
                "token_type": token.token_type,
                "expires_at": token.expires_at,
                "scopes": token.scopes,
            },
        )
        await self._db.commit()


def _row_to_watch_history(row: aiosqlite.Row) -> WatchHistoryEntry:
    return WatchHistoryEntry(
        video_id=row["video_id"],
        watched_at=row["watched_at"],
        position_seconds=row["position_seconds"],
        duration=row["duration"],
        completed=row["completed"],
    )


class WatchHistoryRepo:
    def __init__(self, db: aiosqlite.Connection):
        self._db = db

    async def upsert(self, entry: WatchHistoryEntry) -> None:
        completed = 0
        if entry.duration and entry.duration > 0 and entry.position_seconds > 0.9 * entry.duration:
            completed = 1
        await self._db.execute(
            """INSERT OR REPLACE INTO watch_history
               (video_id, watched_at, position_seconds, duration, completed)
               VALUES (?, ?, ?, ?, ?)""",
            (entry.video_id, entry.watched_at, entry.position_seconds, entry.duration, completed),
        )
        await self._db.commit()

    async def get(self, video_id: str) -> WatchHistoryEntry | None:
        async with self._db.execute(
            "SELECT * FROM watch_history WHERE video_id = ?", (video_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return _row_to_watch_history(row) if row else None

    async def get_recent(self, limit: int = 50) -> list[WatchHistoryEntry]:
        async with self._db.execute(
            "SELECT * FROM watch_history ORDER BY watched_at DESC LIMIT ?", (limit,)
        ) as cursor:
            rows = await cursor.fetchall()
        return [_row_to_watch_history(r) for r in rows]


class RecommendationRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert_run(self, run: RecommendationRun) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO recommendation_runs (run_id, run_at, source, model_name, video_count)"
            " VALUES (?, ?, ?, ?, ?)",
            (run.run_id, run.run_at, run.source, run.model_name, run.video_count),
        )
        await self._db.commit()

    async def upsert_recommendations(self, run_id: str, recs: list) -> None:
        for rec in recs:
            await self._db.execute(
                "INSERT OR REPLACE INTO recommendations (video_id, run_id, score, source, reason)"
                " VALUES (?, ?, ?, ?, ?)",
                (rec.video_id, run_id, rec.score, rec.source, rec.reason),
            )
        await self._db.commit()

    async def get_latest_run(self) -> RecommendationRun | None:
        async with self._db.execute(
            "SELECT * FROM recommendation_runs ORDER BY run_at DESC LIMIT 1"
        ) as cursor:
            row = await cursor.fetchone()
        if row is None:
            return None
        return RecommendationRun(
            run_id=row["run_id"], run_at=row["run_at"], source=row["source"],
            model_name=row["model_name"], video_count=row["video_count"],
        )

    async def get_recommendations(self, run_id: str | None = None, limit: int = 50) -> list[Recommendation]:
        if run_id is None:
            latest = await self.get_latest_run()
            if latest is None:
                return []
            run_id = latest.run_id
        async with self._db.execute(
            "SELECT * FROM recommendations WHERE run_id = ? ORDER BY score DESC LIMIT ?",
            (run_id, limit),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            Recommendation(
                video_id=r["video_id"], run_id=r["run_id"], score=r["score"],
                source=r["source"], reason=r["reason"], created_at=r["created_at"],
            )
            for r in rows
        ]


class WatchSignalRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert(self, signal: WatchSignal) -> None:
        await self._db.execute(
            """INSERT INTO watch_signals
               (video_id, session_start, completion_rate, pause_count,
                seek_forward_count, avg_playback_speed, time_of_day, abandoned_at_pct)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?)""",
            (signal.video_id, signal.session_start, signal.completion_rate,
             signal.pause_count, signal.seek_forward_count, signal.avg_playback_speed,
             signal.time_of_day, signal.abandoned_at_pct),
        )
        await self._db.commit()

    async def get_for_video(self, video_id: str) -> list[WatchSignal]:
        async with self._db.execute(
            "SELECT * FROM watch_signals WHERE video_id = ? ORDER BY session_start DESC",
            (video_id,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [
            WatchSignal(
                id=r["id"], video_id=r["video_id"], session_start=r["session_start"],
                completion_rate=r["completion_rate"], pause_count=r["pause_count"],
                seek_forward_count=r["seek_forward_count"],
                avg_playback_speed=r["avg_playback_speed"],
                time_of_day=r["time_of_day"], abandoned_at_pct=r["abandoned_at_pct"],
                updated_at=r["updated_at"],
            )
            for r in rows
        ]


class VideoRatingRepo:
    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def upsert(self, video_id: str, rating: str) -> None:
        await self._db.execute(
            "INSERT OR REPLACE INTO video_ratings (video_id, rating, rated_at) VALUES (?, ?, CURRENT_TIMESTAMP)",
            (video_id, rating),
        )
        await self._db.commit()

    async def get(self, video_id: str) -> str | None:
        async with self._db.execute(
            "SELECT rating FROM video_ratings WHERE video_id = ?", (video_id,)
        ) as cursor:
            row = await cursor.fetchone()
        return row["rating"] if row else None

    async def get_recent(self, limit: int = 50) -> list[dict]:
        async with self._db.execute(
            "SELECT video_id, rating, rated_at FROM video_ratings ORDER BY rated_at DESC LIMIT ?",
            (limit,),
        ) as cursor:
            rows = await cursor.fetchall()
        return [{"video_id": r["video_id"], "rating": r["rating"], "rated_at": r["rated_at"]} for r in rows]
