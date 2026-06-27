#!/usr/bin/env bash
# Phase 4 (schema task) — run the four response-schema-validation agents against the
# local target, score fidelity vs gold, update the leaderboard. Self-contained +
# air-gapped. Re-runnable; each run appends to the leaderboard.
set -uo pipefail

# Self-locating: the foundry is this script's parent dir; the target repo is the
# foundry's parent (the foundry lives inside the host repo). No hardcoded paths.
FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
export FORGE_MAX_ENDPOINTS="${FORGE_MAX_ENDPOINTS:-0}"   # 0 = all 22
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"   # so run_schema_agents.py's "python" = venv python

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# 1. Ollama up
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
    say "starting ollama"; nohup ollama serve >/tmp/ollama.log 2>&1 &
    for i in $(seq 1 20); do curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1 && break; sleep 1; done
  fi
fi

# 1b. EverOS shared-memory pool up (loopback)
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Target API up (air-gapped: no Mongo). Only start if not already serving.
if ! curl -fsS "$BASE/test" >/dev/null 2>&1; then
  say "starting DummyJSON on :$PORT"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  DJPID=$!
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; [ -n "${DJPID:-}" ] && kill $DJPID 2>/dev/null; exit 2; }

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. (Re)build gold so fidelity is scored against fresh observed behavior.
say "rebuilding gold (data/schema/)"
BASE_URL="$BASE" python data/schema/build_gold.py >/dev/null

# 4. Run the four agents. Default concurrency=1: the local llama-server serves one
#    request at a time (-np 1), so >1 agent contends -> multi-minute waits -> 500s.
#    Serializing agents keeps each LLM call fast and the run reliable. Override with
#    FORGE_CONCURRENCY if the backend can handle more (e.g. cloud Haiku).
CONC="${FORGE_CONCURRENCY:-1}"
say "running four agents (concurrency=$CONC)"
python scripts/run_schema_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency "$CONC"
RC=$?

# 5. Score fidelity vs gold + leaderboard
say "scoring fidelity + leaderboard"
python judge/schema/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"

# 6. Stop target (+ EverOS) if we started them
[ -n "${DJPID:-}" ] && { kill $DJPID 2>/dev/null; sleep 1; kill -9 $DJPID 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_schema_agents rc=$RC)"
