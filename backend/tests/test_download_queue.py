import pytest
import asyncio
from unittest.mock import AsyncMock, MagicMock, patch

from backend.services.download_queue import DownloadQueue

pytestmark = pytest.mark.asyncio


@pytest.fixture
def mock_dm():
    dm = MagicMock()
    dm._active = {}
    dm.get_or_start_download = AsyncMock()
    dm.download_for_queue = AsyncMock()
    return dm


@pytest.fixture
def mock_db():
    db = AsyncMock()
    db.execute = AsyncMock()
    db.commit = AsyncMock()
    return db


async def test_enqueue_and_pending_count(mock_dm):
    queue = DownloadQueue(mock_dm)
    await queue.enqueue("v1")
    await queue.enqueue("v2")
    assert queue.pending_count == 2


async def test_enqueue_many(mock_dm):
    queue = DownloadQueue(mock_dm)
    await queue.enqueue_many(["v1", "v2", "v3"])
    assert queue.pending_count == 3


async def test_worker_processes_queue(mock_dm, mock_db):
    with patch("backend.services.download_queue.get_db", return_value=mock_db):
        queue = DownloadQueue(mock_dm)
        await queue.enqueue("v1")
        await queue.start()
        await asyncio.sleep(0.2)
        await queue.stop()
        mock_dm.download_for_queue.assert_called_with("v1")


async def test_stop_cancels_workers(mock_dm):
    queue = DownloadQueue(mock_dm)
    await queue.start()
    await queue.stop()
    assert all(t.cancelled() or t.done() for t in queue._worker_tasks)
