# CppRealtimeMessagingServer — multi-instance prototype

This is a local single-host, two-process messaging demonstration. It supports WebSocket rooms, SQLite-backed messages, history and acknowledgements, and Redis Pub/Sub forwarding. It is not a production-ready high-availability system. Demo credentials and unencrypted local traffic are unsuitable for untrusted networks.

Tested on WSL2 Ubuntu, GCC 15.2, CMake 4.2, system SQLite 3.46.1 and Redis 8.0.5. The project uses C++17. SQLiteCpp requires SQLite 3.38 or newer and is built against system SQLite; Hiredis is built from the pinned source (version 1.6.0). A system SQLite package older than the stated minimum must be upgraded through that system's supported packages before building. See [LICENSES.md](LICENSES.md) for revision pins and license information. Other package versions have not yet been validated.

On Ubuntu install the prerequisites with appropriate administrator approval: `build-essential cmake git pkg-config zlib1g-dev libsqlite3-dev redis-server python3`. This changes system packages. Fetch pinned sources into an otherwise empty `third_party` directory with `bash scripts/fetch-deps.sh`; the script refuses to overwrite existing source directories. A clean dependency download and build was verified on this WSL Ubuntu installation, not on a second machine. Then:

```sh
cmake -S . -B build -DCMAKE_BUILD_TYPE=Debug
cmake --build build -j2
python3 tests/run_phase1.py
python3 tests/phase2.py
ctest --test-dir build --output-on-failure
./build/realtime_server --db /path/to/messages.db
```

To run two instances using an already running local Redis, use the same local database file in both terminals:

```sh
./build/realtime_server --port 9001 --instance-id A --db /path/to/messages.db --redis-host 127.0.0.1 --redis-port 6379
./build/realtime_server --port 9002 --instance-id B --db /path/to/messages.db --redis-host 127.0.0.1 --redis-port 6379
```

Instance IDs must differ. `--no-redis` disables forwarding for standalone tests. Redis server availability can be checked with `redis-cli ping`; its management is separate from the application. Both services bind to 127.0.0.1. The demo tokens and JSON commands are documented in [the protocol](docs/phase2.md).

The automated tests start disposable servers on separate loopback ports, including Redis on 16379, and terminate their processes afterward; the specified test ports must be free. The standalone server listens on 127.0.0.1:9001 and defaults to `messages.db` in its current directory if `--db` is omitted. Use Ctrl+C to stop it. Prefer a local Linux filesystem for SQLite, and do not use a network share. Demo credentials are not production security.

The integration tests verify two-way room messaging, deduplication, ACK and history after restart, cross-process Redis delivery, Redis outage and resubscription, client offline recovery, idle heartbeat and slow-client backpressure. GoogleTest exercises the repository. These tests do not establish exactly-once delivery. See [phase-1 record](docs/phase1.md) and [current protocol](docs/phase2.md).

The measured small-scale concurrency probe and its limitations are documented in [performance.md](docs/performance.md). SIGINT and SIGTERM close the server's sockets on the event-loop thread and join the background workers; live events not published during shutdown remain retrievable from SQLite history. The initial on-device background deployment and how to restart it are documented in [deployment.md](docs/deployment.md).

The [architecture](docs/architecture.md), [deployment guide](docs/deployment.md), [acceptance evidence](docs/acceptance.md) and [résumé and interview notes](docs/resume-interview.md) describe the implemented scope and its boundaries.
