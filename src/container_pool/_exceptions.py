class ContainerPoolError(Exception):
    """Base class for all container-pool errors."""


class ContainerPoolExhaustedError(ContainerPoolError):
    """
    Raised by ContainerPool.acquire() when no container becomes
    available within acquire_timeout seconds.
    """

    def __init__(self, timeout: float, pool_size: int) -> None:
        self.timeout = timeout
        self.pool_size = pool_size
        super().__init__(
            f"No container available after {timeout}s (pool_size={pool_size})"
        )


class ContainerExpiredError(ContainerPoolError):
    """
    Raised by a backend when it detects a container has expired
    (404 or status=expired). The pool catches this and recreates.
    Callers should never see this in normal flow.
    """

    def __init__(self, container_id: str) -> None:
        self.container_id = container_id
        super().__init__(f"Container {container_id!r} has expired or been deleted")


class ContainerCreationError(ContainerPoolError):
    """
    Raised when all retries to create a new container have failed.
    Wraps the last underlying exception.
    """

    def __init__(self, attempts: int, cause: BaseException) -> None:
        self.attempts = attempts
        self.cause = cause
        super().__init__(
            f"Container creation failed after {attempts} attempt(s): {cause}"
        )


class ContainerFileError(ContainerPoolError):
    """Raised when a file upload, download, or delete operation fails."""
