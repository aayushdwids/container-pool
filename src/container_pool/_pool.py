from __future__ import annotations

import asyncio
import logging

from ._backend import BaseContainerBackend
from ._container import Container
from ._exceptions import (
    ContainerCreationError,
    ContainerExpiredError,
    ContainerPoolExhaustedError,
)
from ._retry import retry_with_backoff
from ._types import ContainerStatus

log = logging.getLogger(__name__)


class ContainerPool:
    """
    Async FIFO pool of Container objects backed by any BaseContainerBackend.

    Usage:
        pool = ContainerPool(
            backend,
            max_pool_size=5,
            acquire_timeout=30.0,
            container_name="mypool",
        )
        container = await pool.acquire()
        try:
            ...
        finally:
            await pool.release(container)
        await pool.shutdown()
    """

    def __init__(
        self,
        backend: BaseContainerBackend,
        *,
        max_pool_size: int,
        acquire_timeout: float,
        container_name: str,
        creation_max_attempts: int = 3,
        creation_base_delay: float = 1.0,
    ) -> None:
        if not (1 <= max_pool_size <= 50):
            raise ValueError(f"max_pool_size must be 1-50, got {max_pool_size}")
        if acquire_timeout <= 0:
            raise ValueError("acquire_timeout must be positive")

        self._backend = backend
        self.max_pool_size = max_pool_size
        self.acquire_timeout = acquire_timeout
        self.container_name = container_name
        self._creation_max_attempts = creation_max_attempts
        self._creation_base_delay = creation_base_delay

        self._queue: asyncio.Queue[Container] = asyncio.Queue()
        # Total containers ever created = items in queue + items checked out.
        # Only decremented on failed creation (rollback) — not on expiry/replace.
        self._total: int = 0
        self._lock = asyncio.Lock()  # guards the growth decision (_total += 1)
        self._closed: bool = False

    # -------------------------------------------------------------------------
    # Public API
    # -------------------------------------------------------------------------

    async def acquire(self) -> Container:
        """
        Return a validated, live Container from the pool.

        Flow:
          1. Queue has an item (non-blocking)? → validate_or_recreate, return.
          2. _total < max_pool_size? → create new container, return.
          3. Otherwise: wait up to acquire_timeout for a release().
             Raises ContainerPoolExhaustedError on timeout.
        """
        if self._closed:
            raise RuntimeError("ContainerPool is shut down")

        # Fast path: something already in the queue
        try:
            container = self._queue.get_nowait()
            return await self._validate_or_recreate(container)
        except asyncio.QueueEmpty:
            pass

        # Growth path: can we create a new one?
        async with self._lock:
            if self._total < self.max_pool_size:
                self._total += 1
                should_create = True
            else:
                should_create = False

        if should_create:
            try:
                return await self._create_container_with_retry()
            except Exception:
                async with self._lock:
                    self._total -= 1  # roll back — creation failed
                raise

        # Blocking path: wait for someone to release
        try:
            container = await asyncio.wait_for(
                self._queue.get(),
                timeout=self.acquire_timeout,
            )
        except asyncio.TimeoutError:
            raise ContainerPoolExhaustedError(
                timeout=self.acquire_timeout,
                pool_size=self.max_pool_size,
            )

        return await self._validate_or_recreate(container)

    async def release(self, container: Container) -> None:
        """
        Return a container to the pool.

        No re-validation at release time — validation happens at the next
        acquire(). This keeps release() fast (safe to call in finally blocks).

        If the pool is already shut down, destroys the container instead
        of queuing it.
        """
        if self._closed:
            await self._safe_destroy(container)
            return
        await self._queue.put(container)

    async def shutdown(self) -> None:
        """
        Mark pool as closed and destroy all containers currently in the queue.

        Containers that are checked out at shutdown time will be destroyed
        when release() is called on them. This method is idempotent.
        """
        if self._closed:
            return
        self._closed = True
        log.info("ContainerPool shutting down. Draining queue...")

        destroyed = 0
        while True:
            try:
                container = self._queue.get_nowait()
                await self._safe_destroy(container)
                destroyed += 1
            except asyncio.QueueEmpty:
                break

        log.info("ContainerPool shutdown complete. Destroyed %d container(s).", destroyed)

    # -------------------------------------------------------------------------
    # Internal helpers
    # -------------------------------------------------------------------------

    async def _create_container_with_retry(self) -> Container:
        info = await retry_with_backoff(
            lambda: self._backend.create_container(self.container_name),
            max_attempts=self._creation_max_attempts,
            base_delay=self._creation_base_delay,
            retryable=ContainerCreationError,
        )
        log.debug("Created container %r", info.container_id)
        return Container(container_id=info.container_id, backend=self._backend)

    async def _validate_or_recreate(self, container: Container) -> Container:
        """
        Confirm the container is alive. If expired or gone, replace it
        with a freshly created one (total pool count stays the same: 1-for-1).
        """
        try:
            info = await self._backend.get_container(container.container_id)
            if info.status == ContainerStatus.ACTIVE:
                return container
            log.info(
                "Container %r has status=%r, recreating.",
                container.container_id,
                info.status,
            )
        except ContainerExpiredError:
            log.info(
                "Container %r returned expired/404, recreating.",
                container.container_id,
            )
        except Exception as exc:
            log.warning(
                "Unexpected error validating container %r (%s), recreating.",
                container.container_id,
                exc,
            )

        await self._safe_destroy(container)
        info = await retry_with_backoff(
            lambda: self._backend.create_container(self.container_name),
            max_attempts=self._creation_max_attempts,
            base_delay=self._creation_base_delay,
            retryable=ContainerCreationError,
        )
        log.debug(
            "Recreated: %r -> %r", container.container_id, info.container_id
        )
        return Container(container_id=info.container_id, backend=self._backend)

    async def _safe_destroy(self, container: Container) -> None:
        """Destroy a container, swallowing all errors."""
        try:
            await self._backend.destroy_container(container.container_id)
        except Exception:
            log.warning(
                "Failed to destroy container %r during cleanup",
                container.container_id,
                exc_info=True,
            )
