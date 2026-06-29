#!/usr/bin/env bash
# Phase 4 — idempotency-of-endpoints task: run the four agents against the local
# target, score fidelity vs gold, update the leaderboard. Self-contained.
#
# BACKEND = OLLAMA (local, air-gapped) — config.toml [backend].provider default.
# FORGE_PROVIDER=ollama is set explicitly so an inherited env var can't override it.
# This script does NOT start the Ollama server — it only health-checks it and fails with
# instructions if it is down (start it yourself: `ollama serve`). The model is taken from
# config.toml ([backend].ollama_model, e.g. qwen2.5:14b-instruct).
#
# WRITES NOTE: the agents and gold issue real PUT/DELETE/POST, but DummyJSON's data is
# deepFrozen and its write controllers do not persist, so the target is never modified
# (verified in src/controllers/*.js: GET after the run shows the record + `total` unchanged).
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
OLLAMA_URL="${FORGE_OLLAMA_URL:-http://127.0.0.1:11434}"
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# 0. Ollama must already be running — we do NOT start it here (by request).
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  if ! curl -fsS "$OLLAMA_URL/api/tags" >/dev/null 2>&1; then
    echo "FATAL: Ollama is not running at $OLLAMA_URL. Start it yourself (e.g. 'ollama serve'),"
    echo "       pull the model from config.toml ([backend].ollama_model), then re-run. This"
    echo "       script intentionally does not launch the server."
    exit 3
  fi
fi

# 1. EverOS shared-memory pool up (loopback, best-effort)
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 15); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Target API up (air-gapped: no Mongo). Only started if not already running.
STARTED_DJ=0
if ! curl -fsS "$BASE/test" >/dev/null 2>&1; then
  say "starting DummyJSON on :$PORT (non-persistent target)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson_idem.log 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }

# 2b. Refresh gold from the live API so fidelity scores against current truth
say "building gold (real replayed writes; non-persistent target)"
BASE_URL="$BASE" python data/test-idempotency-of-endpoints/build_gold.py >/tmp/idem_gold.json
python -c "import json;d=json.load(open('/tmp/idem_gold.json'));print('  compliance%=',d['headline_idempotency_compliance_rate_pct'],'correctness%=',d['empirical_idempotency_correctness_rate_pct'])"

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID  (backend=ollama)"

# 3. Run the four in parallel
say "running four idempotency agents (parallel, ollama)"
python scripts/run_idempotency_agents__test-idempotency-of-endpoints.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --max-concurrency "${FORGE_CONCURRENCY:-2}"
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/test-idempotency-of-endpoints/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-idempotency-of-endpoints/metric.json \
  --out-prefix results/leaderboard-test-idempotency-of-endpoints

# 5. Stop only what we started
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
