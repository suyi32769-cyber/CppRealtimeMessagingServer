#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# -ne 1 || "$1" != /* ]]; then
    echo "Usage: bash scripts/run-demo.sh /absolute/path/to/messages.db" >&2
    exit 2
fi
db=$1
redis_port=${REDIS_PORT:-6379}
if [[ ! -d "$(dirname "$db")" ]]; then echo 'Database parent directory must exist.' >&2; exit 2; fi
redis-cli -h 127.0.0.1 -p "$redis_port" ping | grep -qx PONG || { echo 'Local Redis is not ready.' >&2; exit 1; }
./build/realtime_server --port 9001 --instance-id A --db "$db" --redis-port "$redis_port" &
first=$!
./build/realtime_server --port 9002 --instance-id B --db "$db" --redis-port "$redis_port" &
second=$!
cleanup() {
    trap - EXIT INT TERM
    kill "$first" "$second" 2>/dev/null || true
    wait "$first" 2>/dev/null || true
    wait "$second" 2>/dev/null || true
}
trap cleanup EXIT INT TERM
set +e
wait -n "$first" "$second"
result=$?
set -e
exit "$result"
