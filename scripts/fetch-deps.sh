#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/.."
fetch() {
  local dir=$1 url=$2 revision=$3
  if [[ -e "$dir" ]]; then
    echo "Refusing to overwrite $dir; inspect or move it first." >&2
    return 1
  fi
  git init -q "$dir"
  git -C "$dir" remote add origin "$url"
  git -C "$dir" fetch --depth 1 origin "$revision"
  git -C "$dir" checkout --detach FETCH_HEAD
  test "$(git -C "$dir" rev-parse HEAD)" = "$revision"
}
mkdir -p third_party
fetch third_party/uWebSockets https://github.com/uNetworking/uWebSockets.git 05e6c8b55b4d28293cf23570f0f61318f8600560
git -C third_party/uWebSockets submodule update --init uSockets
test "$(git -C third_party/uWebSockets/uSockets rev-parse HEAD)" = 86097c490263ab662d62e8e7b541390bdec7d149
fetch third_party/SQLiteCpp https://github.com/SRombauts/SQLiteCpp.git 7302cd30b853e2d3d4f2ae1456b01180d068681e
fetch third_party/json https://github.com/nlohmann/json.git 55f93686c01528224f448c19128836e7df245f72
fetch third_party/hiredis https://github.com/redis/hiredis.git 6e0d55b3ff42a4801d756f6ebdceee21019c1e86
fetch third_party/googletest https://github.com/google/googletest.git a46a6012a133c7c0929fdae55b321c2fe65f3c5f
