from __future__ import annotations

import logging
import os

from ._backend import BaseContainerBackend
from ._types import UploadedFile

log = logging.getLogger(__name__)


class Container:
    """
    A live handle to a single container slot.

    Returned by ContainerPool.acquire(). Callers use this object to
    upload/download files. They must call pool.release(container) when done.

    Container does not manage expiry or recreation — that is the pool's job.
    Container does not hold a reference to the pool.
    """

    def __init__(self, container_id: str, backend: BaseContainerBackend) -> None:
        self.container_id = container_id
        self._backend = backend

    # -------------------------------------------------------------------------
    # File operations — thin delegation to backend
    # -------------------------------------------------------------------------

    async def upload_file(self, local_path: str) -> UploadedFile:
        return await self._backend.upload_file(self.container_id, local_path)

    async def download_file_content(self, file_id: str) -> bytes:
        return await self._backend.download_file_content(self.container_id, file_id)

    async def download_file_to_disk(self, file_id: str, local_path: str) -> int:
        return await self._backend.download_file_to_disk(
            self.container_id, file_id, local_path
        )

    async def delete_file(self, file_id: str) -> None:
        await self._backend.delete_file(self.container_id, file_id)

    async def delete_files(self, file_ids: list[str]) -> None:
        """Best-effort bulk delete. Logs and continues on individual failures."""
        for fid in file_ids:
            try:
                await self._backend.delete_file(self.container_id, fid)
            except Exception:
                log.warning(
                    "Failed to delete file %r from container %r",
                    fid,
                    self.container_id,
                    exc_info=True,
                )

    async def list_output_files(self, path_prefix: str = "") -> dict[str, str]:
        """List files in the container, optionally filtered by path prefix."""
        return await self._backend.list_files(self.container_id, path_prefix)

    async def download_files(
        self,
        file_ids: dict[str, str],
        output_dir: str,
    ) -> dict[str, str]:
        """
        Download multiple files to a local directory.

        Args:
            file_ids: {filename: file_id}
            output_dir: Local directory to save files into

        Returns:
            {filename: local_path}
        """
        results: dict[str, str] = {}
        for filename, file_id in file_ids.items():
            local_path = os.path.join(output_dir, filename)
            await self._backend.download_file_to_disk(
                self.container_id, file_id, local_path
            )
            results[filename] = local_path
        return results

    def __repr__(self) -> str:
        return f"Container(id={self.container_id!r})"
