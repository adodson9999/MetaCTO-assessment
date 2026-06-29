#!/usr/bin/env bash
# Phase 4 — null-and-empty-fields task: run the four agents against the local target,
# score fidelity vs gold, update the leaderboard. Self-contained.
#
# BACKEND = OLLAMA (air-gapped local). FORGE_PROVIDER=ollama is exported so every
# agent/judge/evolver uses the local Ollama model. This script does NOT start the
# Ollama server — it must already be running (start it yourself, e.g. `ollama serve`);
# the run aborts with a clear message if it is not reachable. DummyJSON is started
# air-gapped (MONGODB_URI empty) so POST/PUT/PATCH simulate responses and never
# persist; the API source is never modified.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# Ollama must already be running — this script does NOT start it.
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    echo "FATAL: Ollama not reachable at 127.0.0.1:11434. Start it first (e.g. 'ollama serve'); this script will not start it." >&2
    exit 3
  fi
fi

# 1. EverOS shared-memory pool (best-effort; air-gapped, loopback). Non-fatal if absent
#    — the harness falls back to a local breadcrumb under memory/agent-notes/.
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool (best-effort) on 127.0.0.1:8000"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 8); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Target API up (air-gapped: no Mongo). Only started if not already running.
STARTED_DJ=0
if ! curl -fsS "$BASE/test" >/dev/null 2>&1; then
  say "starting DummyJSON on :$PORT (target; simulate-only, no persistence)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 25); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }

# 2b. Refresh gold from the live API so fidelity scores against current truth
say "building gold"
BASE_URL="$BASE" python data/validate-null-empty-fields/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID  ·  backend: $FORGE_PROVIDER"

# 3. Run the four in parallel (cloud backend → no local saturation)
say "running four null/empty agents (parallel, Claude)"
python scripts/run_null_agents__validate-null-empty-fields.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --max-concurrency "${FORGE_CONCURRENCY:-4}"
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/validate-null-empty-fields/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/validate-null-empty-fields/metric.json \
  --out-prefix results/leaderboard-validate-null-empty-fields

# 5. Stop only what we started
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
