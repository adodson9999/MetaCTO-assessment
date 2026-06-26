#!/usr/bin/env bash
# Phase 4 — verify-third-party-oauth-integration task: run the four agents, driving the
# documented OAuth2 authorization-code flow against the local target, score fidelity vs
# gold, update the leaderboard. Re-runnable; each run appends to the leaderboard.
# DummyJSON is never modified — the flow's auth requests are DummyJSON's own auth surface
# and its writes are non-persistent. Backend = claude-haiku (per the task's config.toml),
# so this build is NOT air-gapped: it requires ANTHROPIC_API_KEY. Memory (EverOS) is
# started best-effort and is non-fatal.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }

# 0. Backend precondition (provider-aware). The foundry NEVER starts the LLM server.
PROVIDER="$(python -c 'import tomllib;print(tomllib.load(open("config.toml","rb"))["backend"]["provider"])' 2>/dev/null || echo unknown)"
say "backend provider: $PROVIDER"
if [ "$PROVIDER" = "claude-haiku" ]; then
  if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "FATAL: provider=claude-haiku but ANTHROPIC_API_KEY is not set."; exit 3
  fi
elif [ "$PROVIDER" = "ollama" ]; then
  OLLAMA_URL="$(python -c 'import tomllib;print(tomllib.load(open("config.toml","rb"))["backend"]["ollama_base_url"])' 2>/dev/null)"
  if ! curl -fsS "${OLLAMA_URL%/v1}/api/tags" >/dev/null 2>&1; then
    echo "FATAL: provider=ollama but the Ollama server is not reachable at ${OLLAMA_URL}."
    echo "       Start it yourself ('ollama serve' with the ollama_model pulled) — the foundry does not start it."; exit 3
  fi
else
  echo "FATAL: unknown backend provider '$PROVIDER' in config.toml [backend].provider."; exit 3
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
  say "starting DummyJSON on :$PORT (target — never modified)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }

# 2b. Refresh gold from the live API so fidelity scores against current truth
say "building gold (drive the documented flow against the live target)"
python data/verify-third-party-oauth-integration/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four (parallel; concurrency 2 to stay gentle on the backend)
say "running four OAuth-integration agents"
python scripts/run_oauth_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency "${FORGE_CONCURRENCY:-2}"
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/verify-third-party-oauth-integration/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/verify-third-party-oauth-integration/metric.json \
  --out-prefix results/leaderboard-verify-third-party-oauth-integration

# 5. Stop only what we started
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
