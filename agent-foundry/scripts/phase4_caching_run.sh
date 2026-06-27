#!/usr/bin/env bash
# Phase 4 — verify-caching-headers task: run the four agents against the local target,
# score fidelity vs gold, update the leaderboard. Self-contained.
#
# BACKEND = OLLAMA (local, air-gapped) — switched from claude-haiku per the task owner.
# FORGE_PROVIDER=ollama overrides config.toml just for this task's processes; the model is
# config.toml [backend].ollama_model at [backend].ollama_base_url. No API key needed and
# nothing leaves the machine. This script does NOT start the Ollama server — start it
# yourself (`ollama serve`) before running; the check below only warns if it is down.
#
# DummyJSON is NOT modified: it is the read-mostly system-under-test. The agents and gold
# issue PUT/PATCH/POST/DELETE, but DummyJSON's data is deepFrozen and its write controllers
# do not persist, so the target is never altered (verified in src/controllers/*.js: GET after
# the run shows the record + ETag unchanged).
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

# Ollama must be running locally; this script will NOT start it (owner's instruction).
OLLAMA_URL="$(python -c 'import scripts.backend_config as b; print(b.resolve(".")["base_url"])' 2>/dev/null || echo 'http://127.0.0.1:11434/v1')"
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  if ! curl -fsS "${OLLAMA_URL%/v1}/api/tags" >/dev/null 2>&1; then
    echo "WARN: Ollama not reachable at ${OLLAMA_URL%/v1} — start it with 'ollama serve' before running."
    echo "      (Not starting it here, per instruction. Continuing; agent calls will fail until it is up.)"
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
  say "starting DummyJSON on :$PORT (non-persistent target, untouched)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson_cache.log 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }

# 2b. Refresh gold from the live API so fidelity scores against current truth
say "building gold (real caching probes; non-persistent target)"
BASE_URL="$BASE" python data/verify-caching-headers/build_gold.py >/tmp/caching_gold.json
python -c "import json;d=json.load(open('/tmp/caching_gold.json'));print('  compliance%=',d['headline_caching_header_compliance_rate_pct'],'correctness%=',d['empirical_caching_correctness_rate_pct'])"

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID  (backend=ollama)"

# 3. Run the four in parallel
say "running four caching-headers agents (parallel, ollama)"
python scripts/run_caching_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --max-concurrency "${FORGE_CONCURRENCY:-2}"
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/verify-caching-headers/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/verify-caching-headers/metric.json \
  --out-prefix results/leaderboard-verify-caching-headers

# 5. Stop only what we started
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
