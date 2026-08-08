"""SQL-based heuristic recommender — runs on NAS with zero ML dependencies."""

import math
import random
from collections import defaultdict
import aiosqlite

# Max videos from a single channel in the final results
MAX_PER_CHANNEL = 5


class HeuristicRecommender:
    """Ranks candidate videos using channel affinity, freshness, and completion history.

    Uses logarithmic channel affinity to prevent a single dominant channel
    from taking over the feed, plus a per-channel diversity cap.
    """

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
            COALESCE(cs.watch_count, 0) as raw_watch_count,
            (SELECT MAX(watch_count) FROM channel_stats) as max_watch_count,
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
            raw_count = r["raw_watch_count"] or 0
            max_count = r["max_watch_count"] or 1
            # Log scaling: log(11+1)/log(11+1)=1.0, log(4+1)/log(11+1)=0.65, log(1+1)/log(11+1)=0.28
            ch_affinity = math.log(raw_count + 1) / math.log(max_count + 1) if raw_count > 0 else 0.0
            freshness = r["freshness"] or 0
            views = r["view_count"] or 0
            popularity = min(1.0, math.log(views + 1) / 20.0) if views > 0 else 0.0
            base_score = (0.35 * ch_affinity) + (0.35 * freshness) + (0.3 * popularity)
            # Add ±15% random jitter so results vary between runs
            jitter = random.uniform(-0.15, 0.15) * max(base_score, 0.1)
            score = base_score + jitter
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

        # Enforce per-channel diversity cap
        channel_counts: dict[str, int] = defaultdict(int)
        diverse_results = []
        for r in results:
            cid = r["channel_id"]
            if channel_counts[cid] < MAX_PER_CHANNEL:
                diverse_results.append(r)
                channel_counts[cid] += 1
            if len(diverse_results) >= limit:
                break

        return diverse_results
