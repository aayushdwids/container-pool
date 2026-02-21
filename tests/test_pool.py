import asyncio
import pytest
from unittest.mock import AsyncMock, patch

from container_pool import (
    ContainerPool,
    ContainerInfo,
    ContainerStatus,
    ContainerPoolExhaustedError,
)
from container_pool._exceptions import ContainerExpiredError, ContainerCreationError


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def make_info(container_id: str, status: ContainerStatus = ContainerStatus.ACTIVE) -> ContainerInfo:
    return ContainerInfo(container_id=container_id, status=status)


# ---------------------------------------------------------------------------
# Basic acquire / create
# ---------------------------------------------------------------------------

async def test_acquire_creates_container_on_empty_pool(pool_factory, mock_backend):
    pool = pool_factory()
    container = await pool.acquire()
    assert container.container_id == "ctr-001"
    mock_backend.create_container.assert_awaited_once()
    await pool.shutdown()


async def test_acquire_increments_total(pool_factory, mock_backend):
    pool = pool_factory(max_pool_size=3)
    await pool.acquire()
    assert pool._total == 1
    await pool.acquire()
    assert pool._total == 2
    await pool.shutdown()


async def test_acquire_validates_queued_container(pool_factory, mock_backend):
    pool = pool_factory()
    c = await pool.acquire()
    await pool.release(c)

    mock_backend.create_container.reset_mock()
    c2 = await pool.acquire()

    # get_container should be called for validation, create_container should NOT
    mock_backend.get_container.assert_awaited()
    mock_backend.create_container.assert_not_awaited()
    assert c2.container_id == "ctr-001"
    await pool.shutdown()


# ---------------------------------------------------------------------------
# Expiry recovery
# ---------------------------------------------------------------------------

async def test_acquire_replaces_expired_container(pool_factory, mock_backend):
    pool = pool_factory()

    # First acquire creates container
    c = await pool.acquire()
    total_after_first = pool._total
    await pool.release(c)

    # On next acquire, get_container reports expired
    mock_backend.get_container.side_effect = ContainerExpiredError("ctr-001")
    mock_backend.create_container.return_value = make_info("ctr-002")

    c2 = await pool.acquire()
    assert c2.container_id == "ctr-002"
    # Total unchanged — 1-for-1 replacement
    assert pool._total == total_after_first
    await pool.shutdown()


async def test_acquire_replaces_non_active_status(pool_factory, mock_backend):
    pool = pool_factory()
    c = await pool.acquire()
    await pool.release(c)

    mock_backend.get_container.return_value = make_info("ctr-001", ContainerStatus.EXPIRED)
    mock_backend.create_container.return_value = make_info("ctr-003")

    c2 = await pool.acquire()
    assert c2.container_id == "ctr-003"
    await pool.shutdown()


# ---------------------------------------------------------------------------
# Pool exhaustion
# ---------------------------------------------------------------------------

async def test_acquire_raises_when_exhausted_on_timeout(pool_factory, mock_backend):
    pool = pool_factory(max_pool_size=1, acquire_timeout=0.1)

    c = await pool.acquire()  # consumes the only slot

    with pytest.raises(ContainerPoolExhaustedError) as exc_info:
        await pool.acquire()

    assert exc_info.value.pool_size == 1
    assert exc_info.value.timeout == pytest.approx(0.1)
    await pool.release(c)
    await pool.shutdown()


async def test_acquire_unblocks_when_concurrent_release(pool_factory, mock_backend):
    pool = pool_factory(max_pool_size=1, acquire_timeout=2.0)
    c = await pool.acquire()

    async def release_after_delay():
        await asyncio.sleep(0.05)
        await pool.release(c)

    release_task = asyncio.create_task(release_after_delay())
    c2 = await pool.acquire()  # should unblock once c is released

    assert c2 is not None
    await release_task
    await pool.shutdown()


# ---------------------------------------------------------------------------
# Concurrency invariant
# ---------------------------------------------------------------------------

async def test_concurrent_acquires_respect_max_pool_size(mock_backend):
    """10 concurrent acquires with max=3 should create exactly 3 containers."""
    create_count = 0
    original_create = mock_backend.create_container

    async def counting_create(name: str) -> ContainerInfo:
        nonlocal create_count
        create_count += 1
        return make_info(f"ctr-{create_count:03d}")

    mock_backend.create_container.side_effect = counting_create

    pool = ContainerPool(
        mock_backend,
        max_pool_size=3,
        acquire_timeout=2.0,
        container_name="test",
    )

    # Acquire 3 containers concurrently (fills the pool)
    containers = await asyncio.gather(*[pool.acquire() for _ in range(3)])
    assert create_count == 3

    # Release all
    for c in containers:
        await pool.release(c)

    # Re-acquire from pool — no new containers should be created
    mock_backend.get_container.side_effect = None
    mock_backend.get_container.return_value = make_info("ctr-001")
    containers2 = await asyncio.gather(*[pool.acquire() for _ in range(3)])
    assert create_count == 3  # still 3

    await pool.shutdown()


# ---------------------------------------------------------------------------
# Shutdown
# ---------------------------------------------------------------------------

async def test_shutdown_destroys_all_queued_containers(pool_factory, mock_backend):
    pool = pool_factory(max_pool_size=2)

    c1 = await pool.acquire()
    c2 = await pool.acquire()
    await pool.release(c1)
    await pool.release(c2)

    await pool.shutdown()

    assert mock_backend.destroy_container.await_count == 2


async def test_release_after_shutdown_destroys_container(pool_factory, mock_backend):
    pool = pool_factory()
    c = await pool.acquire()

    await pool.shutdown()
    await pool.release(c)

    # Container should be destroyed, not put back in queue
    mock_backend.destroy_container.assert_awaited()
    assert pool._queue.empty()


async def test_shutdown_is_idempotent(pool_factory, mock_backend):
    pool = pool_factory()
    await pool.shutdown()
    await pool.shutdown()  # should not raise or double-destroy


# ---------------------------------------------------------------------------
# Error handling
# ---------------------------------------------------------------------------

async def test_creation_failure_rolls_back_total(pool_factory, mock_backend):
    pool = pool_factory(max_pool_size=2)
    mock_backend.create_container.side_effect = ContainerCreationError(
        attempts=3, cause=Exception("api down")
    )

    with pytest.raises(ContainerCreationError):
        await pool.acquire()

    assert pool._total == 0  # rolled back


async def test_acquire_raises_on_closed_pool(pool_factory):
    pool = pool_factory()
    await pool.shutdown()

    with pytest.raises(RuntimeError, match="shut down"):
        await pool.acquire()


# ---------------------------------------------------------------------------
# Validation
# ---------------------------------------------------------------------------

async def test_invalid_max_pool_size_raises():
    with pytest.raises(ValueError):
        ContainerPool(
            AsyncMock(),
            max_pool_size=0,
            acquire_timeout=10.0,
            container_name="x",
        )

    with pytest.raises(ValueError):
        ContainerPool(
            AsyncMock(),
            max_pool_size=51,
            acquire_timeout=10.0,
            container_name="x",
        )


async def test_invalid_acquire_timeout_raises():
    with pytest.raises(ValueError):
        ContainerPool(
            AsyncMock(),
            max_pool_size=5,
            acquire_timeout=0,
            container_name="x",
        )
