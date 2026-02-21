import pytest
from unittest.mock import AsyncMock

from container_pool import Container, BaseContainerBackend
from container_pool._types import UploadedFile


@pytest.fixture
def backend():
    b = AsyncMock(spec=BaseContainerBackend)
    b.delete_file.return_value = None
    return b


@pytest.fixture
def container(backend):
    return Container(container_id="ctr-abc", backend=backend)


async def test_upload_file_delegates_to_backend(container, backend):
    backend.upload_file.return_value = UploadedFile(
        container_id="ctr-abc", file_id="file-1", container_path="/mnt/data/f.csv"
    )
    result = await container.upload_file("/tmp/f.csv")
    backend.upload_file.assert_awaited_once_with("ctr-abc", "/tmp/f.csv")
    assert result.file_id == "file-1"


async def test_download_file_content_delegates(container, backend):
    backend.download_file_content.return_value = b"hello"
    data = await container.download_file_content("file-1")
    assert data == b"hello"
    backend.download_file_content.assert_awaited_once_with("ctr-abc", "file-1")


async def test_delete_files_continues_on_error(container, backend):
    """delete_files should not raise even if one delete fails."""
    backend.delete_file.side_effect = [Exception("boom"), None]
    # Should not raise
    await container.delete_files(["file-1", "file-2"])
    assert backend.delete_file.await_count == 2


async def test_list_output_files_delegates(container, backend):
    backend.list_files.return_value = {"out.csv": "file-99"}
    result = await container.list_output_files("/mnt/data/")
    backend.list_files.assert_awaited_once_with("ctr-abc", "/mnt/data/")
    assert result == {"out.csv": "file-99"}


async def test_download_files_returns_local_paths(container, backend, tmp_path):
    backend.download_file_to_disk.return_value = 42
    result = await container.download_files(
        {"out.csv": "file-1"}, str(tmp_path)
    )
    assert result == {"out.csv": str(tmp_path / "out.csv")}


def test_repr(container):
    assert "ctr-abc" in repr(container)
