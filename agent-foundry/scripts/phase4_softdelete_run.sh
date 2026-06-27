#!/usr/bin/env bash
# Phase 4 — soft-delete-behavior task: run the four agents against the local soft-delete
# target, score fidelity vs gold, update the leaderboard. Self-contained.
#
# Backend = OLLAMA (local, air-gapped) per the user's latest instruction. Set via
# FORGE_PROVIDER below; config.toml is already provider=ollama. This script does NOT
# start the ollama server — start it yourself (`ollama serve`, with the [backend].
# ollama_model pulled) before running, or set FORGE_PROVIDER=claude-haiku to use the
# Anthropic API (needs ANTHROPIC_API_KEY + credits), or FORGE_PROVIDER=claude-cli to use
# the claude.ai subscription via scripts/claude_cli_shim.py (needs the shim on :8787).
#
# Target:
#   SUT = local, air-gapped, SQLite-backed soft-delete endpoint on :8950
#         (tools/softdelete_target/app.py). DummyJSON is NOT used and NOT modified:
#         it never persists and exposes no queryable DB, so the deleted_at / DB-row /
#         collection-exclusion assertions are unverifiable against it.
# Re-runnable; the DB is reset each run so the listing stays small and deterministic,
# and each run appends to the leaderboard.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"

SUT_PORT="${SOFTDELETE_TARGET_PORT:-8950}"
SUT_BASE="http://127.0.0.1:${SUT_PORT}"
DB_PATH="$FOUNDRY/data/test-soft-delete-behavior/resources.db"

export FORGE_BASE_URL="$SUT_BASE"
export SOFTDELETE_TARGET_PORT="$SUT_PORT"
export SOFTDELETE_DB_PATH="$DB_PATH"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

if [ "$FORGE_PROVIDER" = "claude-haiku" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "FATAL: FORGE_PROVIDER=claude-haiku but ANTHROPIC_API_KEY is not set."; exit 3
fi

# 1. EverOS shared-memory pool up (loopback, best-effort)
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Soft-delete target up (local SQLite-backed endpoint). Fresh DB each run.
STARTED_SUT=0
if curl -fsS "$SUT_BASE/health" >/dev/null 2>&1; then
  say "soft-delete target already running on :$SUT_PORT (using it as-is)"
else
  say "resetting DB + starting local soft-delete target on :$SUT_PORT (db=$DB_PATH)"
  rm -f "$DB_PATH" "$DB_PATH-wal" "$DB_PATH-shm" 2>/dev/null
  python tools/softdelete_target/app.py >/tmp/softdelete_target.log 2>&1 &
  SUTPID=$!; STARTED_SUT=1
  for i in $(seq 1 20); do curl -fsS "$SUT_BASE/health" >/dev/null 2>&1 && break; sleep 0.5; done
fi
curl -fsS "$SUT_BASE/health" >/dev/null 2>&1 || { echo "FATAL: soft-delete target not up"; exit 2; }

# 2b. Refresh gold from the live target so fidelity scores against current truth
say "building gold (case_count create->delete->verify lifecycles + direct DB query)"
python data/test-soft-delete-behavior/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID  ·  backend: $FORGE_PROVIDER"

# 3. Run the four in parallel
say "running four soft-delete agents"
python scripts/run_softdelete_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --max-concurrency "${FORGE_CONCURRENCY:-2}"
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/test-soft-delete-behavior/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-soft-delete-behavior/metric.json \
  --out-prefix results/leaderboard-test-soft-delete-behavior

# 5. Stop only what we started
[ "$STARTED_SUT" = "1" ] && { kill ${SUTPID:-0} 2>/dev/null; sleep 1; kill -9 ${SUTPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
