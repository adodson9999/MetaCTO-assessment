#!/usr/bin/env bash
# Phase 4 — webhook-delivery task: run the four agents against the local target, score
# plan-fidelity vs gold, update the leaderboard. Re-runnable; each run appends to the
# leaderboard. DummyJSON's source is NEVER modified — its POST /<x>/add endpoints are
# simulated (persist nothing) and it has no /webhooks route, so executing the plan can't
# mutate it. The webhook receiver is LOCAL (loopback, ephemeral port) — air-gapped, no
# ngrok. Backend = claude-haiku (per config.toml), so this build is NOT air-gapped on the
# LLM side: it requires ANTHROPIC_API_KEY. Memory (EverOS) is best-effort and non-fatal.
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

# 2. Target API up (air-gapped: no Mongo). Only started if not already running.
STARTED_DJ=0
if ! curl -fsS "$BASE/test" >/dev/null 2>&1; then
  say "starting DummyJSON on :$PORT (target; source untouched)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }

# 2b. Refresh gold from the live API (real receiver, real execution) so fidelity scores
#     against current truth.
say "building gold (local receiver, register/create POSTs, HMAC verify)"
python data/test-webhook-delivery/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel
say "running four webhook agents (parallel)"
python scripts/run_webhook_agents__test-webhook-delivery.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/test-webhook-delivery/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-webhook-delivery/metric.json \
  --out-prefix results/leaderboard-test-webhook-delivery

# 5. Stop only what we started
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
