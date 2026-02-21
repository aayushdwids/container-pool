from __future__ import annotations

import asyncio
import logging
import random
from collections.abc import Awaitable, Callable
from typing import TypeVar

log = logging.getLogger(__name__)

T = TypeVar("T")


async def retry_with_backoff(
    fn: Callable[[], Awaitable[T]],
    *,
    max_attempts: int = 3,
    base_delay: float = 1.0,
    max_delay: float = 30.0,
    jitter: bool = True,
    retryable: type[BaseException] | tuple[type[BaseException], ...] = Exception,
) -> T:
    """
    Call fn() up to max_attempts times with exponential backoff.

    Delay schedule (before jitter): 1s, 2s, 4s, 8s... capped at max_delay.
    Jitter is ±20% of the computed delay to avoid thundering herd.

    Only retries on exceptions matching `retryable`.
    Raises the last exception after all attempts are exhausted.
    """
    last_exc: BaseException | None = None

    for attempt in range(1, max_attempts + 1):
        try:
            return await fn()
        except retryable as exc:
            last_exc = exc
            if attempt == max_attempts:
                break
            delay = min(base_delay * (2 ** (attempt - 1)), max_delay)
            if jitter:
                delay *= random.uniform(0.8, 1.2)
            log.warning(
                "Attempt %d/%d failed (%s). Retrying in %.2fs.",
                attempt,
                max_attempts,
                exc,
                delay,
            )
            await asyncio.sleep(delay)

    raise last_exc  # type: ignore[misc]
