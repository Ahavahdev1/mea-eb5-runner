#!/usr/bin/env bash
set -euo pipefail

case "${BENCHMARK_TIMEOUT:-}" in (*[!0-9]*|'') echo "invalid timeout"; exit 2;; esac
case "${BENCHMARK_SEED:-}" in (*[!0-9]*|'') echo "invalid seed"; exit 2;; esac

args=(
  --challenge "$BENCHMARK_CHALLENGE"
  --adapter "$BENCHMARK_ADAPTER"
  --seeds 1
  --seed-start "$BENCHMARK_SEED"
  --timeout "$BENCHMARK_TIMEOUT"
  --runs-dir runs
  --attempt-only
)
if [ "$BENCHMARK_ADAPTER" = "cli" ]; then
  test -f "$BENCHMARK_ADAPTER_CONFIG"
  args+=(--adapter-config "$BENCHMARK_ADAPTER_CONFIG")
fi
python -m mea_eb5.cli run "${args[@]}"

run_dir=$(find runs -mindepth 1 -maxdepth 1 -type d | head -n 1)
test -n "$run_dir"
archive="attempt-${BENCHMARK_CHALLENGE}-seed-${BENCHMARK_SEED}.tar.gz"
COPYFILE_DISABLE=1 tar -czf "$archive" -C runs "$(basename "$run_dir")"
shasum -a 256 "$archive" > "$archive.sha256"
