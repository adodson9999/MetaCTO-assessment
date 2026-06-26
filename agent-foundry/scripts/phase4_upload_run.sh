#!/usr/bin/env bash
# Phase 4 — file-upload-and-download task: run the four agents against the local target,
# score fidelity vs gold, update the leaderboard. Re-runnable; each run appends to the
# leaderboard. The DummyJSON fork is never modified — its multipart adds are simulated and
# non-persistent, and uploads target real routes only.
#
# Backend is read from config.toml [backend].provider: "ollama" (local/air-gapped — needs a
# reachable `ollama serve`, this script does NOT start it) or "claude-haiku" (cloud, needs
# ANTHROPIC_API_KEY). Memory (EverOS) is best-effort and non-fatal.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8899}"
BASE="http://localhost:${PORT}"
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }

# 0. Backend precondition (read provider from config.toml; do NOT start the LLM server here).
PROVIDER="$(python -c 'import tomllib,pathlib;print(tomllib.loads(pathlib.Path("config.toml").read_text())["backend"]["provider"])' 2>/dev/null || echo ollama)"
if [ "$PROVIDER" = "claude-haiku" ]; then
  if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "FATAL: ANTHROPIC_API_KEY is not set, but config.toml backend = claude-haiku."; exit 3
  fi
elif [ "$PROVIDER" = "ollama" ]; then
  OLLAMA_URL="$(python -c 'import tomllib,pathlib;print(tomllib.loads(pathlib.Path("config.toml").read_text())["backend"]["ollama_base_url"])' 2>/dev/null || echo http://127.0.0.1:11434/v1)"
  # This script never starts Ollama — just verify it is already running, and stop early if not.
  if ! curl -fsS "${OLLAMA_URL%/v1}/api/tags" >/dev/null 2>&1; then
    echo "FATAL: backend = ollama but no Ollama server reachable at ${OLLAMA_URL%/v1}."
    echo "       Start it yourself (\`ollama serve\`, model pulled), then re-run. This script does not start it."
    exit 3
  fi
else
  echo "FATAL: unknown backend provider '$PROVIDER' in config.toml."; exit 3
fi
say "backend provider: $PROVIDER"

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
  say "starting DummyJSON on :$PORT (target, never modified)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "$BASE/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/test" >/dev/null 2>&1 || { echo "FATAL: target not up"; exit 2; }

# 2b. Refresh gold from the live API so fidelity scores against current truth
say "building gold (multipart POST upload + GET download against live target)"
python data/test-file-upload-and-download/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel
say "running four file-upload-and-download agents (parallel)"
python scripts/run_upload_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/test-file-upload-and-download/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-file-upload-and-download/metric.json \
  --out-prefix results/leaderboard-test-file-upload-and-download

# 5. Stop only what we started
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
