import asyncio
import logging

logger = logging.getLogger(__name__)


async def with_retry(fn, max_retries: int = 3, backoff_base: float = 1.0, description: str = "operation"):
    """Call an async function with exponential backoff retry."""
    for attempt in range(max_retries + 1):
        try:
            return await fn()
        except Exception as e:
            if attempt == max_retries:
                logger.error(f"{description} failed after {max_retries + 1} attempts: {e}")
                raise
            wait = backoff_base * (2 ** attempt)
            logger.warning(f"{description} attempt {attempt + 1} failed: {e}. Retrying in {wait}s...")
            await asyncio.sleep(wait)
