"""Periodic yt-dlp auto-updater."""

import asyncio
import logging
import subprocess
import sys
from concurrent.futures import ThreadPoolExecutor

logger = logging.getLogger(__name__)
_executor = ThreadPoolExecutor(max_workers=1)


def _run_update() -> str:
    """Run pip install --upgrade yt-dlp in a subprocess. Returns output."""
    result = subprocess.run(
        [sys.executable, "-m", "pip", "install", "--upgrade", "yt-dlp"],
        capture_output=True,
        text=True,
        timeout=120,
    )
    return result.stdout + result.stderr


async def check_and_update_ytdlp() -> str:
    """Run yt-dlp update in a thread to avoid blocking the event loop."""
    loop = asyncio.get_running_loop()
    try:
        output = await loop.run_in_executor(_executor, _run_update)
        logger.info("yt-dlp update check completed")
        return output
    except Exception as e:
        logger.warning(f"yt-dlp update failed: {e}")
        return str(e)


async def periodic_ytdlp_update(interval_hours: int = 168) -> None:
    """Run yt-dlp update check on a weekly interval (default 168 hours)."""
    while True:
        await check_and_update_ytdlp()
        await asyncio.sleep(interval_hours * 3600)
