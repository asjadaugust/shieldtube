import pytest
import asyncio
from backend.services.retry import with_retry

pytestmark = pytest.mark.asyncio


async def test_succeeds_first_try():
    call_count = 0
    async def fn():
        nonlocal call_count
        call_count += 1
        return "ok"
    result = await with_retry(fn)
    assert result == "ok"
    assert call_count == 1


async def test_retries_on_failure():
    call_count = 0
    async def fn():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ConnectionError("fail")
        return "ok"
    result = await with_retry(fn, backoff_base=0.01)
    assert result == "ok"
    assert call_count == 3


async def test_raises_after_max_retries():
    async def fn():
        raise ConnectionError("always fails")
    with pytest.raises(ConnectionError):
        await with_retry(fn, max_retries=2, backoff_base=0.01)


async def test_zero_retries_raises_immediately():
    call_count = 0
    async def fn():
        nonlocal call_count
        call_count += 1
        raise ValueError("fail")
    with pytest.raises(ValueError):
        await with_retry(fn, max_retries=0)
    assert call_count == 1
