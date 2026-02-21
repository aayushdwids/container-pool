import pytest
from unittest.mock import AsyncMock

from container_pool import BaseContainerBackend, ContainerInfo, ContainerStatus, ContainerPool


@pytest.fixture
def mock_backend():
    """
    Fully-mocked backend. Default behaviour: create succeeds, get returns ACTIVE.
    Individual tests override methods as needed.
    """
    backend = AsyncMock(spec=BaseContainerBackend)
    backend.create_container.return_value = ContainerInfo(
        container_id="ctr-001",
        status=ContainerStatus.ACTIVE,
    )
    backend.get_container.return_value = ContainerInfo(
        container_id="ctr-001",
        status=ContainerStatus.ACTIVE,
    )
    backend.destroy_container.return_value = None
    backend.delete_file.return_value = None
    return backend


@pytest.fixture
def pool_factory(mock_backend):
    """Returns a factory for ContainerPool instances using the mock backend."""

    def make(
        max_pool_size: int = 2,
        acquire_timeout: float = 2.0,
        name: str = "test",
    ) -> ContainerPool:
        return ContainerPool(
            mock_backend,
            max_pool_size=max_pool_size,
            acquire_timeout=acquire_timeout,
            container_name=name,
        )

    return make
