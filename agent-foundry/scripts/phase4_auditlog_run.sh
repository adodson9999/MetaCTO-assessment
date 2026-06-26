#!/usr/bin/env bash
# Phase 4 — verify-audit-log-generation task: run the four agents against the local
# target, score fidelity vs gold, update the leaderboard. Self-contained.
#
# BACKEND = OLLAMA (local/air-gapped) — per the task owner's updated instruction
# ("update the llm to Ollama"). FORGE_PROVIDER=ollama matches the committed config.toml
# default; the four agents elicit plans from the local Ollama endpoint.
# This script does NOT start the Ollama server — bring it up yourself beforehand:
#   ollama serve            # in another terminal
#   ollama pull qwen2.5:14b-instruct   # the [backend].ollama_model in config.toml
#
# DUMMYJSON IS NEVER MODIFIED. The agents/gold issue real auth + create/update/delete,
# but DummyJSON's data is deepFrozen and its write controllers do not persist, so the
# target is never changed. The audit substrate is DummyJSON's OWN winston request-log,
# enabled via the runtime LOG_ENABLED=true env flag (not a source change) and captured
# to a file the harness reads via FORGE_AUDIT_LOG.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"

export PATH="$FOUNDRY/.venv/bin:$PATH"        # venv python first (macOS has no bare `python`)
PYBIN="$(command -v python || command -v python3)"
RUN_ID="${1:-$("$PYBIN" -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
AUDIT_LOG="/tmp/dummyjson_audit_${RUN_ID}.log"

export FORGE_TARGET_BASE_URL="$BASE"
export FORGE_PROVIDER="ollama"                 # <-- local/air-gapped LLM (config.toml default)
export FORGE_AUDIT_LOG="$AUDIT_LOG"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }

# Ollama must already be running (this script does NOT start it). Preflight only.
OLLAMA_URL="$("$PYBIN" -c 'import tomllib;print(tomllib.load(open("config.toml","rb"))["backend"]["ollama_base_url"])' 2>/dev/null || echo "http://127.0.0.1:11434/v1")"
if ! curl -fsS "${OLLAMA_URL%/v1}/api/tags" >/dev/null 2>&1; then
  echo "FATAL: Ollama not reachable at ${OLLAMA_URL%/v1}. Start it first: 'ollama serve' (+ 'ollama pull qwen2.5:14b-instruct'). This script does not start the server."; exit 3
fi

# 1. EverOS shared-memory pool up (loopback, best-effort)
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 15); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Target API up WITH LOGGING (air-gapped: no Mongo). We start our own instance with
#    LOG_ENABLED=true so its winston "HTTP Request" stdout is the captured audit substrate.
STARTED_DJ=0
if curl -fsS "$BASE/test" >/dev/null 2>&1; then
  say "DummyJSON already on :$PORT — reusing it (note: its audit-log capture may be empty if it was started without LOG_ENABLED; the finding stays 0% either way)"
  : > "$AUDIT_LOG"
else
  say "starting DummyJSON on :$PORT with LOG_ENABLED=true (non-persistent target; log -> $AUDIT_LOG)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=production \
      PORT="$PORT" LOG_ENABLED=true node index.js >"$AUDIT_LOG" 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }

# 2b. Refresh gold from the live API + captured log so fidelity scores against current truth
say "building gold (real auth + create/update/delete, captured log; non-persistent target)"
BASE_URL="$BASE" FORGE_AUDIT_LOG="$AUDIT_LOG" python data/verify-audit-log-generation/build_gold.py >/tmp/audit_gold.json
python -c "import json;d=json.load(open('/tmp/audit_gold.json'));print('  coverage_rate%=',d['headline_audit_log_coverage_rate_pct'],'correctness%=',d['empirical_audit_correctness_rate_pct'])"

say "run id: $RUN_ID  (backend=claude-haiku)"

# 3. Run the four in parallel (they read FORGE_AUDIT_LOG from the env)
say "running four audit-log-verification agents (parallel, claude-haiku)"
python scripts/run_auditlog_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --max-concurrency "${FORGE_CONCURRENCY:-2}"
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/verify-audit-log-generation/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/verify-audit-log-generation/metric.json \
  --out-prefix results/leaderboard-verify-audit-log-generation

# 5. Stop only what we started
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
