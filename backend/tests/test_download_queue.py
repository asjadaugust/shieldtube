import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock

from backend.services.download_queue import DownloadQueue

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_dm():
    dm = MagicMock()
    dm._active = {}
    dm.get_or_start_download = AsyncMock()
    return dm


async def test_enqueue_and_pending_count(mock_dm):
    queue = DownloadQueue(mock_dm)
    await queue.enqueue("v1")
    await queue.enqueue("v2")
    assert queue.pending_count == 2


async def test_enqueue_many(mock_dm):
    queue = DownloadQueue(mock_dm)
    await queue.enqueue_many(["v1", "v2", "v3"])
    assert queue.pending_count == 3


async def test_worker_processes_queue(mock_dm):
    queue = DownloadQueue(mock_dm)
    await queue.enqueue("v1")
    await queue.start()
    await asyncio.sleep(0.2)  # Let worker pick up item
    await queue.stop()
    mock_dm.get_or_start_download.assert_called_with("v1")


async def test_stop_cancels_worker(mock_dm):
    queue = DownloadQueue(mock_dm)
    await queue.start()
    await queue.stop()
    assert queue._worker_task.cancelled() or queue._worker_task.done()
