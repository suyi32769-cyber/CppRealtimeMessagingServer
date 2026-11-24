#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
resume=0
if [[ $# == 2 && "$1" == '--resume' ]]; then resume=1; shift; fi
if [[ $# != 1 || "$1" != /* ]]; then echo 'Usage: bash scripts/deploy-local.sh [--resume] /absolute/data-directory' >&2; exit 2; fi
data=$1
if [[ $resume == 1 ]]; then
    [[ -d "$data" && -f "$data/messages.db" ]] || { echo 'Existing data directory and database required.' >&2; exit 1; }
    for name in A B; do
        if [[ -f "$data/$name.pid" ]]; then
            pid=$(cat "$data/$name.pid")
            if [[ "$pid" =~ ^[0-9]+$ && -r "/proc/$pid/cmdline" ]]; then
                command_line=$(tr '\0' ' ' <"/proc/$pid/cmdline")
                if [[ "$command_line" == *realtime_server* && "$command_line" == *"$data/messages.db"* ]]; then
                    echo "Existing server process $pid still running; refusing to start another." >&2
                    exit 1
                fi
            fi
        fi
    done
else
    if [[ -e "$data" ]]; then echo "Refusing to overwrite existing path: $data" >&2; exit 1; fi
fi
if ss -H -ltn | awk '{print $4}' | grep -Eq ':(9001|9002)$'; then echo 'Port 9001 or 9002 is already in use.' >&2; exit 1; fi
redis-cli -h 127.0.0.1 -p 6379 ping | grep -qx PONG || { echo 'Local Redis is unavailable.' >&2; exit 1; }
if [[ $resume == 0 ]]; then mkdir -- "$data"; fi
touch "$data/A.log" "$data/B.log"
start_a=$(($(wc -l <"$data/A.log") + 1))
start_b=$(($(wc -l <"$data/B.log") + 1))
first=''; second=''; success=0
cleanup() {
    if [[ $success != 1 ]]; then
        [[ -n "$first" ]] && kill "$first" 2>/dev/null || true
        [[ -n "$second" ]] && kill "$second" 2>/dev/null || true
        echo "Deployment failed; inspect $data for logs." >&2
    fi
}
trap cleanup EXIT
nohup ./build/realtime_server --port 9001 --instance-id A --db "$data/messages.db" >>"$data/A.log" 2>&1 </dev/null &
first=$!
nohup ./build/realtime_server --port 9002 --instance-id B --db "$data/messages.db" >>"$data/B.log" 2>&1 </dev/null &
second=$!
for ((i=0; i<50; i++)); do
    kill -0 "$first" 2>/dev/null && kill -0 "$second" 2>/dev/null || break
    if tail -n "+$start_a" "$data/A.log" | grep -q 'Listening on 127.0.0.1:9001' && tail -n "+$start_b" "$data/B.log" | grep -q 'Listening on 127.0.0.1:9002'; then
        printf '%s\n' "$first" >"$data/A.pid"
        printf '%s\n' "$second" >"$data/B.pid"
        success=1
        echo "Started A=$first B=$second data=$data"
        exit 0
    fi
    sleep .2
done
exit 1
