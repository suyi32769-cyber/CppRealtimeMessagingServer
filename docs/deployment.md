# Local Ubuntu deployment

Install the packages listed in the README with the machine owner's approval. Clone or copy the project, run `bash scripts/fetch-deps.sh` in an empty dependency directory, then configure and build as in the README. The source bootstrap is pinned by commit; system package versions are not pinned. Never store the SQLite file on a network share. A Linux-local filesystem is recommended, and the parent directory must already exist.

Check an already-running local Redis with `redis-cli ping`. With an absolute database path, start both foreground services together:

```sh
bash scripts/run-demo.sh /absolute/existing-directory/messages.db
```

The script listens only on 127.0.0.1:9001/9002 and uses the existing local Redis at 6379. Ctrl+C ends both processes; SIGINT/SIGTERM requests socket closure on the event loop, and background workers are joined. If Redis fails, a committed message may miss live cross-instance delivery; recover it with history. For protocol examples and demo-only tokens see [phase2.md](phase2.md).

Run `ctest --test-dir build --output-on-failure`. Tests use temporary databases and Redis ports, and require unused 9001, 9002, 16379 and 19003. The benchmark additionally uses 16380, 19001 and 19002. See [performance.md](performance.md); it does not predict production capacity.

On the original device, the initial background deployment was created with `scripts/deploy-local.sh` at `/root/CppRealtimeMessagingServer-data` because root is the current default WSL user. The directory contains `messages.db`, `A.log`, `B.log` and PID files. The helper refuses to use an existing data directory, and it does not install automatic startup. After WSL stops or Windows restarts, start the services with `bash scripts/run-demo.sh /root/CppRealtimeMessagingServer-data/messages.db` from a WSL terminal. `python3 scripts/check-demo.py` checks both running services and writes one real test message and ACK to a fresh room. Before stopping background processes using their PID files, verify the process command lines, since PIDs can be reused. Do not delete the data directory unless its contents are no longer needed.
