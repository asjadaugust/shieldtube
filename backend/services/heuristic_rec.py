"""SQL-based heuristic recommender — runs on NAS with zero ML dependencies."""

import math
import aiosqlite


class HeuristicRecommender:
    """Ranks candidate videos using channel affinity, freshness, and completion history."""

    def __init__(self, db: aiosqlite.Connection) -> None:
        self._db = db

    async def get_recommendations(self, limit: int = 50) -> list[dict]:
        query = """
        WITH channel_stats AS (
            SELECT
                v.channel_id,
                COUNT(*) as watch_count,
                AVG(wh.completed) as avg_completion
            FROM watch_history wh
            JOIN videos v ON v.id = wh.video_id
            GROUP BY v.channel_id
        ),
        candidates AS (
            SELECT v.*
            FROM videos v
            WHERE v.id NOT IN (SELECT video_id FROM watch_history)
              AND v.published_at IS NOT NULL
        )
        SELECT
            c.id, c.title, c.channel_name, c.channel_id,
            c.view_count, c.duration, c.published_at,
            COALESCE(cs.watch_count * 1.0 / (SELECT MAX(watch_count) FROM channel_stats), 0) as channel_affinity,
            CASE
                WHEN c.published_at IS NOT NULL THEN
                    MAX(0, 1.0 - (julianday('now') - julianday(c.published_at)) / 2.0)
                ELSE 0
            END as freshness
        FROM candidates c
        LEFT JOIN channel_stats cs ON c.channel_id = cs.channel_id
        """
        async with self._db.execute(query) as cursor:
            rows = await cursor.fetchall()

        results = []
        for r in rows:
            ch_affinity = r["channel_affinity"] or 0
            freshness = r["freshness"] or 0
            views = r["view_count"] or 0
            popularity = min(1.0, math.log(views + 1) / 20.0) if views > 0 else 0.0
            score = (0.5 * ch_affinity) + (0.3 * freshness) + (0.2 * popularity)
            results.append({
                "id": r["id"],
                "title": r["title"],
                "channel_name": r["channel_name"],
                "channel_id": r["channel_id"],
                "view_count": r["view_count"],
                "duration": r["duration"],
                "published_at": r["published_at"],
                "score": score,
            })
        results.sort(key=lambda x: x["score"], reverse=True)
        return results[:limit]
