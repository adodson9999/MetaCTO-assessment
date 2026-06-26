#!/usr/bin/env bash
# Phase 4 — multipart/form-data handling task: run the four agents against the local
# target, score fidelity vs gold, update the leaderboard.
#
# Backend: OLLAMA (local, air-gapped) per the user's instruction to switch this agent's
# LLM to Ollama. The Ollama server is NOT started here (per the user) — this script only
# checks that it is already reachable and warns if it is not. Re-runnable; each run
# appends to the leaderboard. DummyJSON is never modified — the POST /add routes are
# non-persistent simulated writes and the server deletes any parsed multipart file.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
export FORGE_TARGET_BASE_URL="$BASE"
export FORGE_PROVIDER="ollama"   # <-- Ollama backend (local, air-gapped), not Claude (per user)
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }

# Ollama must already be serving on :11434. We do NOT start it (per user instruction).
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "WARNING: ollama backend selected but the server is not reachable at http://127.0.0.1:11434"
  echo "         not starting it (per instruction). Start it yourself with 'ollama serve', then re-run."
fi

# 1. EverOS shared-memory pool up (loopback). Best-effort; the harness degrades gracefully.
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Target API up (air-gapped: no Mongo). Only started if not already running.
STARTED_DJ=0
if ! curl -fsS "$BASE/test" >/dev/null 2>&1; then
  say "starting DummyJSON on :$PORT (target)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }

# 2b. Refresh gold from the live API so fidelity scores against current truth.
say "building gold"
BASE_URL="$BASE" python data/test-multipart-form-data-handling/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID  (backend: ollama)"

# 3. Run the four in parallel
say "running four multipart-form-data agents (parallel, ollama backend)"
python scripts/run_multipart_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency "${FORGE_CONCURRENCY:-4}"
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/test-multipart-form-data-handling/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-multipart-form-data-handling/metric.json \
  --out-prefix results/leaderboard-test-multipart-form-data-handling

# 5. Stop only what we started
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
