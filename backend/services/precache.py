"""Pre-cache rules loader and video matcher — Phase 4c."""
import json
import logging
from pathlib import Path

import aiosqlite

logger = logging.getLogger(__name__)


def load_rules(path: Path) -> list[dict]:
    """Read pre-cache rules from JSON file. Returns empty list on any error."""
    try:
        if not path.exists():
            return []
        data = json.loads(path.read_text())
        rules = data.get("precache_rules", [])
        # Validate required fields
        valid = []
        for rule in rules:
            if rule.get("type") == "channel" and rule.get("channel_id"):
                valid.append(rule)
            elif rule.get("type") == "playlist" and rule.get("playlist_id"):
                valid.append(rule)
            else:
                logger.warning(f"Invalid pre-cache rule skipped: {rule}")
        return valid
    except (json.JSONDecodeError, Exception) as e:
        logger.warning(f"Failed to load pre-cache rules from {path}: {e}")
        return []


async def match_videos(
    videos: list[dict],
    rules: list[dict],
    db: aiosqlite.Connection,
) -> list[str]:
    """Match feed videos against rules. Return video IDs to queue for download."""
    if not rules or not videos:
        return []

    # Get already-cached video IDs
    video_ids = [v["id"] for v in videos]
    placeholders = ",".join("?" * len(video_ids))
    async with db.execute(
        f"SELECT id FROM videos WHERE id IN ({placeholders}) AND cache_status IN ('cached', 'downloading')",
        video_ids,
    ) as cursor:
        rows = await cursor.fetchall()
    already_cached = {row[0] for row in rows}

    to_queue = []
    for rule in rules:
        if rule["type"] != "channel":
            continue  # Playlist rules deferred

        channel_id = rule["channel_id"]
        max_videos = rule.get("max_videos", 5)

        matches = [
            v["id"] for v in videos
            if v.get("channel_id") == channel_id
            and v["id"] not in already_cached
            and v["id"] not in to_queue
        ]
        to_queue.extend(matches[:max_videos])

    return to_queue
