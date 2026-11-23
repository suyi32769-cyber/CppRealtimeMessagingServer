#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
if [[ $# != 1 || "$1" != /* ]]; then echo 'Usage: bash scripts/deploy-local.sh /absolute/new-data-directory' >&2; exit 2; fi
data=$1
if [[ -e "$data" ]]; then echo "Refusing to overwrite existing path: $data" >&2; exit 1; fi
if ss -H -ltn | awk '{print $4}' | grep -Eq ':(9001|9002)$'; then echo 'Port 9001 or 9002 is already in use.' >&2; exit 1; fi
redis-cli -h 127.0.0.1 -p 6379 ping | grep -qx PONG || { echo 'Local Redis is unavailable.' >&2; exit 1; }
mkdir -- "$data"
first=''; second=''; success=0
cleanup() {
    if [[ $success != 1 ]]; then
        [[ -n "$first" ]] && kill "$first" 2>/dev/null || true
        [[ -n "$second" ]] && kill "$second" 2>/dev/null || true
        echo "Deployment failed; inspect $data for logs." >&2
    fi
}
trap cleanup EXIT
nohup ./build/realtime_server --port 9001 --instance-id A --db "$data/messages.db" >"$data/A.log" 2>&1 </dev/null &
first=$!
nohup ./build/realtime_server --port 9002 --instance-id B --db "$data/messages.db" >"$data/B.log" 2>&1 </dev/null &
second=$!
for ((i=0; i<50; i++)); do
    kill -0 "$first" 2>/dev/null && kill -0 "$second" 2>/dev/null || break
    if grep -q 'Listening on 127.0.0.1:9001' "$data/A.log" && grep -q 'Listening on 127.0.0.1:9002' "$data/B.log"; then
        printf '%s\n' "$first" >"$data/A.pid"
        printf '%s\n' "$second" >"$data/B.pid"
        success=1
        echo "Started A=$first B=$second data=$data"
        exit 0
    fi
    sleep .2
done
exit 1
