#!/usr/bin/env bash
# Phase 4 (Verify Error Message Clarity) — run the four agents against the local
# target on the OLLAMA backend, score, leaderboard.
# Self-contained. Re-runnable; each run appends to the leaderboard.
# NOTE: this script does NOT start the Ollama server — start it yourself
# (`ollama serve`) before running; it only checks reachability and warns.
set -uo pipefail

# Self-locating: the foundry is this script's parent dir; the target repo is the
# foundry's parent (the foundry lives inside the host repo). No hardcoded paths.
FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"

# --- backend: Ollama (local, air-gapped) ---
export FORGE_PROVIDER="ollama"
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"   # so run_*.py's "python" = venv python
# Local single-slot servers saturate under parallelism; default 1, raise with FORGE_CONCURRENCY.
CONC="${FORGE_CONCURRENCY:-1}"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }

# Ollama must already be running — this script intentionally does NOT start it.
OLLAMA_URL="$(python -c 'import backend_config as b;print(b.resolve().get("base_url",""))' 2>/dev/null)"
if ! curl -fsS "${OLLAMA_URL%/v1}/api/tags" >/dev/null 2>&1; then
  echo "FATAL: Ollama not reachable at ${OLLAMA_URL%/v1} — start it first ('ollama serve'), then re-run."; exit 3
fi

# EverOS shared-memory pool (best-effort; the harness falls back to local notes).
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  if [ -x "$FOUNDRY/vendor/EverOS/.venv/bin/everos" ]; then
    say "starting EverOS memory pool on 127.0.0.1:8000"
    ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
        --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
    for i in $(seq 1 15); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
  fi
fi

# Target API up (air-gapped: no Mongo).
if ! curl -fsS "$BASE/test" >/dev/null 2>&1; then
  say "starting DummyJSON on :$PORT"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up at $BASE"; exit 2; }

# Refresh the gold against the live target (deterministic ground truth).
say "rebuilding gold from live target"
BASE_URL="$BASE" python data/clarity/build_gold.py >/dev/null || { echo "FATAL: gold build failed"; exit 2; }

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID  (backend=$FORGE_PROVIDER, concurrency=$CONC)"

say "running four agents (parallel, Claude backend)"
python scripts/run_clarity_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency "$CONC"

say "scoring + leaderboard"
python judge/clarity/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
echo
say "done — results/clarity/leaderboard.md"
