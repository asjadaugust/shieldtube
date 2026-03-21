"""HTTPS client for communicating with the NAS backend."""
import os
import httpx


class NASClient:
    def __init__(self, nas_url: str, api_secret: str | None = None):
        self.nas_url = nas_url.rstrip("/")
        self.api_secret = api_secret or os.environ.get("SHIELDTUBE_API_SECRET", "")
        self._headers = {}
        if self.api_secret:
            self._headers["X-ShieldTube-Secret"] = self.api_secret

    async def get_watch_history(self) -> list[dict]:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(
                f"{self.nas_url}/api/feed/history",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json().get("videos", [])

    async def get_subscriptions(self) -> list[dict]:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(
                f"{self.nas_url}/api/feed/subscriptions",
                headers=self._headers, timeout=120,
            )
            resp.raise_for_status()
            return resp.json().get("videos", [])

    async def sync_recommendations(self, run_id: str, model_name: str, videos: list[dict]) -> dict:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{self.nas_url}/api/recommendations/sync",
                headers=self._headers,
                json={"run_id": run_id, "model_name": model_name, "videos": videos},
            )
            resp.raise_for_status()
            return resp.json()

    async def enqueue_downloads(self, videos: list[dict], threshold: float = 0.7) -> dict:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.post(
                f"{self.nas_url}/api/download/enqueue-batch",
                headers=self._headers,
                json={"videos": videos, "threshold": threshold},
            )
            resp.raise_for_status()
            return resp.json()

    async def get_status(self) -> dict:
        async with httpx.AsyncClient(verify=False) as client:
            resp = await client.get(
                f"{self.nas_url}/api/recommendations/status",
                headers=self._headers,
            )
            resp.raise_for_status()
            return resp.json()
