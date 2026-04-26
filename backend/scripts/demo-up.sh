#!/usr/bin/env bash
# Bring both Sage backend processes up for the demo.
#
# Order matters: Python first (Stagehand prewarm in the bridge will try to
# call /internal/* — none of which exist on Python — but the bridge does
# also call the orchestrator on every utterance, so we want it up first).
#
# Logs are tailed into out/demo.log so a single tail -f tells you everything.
# Exits non-zero if either side fails to come healthy in 10s.
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

mkdir -p out
LOG="$ROOT/out/demo.log"
PIDS="$ROOT/out/demo.pids"
: > "$LOG"
: > "$PIDS"

say() { printf "\033[1;36m›\033[0m %s\n" "$*"; }
ok()  { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
bad() { printf "\033[1;31m✗\033[0m %s\n" "$*" >&2; }

stop_all() {
  while read -r pid; do
    [ -n "$pid" ] && kill "$pid" 2>/dev/null || true
  done < "$PIDS"
}
trap 'stop_all' EXIT

# ── start python orchestrator ───────────────────────────────────────────────
say "starting python orchestrator on :7777"
( python -m uvicorn sage.app:app --app-dir backend/py/src --port 7777 \
    >>"$LOG" 2>&1 & echo $! >> "$PIDS" ) || { bad "python failed to spawn"; exit 1; }

# ── start node bridge ───────────────────────────────────────────────────────
say "starting node bridge on :3001 (STAGEHAND_ENV=${STAGEHAND_ENV:-LOCAL})"
( STAGEHAND_ENV="${STAGEHAND_ENV:-LOCAL}" node backend/node/src/bridge.js \
    >>"$LOG" 2>&1 & echo $! >> "$PIDS" ) || { bad "node failed to spawn"; exit 1; }

# ── wait for health ─────────────────────────────────────────────────────────
wait_for() {
  local url="$1" name="$2" tries=20
  while ((tries > 0)); do
    if curl -fsS "$url" >/dev/null 2>&1; then
      ok "$name healthy"
      return 0
    fi
    sleep 0.5
    tries=$((tries - 1))
  done
  bad "$name never came healthy at $url — see $LOG"
  return 1
}

wait_for "http://localhost:7777/health" "python" || exit 1
wait_for "http://localhost:3001/health" "bridge" || exit 1

# Stop trapping so processes survive after this script exits.
trap - EXIT

cat <<EOF

both up. logs: tail -f "$LOG"
to stop:        bash backend/scripts/demo-down.sh

EOF
