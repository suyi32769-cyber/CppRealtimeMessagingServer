# On-device acceptance evidence — 2026-11-23

The original WSL2 environment used GCC 15.2.0, CMake 4.2.3, Redis 8.0.5 and SQLite 3.46.1. The cloud Ubuntu environment and separate test results are recorded in [server-validation.md](server-validation.md). The fixed source builds Hiredis 1.6.0 from its pinned source. In the cloud isolation directory, the revised build passed 14 CTest cases: `100% tests passed, 0 tests failed out of 14` in 53.25 seconds. Run `cmake --build build -j2` followed by `ctest --test-dir build --output-on-failure` to reproduce; test ports are listed in [deployment.md](deployment.md).

| Requested acceptance item | Observed evidence |
| --- | --- |
| Ubuntu source build | CMake configure/build succeeded on WSL; pinned dependency bootstrap and independent build also succeeded. |
| Start one WebSocket service | `phase1_smoke` receives HTTP 101 and JSON pong from a temporary instance. |
| Clients join and exchange messages | `phase2_rooms` verifies authenticated two-way room broadcast and leaving. |
| Persist actual messages | `phase2_rooms` writes and reads messages through the real server; repository tests verify rows. |
| History after restart | `phase2_rooms` stops and restarts the server with the same DB and reads earlier messages and ACK offset. |
| Two real processes | `phase4_multi_instance` launches two independent executable processes with a shared SQLite file. |
| Cross-instance Redis messages on 9001/9002 | `phase4_multi_instance` verifies both directions on isolated test ports. Separately `scripts/check-demo.py` passed against the actual deployed 9001/9002 listeners and recorded an ACK. |
| Offline catch-up | `phase4_multi_instance` disconnects B, sends via A, reconnects B, repeats history, and advances its ACK. |
| Invalid JSON does not crash | `robustness` sends malformed JSON then successfully continues; `Protocol` tests include numeric overflow and field bounds. |
| Redis failure/recovery | `phase4_multi_instance` stops/restarts a disposable Redis, checks history during the outage, waits for two renewed subscriptions and verifies resumed delivery. |
| Basic automated tests | 14 CTest cases cover repository, schema migration, event deduplication, protocol, single/two-instance workflows, failure handling, startup, heartbeat and backpressure. |
| Ubuntu deployment instructions | README, pinned bootstrap script and [deployment.md](deployment.md); fresh dependency build was tested locally, not on another physical machine. |

Additional real test observations: heartbeat test closed a non-pong client after 31.90 seconds while a client answering ping remained connected; backpressure test closed a stopped reader after 625 4-KiB broadcasts and a healthy client stayed responsive. These are one-run observations, not fixed timing guarantees. See [performance.md](performance.md) for the separate short concurrency probe, its tmpfs storage and the failed earlier 9p run.

This evidence is limited to the tested single-host demonstration. Static demo tokens, no TLS or authorization policy, non-atomic SQLite/Redis publication, no durable Redis queue and prefix ACK cursors rule out claims of production security, high availability or end-to-end exactly-once delivery. A local Git repository exists; no GitHub upload was performed.
