"""Tests for user profile building and candidate scoring."""
import numpy as np
from datetime import datetime, timedelta, timezone


def test_build_profile_returns_weighted_average():
    from rec_engine.scorer import Scorer
    scorer = Scorer()
    history = [
        {"id": "v1", "watched_at": datetime.now(timezone.utc).isoformat(), "completed": 1},
        {"id": "v2", "watched_at": datetime.now(timezone.utc).isoformat(), "completed": 0},
    ]
    embeddings = np.array([[1.0, 0.0, 0.0], [0.0, 1.0, 0.0]])
    profile = scorer.build_profile(history, embeddings)
    assert profile.shape == (3,)
    assert profile[0] > profile[1]


def test_score_candidates_returns_sorted_list():
    from rec_engine.scorer import Scorer
    scorer = Scorer()
    profile = np.array([1.0, 0.0, 0.0])
    candidates = [
        {"id": "c1", "channel_id": "ch1", "view_count": 1000,
         "published_at": datetime.now(timezone.utc).isoformat()},
        {"id": "c2", "channel_id": "ch2", "view_count": 500,
         "published_at": (datetime.now(timezone.utc) - timedelta(days=5)).isoformat()},
    ]
    embeddings = np.array([[0.9, 0.1, 0.0], [0.1, 0.9, 0.0]])
    history = [{"channel_id": "ch1", "completed": 1}]
    scored = scorer.score_candidates(candidates, embeddings, profile, history, limit=10)
    assert len(scored) == 2
    assert scored[0]["id"] == "c1"
    assert scored[0]["score"] > scored[1]["score"]


def test_score_empty_history():
    from rec_engine.scorer import Scorer
    scorer = Scorer()
    profile = np.zeros(3)
    candidates = [{"id": "c1", "channel_id": "ch1", "view_count": 100, "published_at": datetime.now(timezone.utc).isoformat()}]
    embeddings = np.array([[0.5, 0.5, 0.0]])
    scored = scorer.score_candidates(candidates, embeddings, profile, [], limit=10)
    assert len(scored) == 1
    assert scored[0]["score"] >= 0
