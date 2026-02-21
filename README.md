# container-pool

Production-grade async container pool for Python. Handles container lifecycle, reuse, concurrency, and automatic recovery from expiry — so you don't have to.

Built for OpenAI's Code Interpreter, but designed to work with **any sandboxed container runtime** via a pluggable backend interface.

## The Problem

When running sandboxed containers behind a multi-user backend, you hit problems no provider solves for you:

- **Containers expire silently** after 20 minutes of inactivity. Your next request fails with a 404.
- **No built-in pooling.** Every request creates a new container (~2-3s overhead).
- **No concurrency management.** Two users hitting your API simultaneously? You're on your own.
- **File cleanup is your problem.** Leaked files accumulate and you eat the storage cost.

`container-pool` is the infrastructure layer that handles all of this.

## What This Does

```
Request A ──→ acquire() ──→ [Container 1] ──→ release() ──→ back to pool
Request B ──→ acquire() ──→ [Container 2] ──→ release() ──→ back to pool
Request C ──→ acquire() ──→ (pool full, blocks until release) ──→ ...
```

- **FIFO pool** with configurable size, blocking acquisition with timeout when exhausted
- **Automatic expiry recovery** — detects expired containers (404, status=expired) and transparently recreates them
- **Per-request file tracking** with cleanup, so containers stay clean between users
- **Retry with exponential backoff** on container creation failures
- **Graceful shutdown** that destroys all containers on exit
- **Provider-agnostic** — implement `BaseContainerBackend` to support any runtime

## Installation

```bash
pip install container-pool            # core only
pip install "container-pool[openai]"  # with OpenAI backend
```

## Usage

```python
from openai import AsyncOpenAI
from container_pool import ContainerPool, RequestFileTracker
from container_pool.backends.openai import OpenAIContainerBackend

client = AsyncOpenAI()
backend = OpenAIContainerBackend(client)

pool = ContainerPool(
    backend,
    max_pool_size=5,
    acquire_timeout=30.0,
    container_name="my-pool",
)

# Acquire, use, release
container = await pool.acquire()
try:
    tracker = RequestFileTracker(container)
    uploaded = await tracker.upload_file("/tmp/data.csv")
    # ... run code interpreter with container.container_id ...
    files = await container.list_output_files("/mnt/data/")
    results = await container.download_files(files, "/tmp/output")
finally:
    await tracker.cleanup()        # delete uploaded files
    await pool.release(container)  # return to pool

# On app shutdown
await pool.shutdown()
```

## Custom Backends

Implement `BaseContainerBackend` to plug in any container runtime:

```python
from container_pool import BaseContainerBackend, ContainerInfo, UploadedFile

class MyBackend(BaseContainerBackend):
    async def create_container(self, name: str) -> ContainerInfo: ...
    async def get_container(self, container_id: str) -> ContainerInfo: ...
    async def destroy_container(self, container_id: str) -> None: ...
    async def upload_file(self, container_id: str, local_path: str) -> UploadedFile: ...
    async def download_file_content(self, container_id: str, file_id: str) -> bytes: ...
    async def download_file_to_disk(self, container_id: str, file_id: str, local_path: str) -> int: ...
    async def delete_file(self, container_id: str, file_id: str) -> None: ...
    async def list_files(self, container_id: str, path_prefix: str = "") -> dict[str, str]: ...
```

## How It Works

### Acquire Flow

```
acquire()
  ├─ Queue has available container? → validate it's alive → return
  ├─ Pool below max size? → create new container → return
  └─ Pool exhausted? → block until someone calls release() (with timeout)
```

### Expiry Recovery

`container-pool` handles silent expiry transparently — callers always get a live container:

```
validate_or_recreate(container)
  ├─ active status → use it
  ├─ expired status → recreate
  ├─ 404 → recreate
  └─ connection error → recreate
```

### Performance

| Operation | Latency |
|---|---|
| Warm acquire | <100ms |
| Cold acquire | ~2-3s (container creation) |
| Pool exhausted | Blocks up to `acquire_timeout` |
| Expiry recovery | ~2-3s (transparent recreation) |

## Configuration

| Parameter | Description |
|---|---|
| `max_pool_size` | Max containers in pool (1–50) |
| `acquire_timeout` | Seconds to wait when pool is exhausted |
| `container_name` | Name prefix for created containers |
| `creation_max_attempts` | Retry attempts on creation failure (default: 3) |
| `creation_base_delay` | Base delay for exponential backoff in seconds (default: 1.0) |

## Roadmap

### v1 (current)
- [x] FIFO pool with `asyncio.Queue`
- [x] Automatic expiry detection and recovery
- [x] Per-request file tracking and cleanup
- [x] Retry with exponential backoff
- [x] Graceful shutdown
- [x] Pluggable backend interface
- [x] OpenAI Code Interpreter backend

### v2
- [ ] **Pool pre-warming** — create containers at startup to eliminate cold-start latency
- [ ] **Background keep-alive** — periodic pings to prevent idle expiry
- [ ] **Distributed state** — Redis/PostgreSQL backend for multi-node deployments
- [ ] **Observability** — metrics for pool utilization, acquire wait times, expiry rate
- [ ] **Pool strategies** — LRU, priority-based in addition to FIFO

## Contributing

Contributions welcome. Please open an issue first to discuss what you'd like to change.

## Why This Exists

Built after hitting every one of these problems while running Code Interpreter in a multi-user production backend. OpenAI's docs hand you a container ID and say good luck — this is the "good luck" part.

— [@aayushgzip](https://github.com/aayushgzip)

## License

[MIT](LICENSE)
