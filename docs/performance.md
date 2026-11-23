# Local concurrency probe — 2026-11-23

This is a short development measurement, not a capacity claim. Run `python3 tests/benchmark.py` after building. It starts its own Redis on 16380 and two instances on 19001/19002, then cleans them up.

Environment: WSL2 Ubuntu, Linux 6.18.40.1, AMD Ryzen 7 5800H (16 logical CPUs visible), 7.7 GiB WSL memory, GCC 15.2, Debug build, Redis 8.0.5. The SQLite database was placed on `/tmp`, which `df -T` reported as **tmpfs**, so this run does not measure persistent-disk durability or disk latency. Servers and clients ran on the same host through loopback.

Eight concurrent clients each used a separate room and alternated between the two instances. Every client repeatedly sent a 16-byte content string, waited for its `send_ok` and its own room event, then sent the next message. Latency is the client-observed time from sending to `send_ok`, which includes database commit and local scheduling; it is not cross-instance delivery latency. The result is aggregate committed-message throughput, not connections per second.

| Metric | Observed value |
| --- | ---: |
| Target / actual duration | 5 / 5.003 seconds |
| Successful messages | 20,684 |
| Throughput | 4,134.66 messages/s |
| ACK latency p50 | 0.749 ms |
| ACK latency p95 | 3.851 ms |
| ACK latency p99 | 19.188 ms |
| Client errors | 0 |

An earlier run with the database under `/mnt/f/wp` (reported as 9p) and a 3-second client timeout failed: four clients timed out. The successful run changed both the database location and timeout to 15 seconds, so these results do not isolate the cause. Shared SQLite has one writer at a time; storage latency, contention, different room topology, longer runs and networked clients may produce very different outcomes. Redis outage and recovery were tested separately by `tests/phase4.py`.
