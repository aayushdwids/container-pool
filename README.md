# container-pool

Production-grade container pool manager for OpenAI's Code Interpreter API. Handles container lifecycle, reuse, concurrency, and automatic recovery from expiry — so you don't have to.

## The Problem

OpenAI's Code Interpreter gives you two options: `"auto"` (no control) or explicit container management (all the work is on you). For any multi-user system, you immediately hit real problems:

- **Containers expire silently** after 20 minutes of inactivity. Your next request fails with a 404.
- **No built-in pooling.** Every request creates a new container (~2-3s overhead), and you pay for each one.
- **No concurrency management.** Two users hitting your API simultaneously? You're on your own.
- **File cleanup is your problem.** Leaked files in containers accumulate and you eat the storage cost.

If you're running Code Interpreter behind any async Python backend serving multiple users, you need infrastructure that OpenAI doesn't provide. `container-pool` is that infrastructure.

## What This Does

```
Request A ──→ acquire() ──→ [Container 1] ──→ release() ──→ back to pool
Request B ──→ acquire() ──→ [Container 2] ──→ release() ──→ back to pool
Request C ──→ acquire() ──→ (pool full, blocks until release) ──→ ...
```

- **FIFO container pool** with configurable size, blocking acquisition with timeout when exhausted
- **Automatic expiry recovery** — detects expired containers (404, status="expired") and transparently recreates them
- **Per-request file tracking** with cleanup, so containers stay clean between users
- **Retry with exponential backoff** on container creation failures
- **Graceful shutdown** that destroys all containers on app exit

## Quick Start

### Installation

```bash
pip install container-pool  # coming soon
```

### Basic Usage

> 🚧 Coming soon — package is under active development.

### Per-Request File Tracking

`RequestFileTracker` wraps a container and tracks every file you upload. Call `cleanup()` once and it deletes them all — keeps containers clean between users.

> 🚧 Usage examples coming soon.

## How It Works

### Acquire Flow

```
acquire()
  ├─ Queue has available container? → validate it's alive → return
  ├─ Pool below max size? → create new container → return
  └─ Pool exhausted? → block until someone calls release() (with timeout)
```

### Expiry Recovery

OpenAI silently expires containers after 20 min. `container-pool` handles this transparently:

```
validate_or_recreate(container)
  ├─ API returns 200 + status="active" → container is fine, use it
  ├─ API returns 200 + status="expired" → remove from pool, create new one
  ├─ API returns 404 → same, container is gone, create new one
  └─ API connection error → assume dead, create new one
```

The caller never sees an expired container. From their perspective, `acquire()` always returns a working container.

### Performance Characteristics

| Operation | Latency |
|---|---|
| First acquire (cold) | ~2-3s (container creation + API validation) |
| Subsequent acquire (warm) | <100ms (queue retrieval + API validation) |
| Pool exhausted | Blocks up to `acquire_timeout` seconds |
| Expiry recovery | ~2-3s (transparent recreation) |

## Configuration

| Parameter | Default | Description |
|---|---|---|
| `max_pool_size` | — | Maximum containers in pool (1-50) |
| `acquire_timeout` | — | Max seconds to wait when pool is exhausted |
| `container_name` | — | Name prefix for created containers |

## Roadmap

### v1 (current)
- [x] FIFO container pool with `asyncio.Queue`
- [x] Automatic expiry detection and recovery
- [x] Per-request file tracking and cleanup
- [x] Retry with exponential backoff
- [x] Graceful shutdown
- [x] Configurable pool size and acquire timeout

### v2
- [ ] **Distributed pool state** — Redis/PostgreSQL backend for multi-node deployments (current implementation is single-process only)
- [ ] **Pool pre-warming** — `warm(n)` method to create containers at startup, eliminating cold-start latency
- [ ] **Background keep-alive** — periodic pings to prevent idle container expiry
- [ ] **Observability** — metrics for pool utilization, acquire wait times, container churn rate, expiry events
- [ ] **Memory tier mixing** — support pools with mixed container sizes (1g, 4g, 16g, 64g)
- [ ] **Pool strategies** — LRU, priority-based allocation in addition to FIFO
- [ ] **Vendor abstraction** — pluggable backend interface to support other sandboxed runtimes beyond OpenAI

## Contributing

Contributions welcome. Please open an issue first to discuss what you'd like to change.

## Why This Exists

Built this after hitting every one of these problems while running Code Interpreter in a multi-user production backend. OpenAI's docs hand you a container ID and say good luck — this is the "good luck" part.

— [@aayushgzip](https://github.com/aayushgzip)

## License

[MIT](LICENSE)
