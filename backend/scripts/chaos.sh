#!/usr/bin/env bash
# Demo-day fallback drill. Walks each failure mode and confirms the user-visible
# story still completes. Run once at hour ~18 before the dress rehearsal.
#
# Each scenario is a separate process group so you can read the bridge log
# between runs. None of these reach the network beyond what is needed.
set -u

ROOT="$(cd "$(dirname "$0")/../.." && pwd)"
cd "$ROOT"

bridge_url=${BRIDGE_URL:-http://localhost:3001}
py_url=${PY_URL:-http://localhost:7777}

say() { printf "\n\033[1;36m=== %s ===\033[0m\n" "$*"; }
ok()  { printf "\033[1;32m✓\033[0m %s\n" "$*"; }
bad() { printf "\033[1;31m✗\033[0m %s\n" "$*"; }

require() {
  if ! curl -fsS "$1" >/dev/null 2>&1; then
    bad "$2 not reachable at $1 — start the demo before running chaos"
    exit 1
  fi
}

say "preflight: bridge + python alive?"
require "$bridge_url/health" "bridge"
require "$py_url/health"     "python orchestrator"
ok "both services up"

# ── 1. TTS fallback ──────────────────────────────────────────────────────────
say "1) TTS fallback — temporarily clobber ELEVENLABS_API_KEY and run a turn"
echo "  Action: in another terminal, restart the bridge with ELEVENLABS_API_KEY=BAD"
echo "         then trigger a /turn here. Listen for the OpenAI fallback voice."
echo "  Expect: bridge log line '[tts] elevenlabs failed (...) — engaging openai fallback'"
echo "  Expect: socket emits tts:fallback-engaged; voice still plays."
read -r -p "  press enter when you have observed the fallback (or 's' to skip) " ans
[[ "$ans" == "s" ]] && bad "skipped" || ok "tts fallback drill done"

# ── 2. Stagehand graceful failure ───────────────────────────────────────────
say "2) Browser failure — force a stagehand miss and confirm graceful response"
echo "  Action: ask Sage for an absurdly specific item that won't match, e.g."
echo "          'order me a left-handed walrus polishing kit'."
echo "  Expect: responder emits the fixed graceful line:"
echo "          'I had trouble finding that on Amazon just now. I can save it"
echo "           to your list and try again later. Is that okay?'"
echo "  Expect: orb does not get stuck on 'thinking'; cycles to speaking → complete."
read -r -p "  press enter when you have observed the graceful path (or 's' to skip) " ans
[[ "$ans" == "s" ]] && bad "skipped" || ok "browser graceful drill done"

# ── 3. Snowflake write retry + disk backup ──────────────────────────────────
say "3) Snowflake outage — force write_session to fail and check JSON backup"
echo "  Action: in the python orchestrator's env set SNOWFLAKE_PASSWORD=BAD,"
echo "          restart, then end a session via the Electron client."
echo "  Expect: log line '[sage.snowflake_io] snowflake.write_session attempt 1/2 failed'"
echo "         followed by 'snowflake.write_session — wrote disk backup: out/failed-writes/...'"
echo "  Expect: bridge does not crash. Restart with the real password to resume."
read -r -p "  press enter when you see the JSON in out/failed-writes (or 's' to skip) " ans
[[ "$ans" == "s" ]] && bad "skipped" || ok "snowflake backup drill done"

say "all chaos drills exercised"
