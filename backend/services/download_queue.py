"""Async download queue — parallel workers with yt-dlp concurrent fragments."""
import asyncio
import logging

from backend.config import settings
from backend.db.database import get_db
from backend.services.download_manager import DownloadManager

logger = logging.getLogger(__name__)


class DownloadQueue:
    """Async queue with multiple workers for parallel background downloads."""

    def __init__(self, download_manager: DownloadManager):
        self._dm = download_manager
        self._queue: asyncio.Queue[str] = asyncio.Queue()
        self._queued: set[str] = set()  # tracks what's already queued or in-progress
        self._worker_tasks: list[asyncio.Task] = []

    async def start(self):
        n = settings.download_max_parallel
        self._worker_tasks = [
            asyncio.create_task(self._worker(i)) for i in range(n)
        ]
        logger.info("Download queue started with %d workers", n)

    async def stop(self):
        for task in self._worker_tasks:
            task.cancel()
        for task in self._worker_tasks:
            try:
                await task
            except asyncio.CancelledError:
                pass
        self._worker_tasks.clear()

    async def enqueue(self, video_id: str):
        if video_id not in self._queued:
            self._queued.add(video_id)
            await self._queue.put(video_id)

    async def enqueue_many(self, video_ids: list[str]):
        for vid in video_ids:
            await self.enqueue(vid)

    @property
    def pending_count(self) -> int:
        return self._queue.qsize()

    async def _worker(self, worker_id: int):
        while True:
            video_id = await self._queue.get()
            try:
                db = await get_db()
                await db.execute(
                    "UPDATE videos SET download_source = COALESCE(download_source, 'auto') WHERE id = ?",
                    (video_id,),
                )
                await db.commit()

                logger.info("Worker %d: download starting: %s", worker_id, video_id)
                await self._dm.download_for_queue(video_id)
                logger.info("Worker %d: download complete: %s", worker_id, video_id)
            except asyncio.CancelledError:
                break
            except Exception as e:
                logger.warning("Worker %d: download failed for %s: %s", worker_id, video_id, e)
            finally:
                self._queued.discard(video_id)
                self._queue.task_done()
