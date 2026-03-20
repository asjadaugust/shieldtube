"""Async download queue for pre-caching — Phase 4c."""
import asyncio
import logging

from backend.services.download_manager import DownloadManager

logger = logging.getLogger(__name__)


class DownloadQueue:
    """Async queue that processes pre-cache downloads one at a time."""

    def __init__(self, download_manager: DownloadManager):
        self._dm = download_manager
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._worker_task: asyncio.Task | None = None

    async def start(self):
        self._worker_task = asyncio.create_task(self._worker())

    async def stop(self):
        if self._worker_task:
            self._worker_task.cancel()
            try:
                await self._worker_task
            except asyncio.CancelledError:
                pass

    async def enqueue(self, video_id: str):
        await self._queue.put(video_id)

    async def enqueue_many(self, video_ids: list[str]):
        for vid in video_ids:
            await self._queue.put(vid)

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    async def _worker(self):
        while True:
            video_id = await self._queue.get()
            try:
                # Wait if on-demand download is active
                while self._has_active_download():
                    await asyncio.sleep(5)

                logger.info(f"Pre-cache download starting: {video_id}")
                await self._dm.get_or_start_download(video_id)
                await self._wait_for_completion(video_id)
                logger.info(f"Pre-cache download complete: {video_id}")
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning(f"Pre-cache download failed for {video_id}: {e}")
            finally:
                self._queue.task_done()

    def _has_active_download(self) -> bool:
        for state in self._dm._active.values():
            if state.status == "downloading":
                return True
        return False

    async def _wait_for_completion(self, video_id: str, timeout: int = 3600):
        elapsed = 0
        while elapsed < timeout:
            state = self._dm._active.get(video_id)
            if state is None or state.status in ("cached", "error"):
                return
            await asyncio.sleep(5)
            elapsed += 5
