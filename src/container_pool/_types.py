from __future__ import annotations

from dataclasses import dataclass, field
from enum import StrEnum
from typing import Any


class ContainerStatus(StrEnum):
    ACTIVE = "active"
    EXPIRED = "expired"
    UNKNOWN = "unknown"


@dataclass(frozen=True)
class ContainerInfo:
    """
    Vendor-neutral snapshot of a container's identity and status.
    Backends return this; the pool never touches raw vendor objects.
    """

    container_id: str
    status: ContainerStatus
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class UploadedFile:
    """
    Returned by backend.upload_file(). Carries all three identifiers
    the caller needs: the container it belongs to, the remote file id,
    and the path the runtime sees it at.
    """

    container_id: str
    file_id: str
    container_path: str
