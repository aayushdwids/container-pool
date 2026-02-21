from __future__ import annotations

from abc import ABC, abstractmethod

from ._types import ContainerInfo, UploadedFile


class BaseContainerBackend(ABC):
    """
    Abstract interface every backend must implement.

    All methods are async. Implementations are responsible for:
    - Translating vendor-specific errors into ContainerExpiredError /
      ContainerCreationError / ContainerFileError.
    - Never leaking vendor SDK types through return values.
    - Best-effort operations (destroy, delete_file) should swallow 404 silently.
    """

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    @abstractmethod
    async def create_container(self, name: str) -> ContainerInfo:
        """
        Create and activate a new container.
        Raises ContainerCreationError on failure (after any internal retry).
        """

    @abstractmethod
    async def get_container(self, container_id: str) -> ContainerInfo:
        """
        Fetch the current status of an existing container.
        Raises ContainerExpiredError if the container is gone or expired.
        """

    @abstractmethod
    async def destroy_container(self, container_id: str) -> None:
        """
        Permanently destroy a container.
        Best-effort: should swallow 404 silently.
        """

    # -------------------------------------------------------------------------
    # File operations
    # -------------------------------------------------------------------------

    @abstractmethod
    async def upload_file(self, container_id: str, local_path: str) -> UploadedFile:
        """
        Upload a local file into the container.
        Returns an UploadedFile with container_id, file_id, container_path.
        Raises ContainerFileError on failure.
        """

    @abstractmethod
    async def download_file_content(self, container_id: str, file_id: str) -> bytes:
        """
        Download a file's raw bytes by file_id.
        Raises ContainerFileError on failure.
        """

    @abstractmethod
    async def download_file_to_disk(
        self,
        container_id: str,
        file_id: str,
        local_path: str,
    ) -> int:
        """
        Download a file and write it to local_path.
        Returns the number of bytes written.
        Raises ContainerFileError on failure.
        """

    @abstractmethod
    async def delete_file(self, container_id: str, file_id: str) -> None:
        """
        Delete a single file from the container.
        Best-effort: should swallow 404 silently.
        """

    @abstractmethod
    async def list_files(
        self,
        container_id: str,
        path_prefix: str = "",
    ) -> dict[str, str]:
        """
        List files inside the container whose path starts with path_prefix.
        Returns {filename: file_id}.
        """
