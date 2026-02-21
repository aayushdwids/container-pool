"""
container-pool: Provider-agnostic async container pool with expiry recovery.

Quick start:
    from container_pool import ContainerPool
    from container_pool.backends.openai import OpenAIContainerBackend

    backend = OpenAIContainerBackend(openai_client)
    pool = ContainerPool(backend, max_pool_size=5, acquire_timeout=30.0, container_name="ci")

    container = await pool.acquire()
    try:
        uploaded = await container.upload_file("/tmp/data.csv")
        ...
    finally:
        await pool.release(container)

    await pool.shutdown()
"""

from ._backend import BaseContainerBackend
from ._container import Container
from ._exceptions import (
    ContainerCreationError,
    ContainerExpiredError,
    ContainerFileError,
    ContainerPoolError,
    ContainerPoolExhaustedError,
)
from ._pool import ContainerPool
from ._tracker import RequestFileTracker
from ._types import ContainerInfo, ContainerStatus, UploadedFile

__all__ = [
    # Core
    "ContainerPool",
    "Container",
    "RequestFileTracker",
    # ABC
    "BaseContainerBackend",
    # Types
    "ContainerInfo",
    "ContainerStatus",
    "UploadedFile",
    # Exceptions
    "ContainerPoolError",
    "ContainerPoolExhaustedError",
    "ContainerExpiredError",
    "ContainerCreationError",
    "ContainerFileError",
]
