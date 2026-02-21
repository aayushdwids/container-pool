"""
Tests for OpenAIContainerBackend.

All OpenAI API calls are mocked — no real network calls are made.
"""
import pytest
from unittest.mock import AsyncMock, MagicMock, patch, mock_open

import openai

from container_pool.backends.openai import OpenAIContainerBackend
from container_pool._exceptions import (
    ContainerCreationError,
    ContainerExpiredError,
    ContainerFileError,
)
from container_pool._types import ContainerStatus


@pytest.fixture
def mock_client():
    client = AsyncMock()
    # Nest containers and files as regular MagicMock so attribute access works
    client.containers = MagicMock()
    client.containers.create = AsyncMock()
    client.containers.retrieve = AsyncMock()
    client.containers.delete = AsyncMock()
    client.containers.files = MagicMock()
    client.containers.files.create = AsyncMock()
    client.containers.files.content = MagicMock()
    client.containers.files.content.retrieve = AsyncMock()
    client.containers.files.delete = AsyncMock()
    client.containers.files.list = AsyncMock()
    return client


@pytest.fixture
def backend(mock_client):
    return OpenAIContainerBackend(mock_client)


# ---------------------------------------------------------------------------
# create_container
# ---------------------------------------------------------------------------

async def test_create_container_returns_container_info(backend, mock_client):
    mock_client.containers.create.return_value = MagicMock(id="ctr-new", status="active")
    info = await backend.create_container("mypool")
    assert info.container_id == "ctr-new"
    assert info.status == ContainerStatus.ACTIVE


async def test_create_container_raises_creation_error_on_api_error(backend, mock_client):
    mock_client.containers.create.side_effect = openai.APIError(
        "bad request", request=MagicMock(), body=None
    )
    with pytest.raises(ContainerCreationError):
        await backend.create_container("mypool")


# ---------------------------------------------------------------------------
# get_container
# ---------------------------------------------------------------------------

async def test_get_container_returns_active_info(backend, mock_client):
    mock_client.containers.retrieve.return_value = MagicMock(id="ctr-1", status="active")
    info = await backend.get_container("ctr-1")
    assert info.status == ContainerStatus.ACTIVE


async def test_get_container_raises_expired_on_404(backend, mock_client):
    mock_client.containers.retrieve.side_effect = openai.NotFoundError(
        "not found", response=MagicMock(status_code=404), body=None
    )
    with pytest.raises(ContainerExpiredError):
        await backend.get_container("ctr-gone")


async def test_get_container_raises_expired_on_expired_status(backend, mock_client):
    mock_client.containers.retrieve.return_value = MagicMock(id="ctr-1", status="expired")
    with pytest.raises(ContainerExpiredError):
        await backend.get_container("ctr-1")


# ---------------------------------------------------------------------------
# destroy_container
# ---------------------------------------------------------------------------

async def test_destroy_container_swallows_404(backend, mock_client):
    mock_client.containers.delete.side_effect = openai.NotFoundError(
        "not found", response=MagicMock(status_code=404), body=None
    )
    # Should not raise
    await backend.destroy_container("ctr-gone")


# ---------------------------------------------------------------------------
# delete_file
# ---------------------------------------------------------------------------

async def test_delete_file_swallows_404(backend, mock_client):
    mock_client.containers.files.delete.side_effect = openai.NotFoundError(
        "not found", response=MagicMock(status_code=404), body=None
    )
    await backend.delete_file("ctr-1", "file-gone")  # no raise


# ---------------------------------------------------------------------------
# list_files
# ---------------------------------------------------------------------------

async def test_list_files_filters_by_prefix(backend, mock_client):
    mock_client.containers.files.list.return_value = MagicMock(
        data=[
            MagicMock(path="/mnt/data/out.csv", id="f-1"),
            MagicMock(path="/tmp/input.csv", id="f-2"),
        ]
    )
    result = await backend.list_files("ctr-1", path_prefix="/mnt/data/")
    assert result == {"out.csv": "f-1"}


async def test_list_files_no_prefix_returns_all(backend, mock_client):
    mock_client.containers.files.list.return_value = MagicMock(
        data=[
            MagicMock(path="/mnt/data/out.csv", id="f-1"),
            MagicMock(path="/tmp/input.csv", id="f-2"),
        ]
    )
    result = await backend.list_files("ctr-1")
    assert len(result) == 2


async def test_list_files_raises_file_error_on_exception(backend, mock_client):
    mock_client.containers.files.list.side_effect = Exception("network error")
    with pytest.raises(ContainerFileError):
        await backend.list_files("ctr-1")


# ---------------------------------------------------------------------------
# upload_file
# ---------------------------------------------------------------------------

async def test_upload_file_returns_uploaded_file(backend, mock_client, tmp_path):
    test_file = tmp_path / "data.csv"
    test_file.write_text("a,b\n1,2")
    mock_client.containers.files.create.return_value = MagicMock(
        id="file-99", path="/mnt/data/data.csv"
    )
    result = await backend.upload_file("ctr-1", str(test_file))
    assert result.file_id == "file-99"
    assert result.container_path == "/mnt/data/data.csv"
    assert result.container_id == "ctr-1"


async def test_upload_file_raises_file_not_found(backend, mock_client):
    with pytest.raises(FileNotFoundError):
        await backend.upload_file("ctr-1", "/nonexistent/file.csv")


# ---------------------------------------------------------------------------
# download_file_content
# ---------------------------------------------------------------------------

async def test_download_file_content_returns_bytes(backend, mock_client):
    mock_client.containers.files.content.retrieve.return_value = MagicMock(
        content=b"hello world"
    )
    data = await backend.download_file_content("ctr-1", "file-1")
    assert data == b"hello world"


async def test_download_file_content_raises_file_error(backend, mock_client):
    mock_client.containers.files.content.retrieve.side_effect = Exception("timeout")
    with pytest.raises(ContainerFileError):
        await backend.download_file_content("ctr-1", "file-1")
