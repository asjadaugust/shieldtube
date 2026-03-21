"""Adaptive model loading and video text embedding."""
import logging

import numpy as np
import psutil
from sentence_transformers import SentenceTransformer

logger = logging.getLogger(__name__)

MODEL_SIZES_MB = {
    "all-mpnet-base-v2": 420,
    "all-MiniLM-L12-v2": 120,
    "all-MiniLM-L6-v2": 80,
}


class Embedder:
    def __init__(self, config: dict, model_override: str | None = None):
        self.config = config
        self.model_name = model_override or config["models"]["preferred"]
        self._model = self._load_model()

    def _load_model(self) -> SentenceTransformer:
        models_to_try = [self.model_name] + self.config["models"].get("fallback", [])
        threshold_mb = self.config.get("ram_threshold_mb", 500)
        available_mb = psutil.virtual_memory().available / (1024 * 1024)
        budget_mb = available_mb - threshold_mb

        for name in models_to_try:
            model_size = MODEL_SIZES_MB.get(name, 200)
            if budget_mb < model_size and self.config["models"].get("auto_fallback"):
                logger.info(f"Low RAM: {name} ({model_size}MB) may exceed {budget_mb:.0f}MB budget")
            try:
                model = SentenceTransformer(name)
                self.model_name = name
                logger.info(f"Loaded model: {name}")
                return model
            except Exception as e:
                logger.warning(f"Failed to load {name}: {e}")
                if not self.config["models"].get("auto_fallback"):
                    raise

        raise RuntimeError("No embedding model could be loaded")

    def embed_videos(self, videos: list[dict]) -> np.ndarray:
        texts = [self._video_to_text(v) for v in videos]
        return self._model.encode(texts, show_progress_bar=len(texts) > 50)

    @staticmethod
    def _video_to_text(video: dict) -> str:
        title = video.get("title", "")
        channel = video.get("channel_name", video.get("channelName", ""))
        desc = (video.get("description") or "")[:200]
        parts = [p for p in [title, channel, desc] if p]
        return " | ".join(parts)
