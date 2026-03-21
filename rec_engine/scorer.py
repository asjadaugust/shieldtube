"""User profile vector construction and candidate scoring."""
import math
from datetime import datetime, timedelta, timezone

import numpy as np


class Scorer:
    RECENCY_HALF_LIFE_DAYS = 7
    FRESHNESS_HALF_LIFE_HOURS = 48

    def build_profile(self, history: list[dict], embeddings: np.ndarray) -> np.ndarray:
        now = datetime.now(timezone.utc)
        weights = []
        for video in history:
            w = 1.0
            if video.get("completed"):
                w *= 1.0
            else:
                w *= 0.4
            watched_at = video.get("watched_at")
            if watched_at:
                try:
                    dt = datetime.fromisoformat(watched_at)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    days_ago = (now - dt).total_seconds() / 86400
                    w *= math.exp(-0.693 * days_ago / self.RECENCY_HALF_LIFE_DAYS)
                except (ValueError, TypeError):
                    pass
            weights.append(w)

        weights = np.array(weights, dtype=np.float32)
        if weights.sum() == 0:
            return np.zeros(embeddings.shape[1])
        profile = (embeddings.T @ weights) / weights.sum()
        return profile / (np.linalg.norm(profile) + 1e-8)

    def score_candidates(
        self, candidates: list[dict], embeddings: np.ndarray,
        profile: np.ndarray, history: list[dict], limit: int = 100,
    ) -> list[dict]:
        now = datetime.now(timezone.utc)

        channel_counts: dict[str, int] = {}
        for v in history:
            ch = v.get("channel_id", v.get("channelId", ""))
            channel_counts[ch] = channel_counts.get(ch, 0) + 1
        max_count = max(channel_counts.values()) if channel_counts else 1

        norms = np.linalg.norm(embeddings, axis=1, keepdims=True) + 1e-8
        normalized = embeddings / norms
        similarities = normalized @ profile

        scored = []
        for i, candidate in enumerate(candidates):
            sim = float(similarities[i])
            ch_id = candidate.get("channel_id", candidate.get("channelId", ""))
            ch_affinity = channel_counts.get(ch_id, 0) / max_count

            freshness = 0.0
            pub = candidate.get("published_at", candidate.get("publishedAt"))
            if pub:
                try:
                    dt = datetime.fromisoformat(pub)
                    if dt.tzinfo is None:
                        dt = dt.replace(tzinfo=timezone.utc)
                    hours_ago = (now - dt).total_seconds() / 3600
                    freshness = max(0, math.exp(-0.693 * hours_ago / self.FRESHNESS_HALF_LIFE_HOURS))
                except (ValueError, TypeError):
                    pass

            views = candidate.get("view_count", candidate.get("viewCount")) or 0
            popularity = min(1.0, math.log(views + 1) / 20.0) if views > 0 else 0.0

            score = (0.6 * sim) + (0.2 * ch_affinity) + (0.1 * freshness) + (0.1 * popularity)

            reason = []
            if ch_affinity > 0.5:
                reason.append("channel you watch")
            if sim > 0.7:
                reason.append("similar content")
            if freshness > 0.8:
                reason.append("recently published")

            scored.append({
                **candidate,
                "score": score,
                "reason": ", ".join(reason) if reason else "recommended",
            })

        scored.sort(key=lambda x: x["score"], reverse=True)
        return scored[:limit]
