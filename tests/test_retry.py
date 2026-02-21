import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from container_pool._retry import retry_with_backoff


async def test_succeeds_on_first_attempt():
    fn = AsyncMock(return_value="ok")
    result = await retry_with_backoff(fn, max_attempts=3, base_delay=0.01)
    assert result == "ok"
    fn.assert_awaited_once()


async def test_retries_on_retryable_exception():
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 3:
            raise ValueError("transient")
        return "success"

    with patch("container_pool._retry.asyncio.sleep", new_callable=AsyncMock):
        result = await retry_with_backoff(
            flaky, max_attempts=3, base_delay=0.01, retryable=ValueError
        )
    assert result == "success"
    assert call_count == 3


async def test_raises_after_max_attempts():
    fn = AsyncMock(side_effect=ValueError("always fails"))

    with patch("container_pool._retry.asyncio.sleep", new_callable=AsyncMock):
        with pytest.raises(ValueError, match="always fails"):
            await retry_with_backoff(
                fn, max_attempts=3, base_delay=0.01, retryable=ValueError
            )

    assert fn.await_count == 3


async def test_non_retryable_exception_propagates_immediately():
    fn = AsyncMock(side_effect=TypeError("not retryable"))

    with pytest.raises(TypeError, match="not retryable"):
        await retry_with_backoff(
            fn, max_attempts=3, base_delay=0.01, retryable=ValueError
        )

    fn.assert_awaited_once()


async def test_jitter_does_not_break_delay():
    """Retry still completes with jitter enabled (default)."""
    call_count = 0

    async def flaky():
        nonlocal call_count
        call_count += 1
        if call_count < 2:
            raise RuntimeError("once")
        return "done"

    with patch("container_pool._retry.asyncio.sleep", new_callable=AsyncMock):
        result = await retry_with_backoff(
            flaky, max_attempts=2, base_delay=0.01, jitter=True, retryable=RuntimeError
        )
    assert result == "done"
