import pytest
from unittest.mock import AsyncMock, patch

from container_pool import Container, RequestFileTracker, BaseContainerBackend
from container_pool._types import UploadedFile


@pytest.fixture
def backend():
    b = AsyncMock(spec=BaseContainerBackend)
    b.delete_file.return_value = None
    return b


@pytest.fixture
def container(backend):
    return Container(container_id="ctr-xyz", backend=backend)


@pytest.fixture
def tracker(container):
    return RequestFileTracker(container)


async def test_upload_tracks_file_id(tracker, backend):
    backend.upload_file.return_value = UploadedFile(
        container_id="ctr-xyz", file_id="f-1", container_path="/mnt/data/f.csv"
    )
    await tracker.upload_file("/tmp/f.csv")
    assert "f-1" in tracker._tracked_file_ids


async def test_cleanup_calls_delete_for_all_tracked(tracker, backend):
    backend.upload_file.side_effect = [
        UploadedFile("ctr-xyz", "f-1", "/mnt/data/a.csv"),
        UploadedFile("ctr-xyz", "f-2", "/mnt/data/b.csv"),
    ]
    await tracker.upload_file("/tmp/a.csv")
    await tracker.upload_file("/tmp/b.csv")

    await tracker.cleanup()

    assert backend.delete_file.await_count == 2
    assert tracker._tracked_file_ids == []


async def test_cleanup_clears_list_even_on_error(tracker, backend):
    backend.upload_file.return_value = UploadedFile("ctr-xyz", "f-1", "/mnt/data/f.csv")
    backend.delete_file.side_effect = Exception("network error")

    await tracker.upload_file("/tmp/f.csv")
    await tracker.cleanup()

    # List must be cleared despite the error
    assert tracker._tracked_file_ids == []


async def test_cleanup_is_idempotent(tracker, backend):
    backend.upload_file.return_value = UploadedFile("ctr-xyz", "f-1", "/mnt/data/f.csv")
    await tracker.upload_file("/tmp/f.csv")

    await tracker.cleanup()
    await tracker.cleanup()  # second call is a no-op

    assert backend.delete_file.await_count == 1


async def test_cleanup_noop_when_no_files(tracker, backend):
    await tracker.cleanup()
    backend.delete_file.assert_not_awaited()


def test_container_property(tracker, container):
    assert tracker.container is container
