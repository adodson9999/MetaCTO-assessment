#!/usr/bin/env bash
# Phase 4 — IP-allowlist-enforcement task: run the four agents against the LOCAL
# ip-allowlist-gateway, score fidelity vs gold, update the leaderboard. Re-runnable; each
# run appends to the leaderboard. DummyJSON is NEVER used or modified — the target is the
# local gateway only. Backend = claude-haiku (per the task's config.toml), so this build
# is NOT air-gapped: it requires ANTHROPIC_API_KEY. Memory (EverOS) is started best-effort
# and is non-fatal.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GW_PORT="${FORGE_GATEWAY_PORT:-8913}"
BASE="http://127.0.0.1:${GW_PORT}"
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# 0. Backend precondition (provider-aware; mirrors the other phase4 scripts).
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 || {
    echo "FATAL: ollama backend selected but the Ollama server is not running on :11434." >&2
    echo "       Start it yourself: 'ollama serve' (this script does not start it)." >&2; exit 3; }
elif [ "$FORGE_PROVIDER" = "claude-haiku" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "FATAL: ANTHROPIC_API_KEY is not set, but FORGE_PROVIDER=claude-haiku."; exit 3
fi

# 1. EverOS shared-memory pool up (loopback, best-effort — note-writing is non-fatal)
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000 (best-effort)"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 15); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Local IP-allowlist gateway up (the SUT). Only started if not already running.
STARTED_GW=0
if ! curl -fsS "$BASE/__health" >/dev/null 2>&1; then
  say "starting ip-allowlist-gateway on :$GW_PORT (local SUT)"
  ( python tools/ip-allowlist-gateway/gateway.py --host 127.0.0.1 --port "$GW_PORT" \
      >/tmp/ip-allowlist-gateway.log 2>&1 ) &
  GWPID=$!; STARTED_GW=1
  for i in $(seq 1 20); do curl -fsS "$BASE/__health" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/__health" >/dev/null 2>&1 || { echo "FATAL: gateway not up"; exit 2; }

# 2b. Refresh gold from the live gateway so fidelity scores against current truth
say "building gold (local gateway, real requests + allowlist management)"
BASE_URL="$BASE" python data/test-ip-allowlist-enforcement/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel
say "running four IP-allowlist agents (parallel)"
python scripts/run_ip_allowlist_agents__test-ip-allowlist-enforcement.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/test-ip-allowlist-enforcement/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-ip-allowlist-enforcement/metric.json \
  --out-prefix results/leaderboard-test-ip-allowlist-enforcement

# 5. Stop only what we started
[ "$STARTED_GW" = "1" ] && { kill ${GWPID:-0} 2>/dev/null; sleep 1; kill -9 ${GWPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
