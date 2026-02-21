from __future__ import annotations

import logging

from ._container import Container
from ._types import UploadedFile

log = logging.getLogger(__name__)


class RequestFileTracker:
    """
    Wraps a Container for the duration of a single request.

    Tracks every file_id returned by upload_file(). Call cleanup() once the
    request is complete to delete all tracked files. Keeps containers clean
    between users without the caller needing to track individual file ids.

    Usage:
        container = await pool.acquire()
        tracker = RequestFileTracker(container)
        try:
            uploaded = await tracker.upload_file("/tmp/input.csv")
            # ... use container ...
        finally:
            await tracker.cleanup()
            await pool.release(container)
    """

    def __init__(self, container: Container) -> None:
        self._container = container
        self._tracked_file_ids: list[str] = []

    @property
    def container(self) -> Container:
        return self._container

    async def upload_file(self, local_path: str) -> UploadedFile:
        """Upload a file and automatically track its file_id for cleanup."""
        result = await self._container.upload_file(local_path)
        self._tracked_file_ids.append(result.file_id)
        return result

    async def cleanup(self) -> None:
        """
        Delete all tracked files. Best-effort: always clears the tracking
        list even if some deletes fail. Errors are logged, not raised.
        """
        if not self._tracked_file_ids:
            return

        ids_to_delete = list(self._tracked_file_ids)
        self._tracked_file_ids.clear()  # clear before deleting — safe on partial failure

        await self._container.delete_files(ids_to_delete)
        log.debug("RequestFileTracker cleaned up %d file(s).", len(ids_to_delete))
