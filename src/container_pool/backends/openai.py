from __future__ import annotations

import os

try:
    import openai as _openai
    from openai import AsyncOpenAI
except ImportError as exc:
    raise ImportError(
        "The OpenAI backend requires the 'openai' package. "
        "Install it with: pip install 'container-pool[openai]'"
    ) from exc

from .._backend import BaseContainerBackend
from .._exceptions import (
    ContainerCreationError,
    ContainerExpiredError,
    ContainerFileError,
)
from .._types import ContainerInfo, ContainerStatus, UploadedFile


class OpenAIContainerBackend(BaseContainerBackend):
    """
    Concrete backend using the OpenAI Code Interpreter Container API.

    Requires openai>=1.0.0 and an AsyncOpenAI client. Install the extra:
        pip install 'container-pool[openai]'

    All vendor-specific errors are translated into ContainerPoolError subclasses.
    The pool and Container classes never see openai SDK types.
    """

    def __init__(self, client: AsyncOpenAI) -> None:
        self._client = client

    # -------------------------------------------------------------------------
    # Lifecycle
    # -------------------------------------------------------------------------

    async def create_container(self, name: str) -> ContainerInfo:
        try:
            result = await self._client.containers.create(name=name)
            return ContainerInfo(
                container_id=result.id,
                status=self._parse_status(result.status),
            )
        except _openai.APIError as exc:
            raise ContainerCreationError(attempts=1, cause=exc) from exc

    async def get_container(self, container_id: str) -> ContainerInfo:
        try:
            result = await self._client.containers.retrieve(container_id)
            status = self._parse_status(result.status)
            if status != ContainerStatus.ACTIVE:
                raise ContainerExpiredError(container_id)
            return ContainerInfo(container_id=result.id, status=status)
        except _openai.NotFoundError as exc:
            raise ContainerExpiredError(container_id) from exc
        except ContainerExpiredError:
            raise
        except _openai.APIConnectionError as exc:
            # Network error — treat as expired so the pool recreates
            raise ContainerExpiredError(container_id) from exc
        except _openai.APIError as exc:
            raise ContainerExpiredError(container_id) from exc

    async def destroy_container(self, container_id: str) -> None:
        try:
            await self._client.containers.delete(container_id)
        except (_openai.NotFoundError, _openai.APIError):
            pass  # best-effort

    # -------------------------------------------------------------------------
    # File operations
    # -------------------------------------------------------------------------

    async def upload_file(self, container_id: str, local_path: str) -> UploadedFile:
        try:
            with open(local_path, "rb") as f:
                result = await self._client.containers.files.create(
                    container_id=container_id,
                    file=f,
                )
            return UploadedFile(
                container_id=container_id,
                file_id=result.id,
                container_path=result.path,
            )
        except FileNotFoundError:
            raise
        except Exception as exc:
            raise ContainerFileError(
                f"Upload failed for {local_path!r}: {exc}"
            ) from exc

    async def download_file_content(self, container_id: str, file_id: str) -> bytes:
        try:
            response = await self._client.containers.files.content.retrieve(
                file_id=file_id,
                container_id=container_id,
            )
            return response.content
        except Exception as exc:
            raise ContainerFileError(
                f"Download failed for file {file_id!r}: {exc}"
            ) from exc

    async def download_file_to_disk(
        self,
        container_id: str,
        file_id: str,
        local_path: str,
    ) -> int:
        content = await self.download_file_content(container_id, file_id)
        os.makedirs(os.path.dirname(local_path) or ".", exist_ok=True)
        with open(local_path, "wb") as f:
            f.write(content)
        return len(content)

    async def delete_file(self, container_id: str, file_id: str) -> None:
        try:
            await self._client.containers.files.delete(
                file_id=file_id,
                container_id=container_id,
            )
        except (_openai.NotFoundError, _openai.APIError):
            pass  # best-effort

    async def list_files(
        self,
        container_id: str,
        path_prefix: str = "",
    ) -> dict[str, str]:
        try:
            response = await self._client.containers.files.list(
                container_id=container_id
            )
            files: dict[str, str] = {}
            for f in response.data:
                if path_prefix and not f.path.startswith(path_prefix):
                    continue
                filename = os.path.basename(f.path)
                files[filename] = f.id
            return files
        except Exception as exc:
            raise ContainerFileError(f"list_files failed: {exc}") from exc

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------

    @staticmethod
    def _parse_status(raw: str) -> ContainerStatus:
        try:
            return ContainerStatus(raw)
        except ValueError:
            return ContainerStatus.UNKNOWN
