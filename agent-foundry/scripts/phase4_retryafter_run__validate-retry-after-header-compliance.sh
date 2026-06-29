#!/usr/bin/env bash
# Phase 4 — Retry-After-header-compliance task: run the four agents against the local
# target (READ-ONLY), score fidelity vs gold, update the leaderboard. Re-runnable; each
# run appends to the leaderboard. DummyJSON is NEVER modified — agents and gold only issue
# read-only GETs.
#
# Backend = CLAUDE per the task owner ("don't use ollama here, just the claude option").
# This build pins FORGE_PROVIDER=claude-haiku for THIS run only (env override; it does NOT
# mutate the shared config.toml, which other builds keep at ollama). Requires
# ANTHROPIC_API_KEY. Memory (EverOS) is started best-effort and is non-fatal.
set -uo pipefail

# --- backend: claude only (per owner). Env override wins over config.toml. ---

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

# 0. Backend precondition: this build is claude-only; claude-haiku needs an API key.
case "$FORGE_PROVIDER" in
  claude-haiku|claude-cli)
    if [ "$FORGE_PROVIDER" = "claude-haiku" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
      echo "FATAL: ANTHROPIC_API_KEY is not set, but this build is claude-only (FORGE_PROVIDER=claude-haiku)."; exit 3
    fi ;;
  *)
    echo "FATAL: this build is claude-only per the owner; refusing FORGE_PROVIDER=$FORGE_PROVIDER (use claude-haiku or claude-cli)."; exit 3 ;;
esac
say "backend = $FORGE_PROVIDER (claude only, per owner; DummyJSON never modified)"

# 1. EverOS shared-memory pool up (loopback, best-effort — note-writing is non-fatal)
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000 (best-effort)"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 15); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Target API up with the rate limiter ACTIVE. The limiter is skipped when
#    NODE_ENV=development, so we MUST boot NODE_ENV=production. A stale development
#    instance would silently disable the limiter and corrupt the whole task, so we
#    always kill any running DummyJSON and start a guaranteed-fresh production one
#    (air-gapped: MONGODB_URI= -> connectDB no-ops; NODE_ENV does not gate Mongo).
#    DummyJSON source is NEVER edited — only its NODE_ENV at boot.
say "starting fresh DummyJSON on :$PORT (NODE_ENV=production, limiter ACTIVE) — source unmodified"
pkill -f "node index.js" 2>/dev/null; sleep 2
( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=production \
    PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
DJPID=$!; STARTED_DJ=1
for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }
# verify the limiter is actually active (X-RateLimit-* present); else abort — a run
# against a disabled limiter would be meaningless.
if ! curl -fsS -D - -o /dev/null -H "X-Forwarded-For: 10.250.250.1" "$BASE/test" \
     | grep -qi "x-ratelimit-limit"; then
  echo "FATAL: rate limiter not active on target (no X-RateLimit-* header). Check NODE_ENV."; exit 4
fi
say "rate limiter confirmed active"

# 2b. Refresh gold from the live API (read-only, real timing) so fidelity scores against
#     current truth AND the timing-sensitive still-limited probe is observed under the
#     SAME machine conditions as the agents in this run.
say "building gold (read-only GETs, real timing)"
python data/validate-retry-after-header-compliance/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel
say "running four Retry-After agents (parallel)"
python scripts/run_retryafter_agents__validate-retry-after-header-compliance.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/validate-retry-after-header-compliance/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/validate-retry-after-header-compliance/metric.json \
  --out-prefix results/leaderboard-validate-retry-after-header-compliance

# 5. Stop only what we started
[ "${STARTED_DJ:-0}" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
