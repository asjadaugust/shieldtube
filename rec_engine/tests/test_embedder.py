"""Tests for adaptive embedding model selection and video embedding."""
from unittest.mock import patch, MagicMock
import numpy as np


def test_model_selection_picks_preferred_when_ram_available():
    from rec_engine.embedder import Embedder
    config = {
        "models": {
            "preferred": "all-mpnet-base-v2",
            "fallback": ["all-MiniLM-L6-v2"],
            "auto_fallback": True,
        },
        "ram_threshold_mb": 500,
    }
    with patch("rec_engine.embedder.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value = MagicMock(available=4_000_000_000)
        with patch("rec_engine.embedder.SentenceTransformer") as mock_st:
            mock_st.return_value = MagicMock()
            embedder = Embedder(config)
            assert embedder.model_name == "all-mpnet-base-v2"


def test_model_selection_falls_back_when_ram_low():
    from rec_engine.embedder import Embedder
    config = {
        "models": {
            "preferred": "all-mpnet-base-v2",
            "fallback": ["all-MiniLM-L6-v2"],
            "auto_fallback": True,
        },
        "ram_threshold_mb": 500,
    }
    with patch("rec_engine.embedder.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value = MagicMock(available=600_000_000)
        with patch("rec_engine.embedder.SentenceTransformer") as mock_st:
            mock_st.side_effect = [RuntimeError("OOM"), MagicMock()]
            embedder = Embedder(config)
            assert embedder.model_name == "all-MiniLM-L6-v2"


def test_embed_videos_returns_array():
    from rec_engine.embedder import Embedder
    config = {
        "models": {"preferred": "all-MiniLM-L6-v2", "fallback": [], "auto_fallback": True},
        "ram_threshold_mb": 100,
    }
    with patch("rec_engine.embedder.psutil") as mock_psutil:
        mock_psutil.virtual_memory.return_value = MagicMock(available=4_000_000_000)
        with patch("rec_engine.embedder.SentenceTransformer") as mock_st:
            mock_model = MagicMock()
            mock_model.encode.return_value = np.array([[0.1, 0.2, 0.3], [0.4, 0.5, 0.6]])
            mock_st.return_value = mock_model
            embedder = Embedder(config)
            videos = [
                {"title": "Test Video 1", "channel_name": "Ch1"},
                {"title": "Test Video 2", "channel_name": "Ch2"},
            ]
            result = embedder.embed_videos(videos)
            assert result.shape == (2, 3)


def test_video_to_text_format():
    from rec_engine.embedder import Embedder
    text = Embedder._video_to_text({
        "title": "My Video",
        "channel_name": "My Channel",
        "description": "A great video about something",
    })
    assert "My Video" in text
    assert "My Channel" in text
    assert "A great video" in text
    assert " | " in text
