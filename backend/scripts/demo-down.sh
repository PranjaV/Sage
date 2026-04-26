#!/usr/bin/env bash
# Stop the bridge + python orchestrator started by demo-up.sh.
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
PIDS="$ROOT/out/demo.pids"

if [ ! -f "$PIDS" ]; then
  echo "no $PIDS — nothing to stop"
  exit 0
fi

while read -r pid; do
  if [ -n "$pid" ] && kill -0 "$pid" 2>/dev/null; then
    echo "stopping pid $pid"
    kill "$pid" 2>/dev/null || true
  fi
done < "$PIDS"

rm -f "$PIDS"
echo "demo-down complete"
