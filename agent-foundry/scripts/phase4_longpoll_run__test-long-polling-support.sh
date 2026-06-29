#!/usr/bin/env bash
# Phase 4 — long-polling task: stand up the local longpoll-target fixture, refresh gold
# (real behavior under real wall-clock timing), run the four agents on the OLLAMA backend,
# score fidelity vs gold, update the leaderboard. Re-runnable; each run appends.
#
# Backend = OLLAMA per the owner note. This script forces FORGE_PROVIDER=ollama for this
# build without touching the global config.toml. It NEVER starts the Ollama server — start
# it yourself (`ollama serve`, with the configured model pulled) before running; the script
# only verifies it is reachable and stops early if not. DummyJSON is NOT used and NOT
# modified by this build at all — the SUT is the air-gapped longpoll-target fixture.
# Memory (EverOS) is best-effort.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8921}"
BASE="http://127.0.0.1:${PORT}"
export FORGE_TARGET_BASE_URL="$BASE"
# OLLAMA backend for this build (override only; global config.toml stays ollama).
PY="$FOUNDRY/.venv/bin/python"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# 0. Backend precondition. This script NEVER starts the LLM server.
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  OLLAMA_URL="$("$PY" -c 'import tomllib,pathlib;print(tomllib.loads(pathlib.Path("config.toml").read_text())["backend"]["ollama_base_url"])' 2>/dev/null || echo http://127.0.0.1:11434/v1)"
  if ! curl -fsS "${OLLAMA_URL%/v1}/api/tags" >/dev/null 2>&1; then
    echo "FATAL: backend = ollama but no Ollama server reachable at ${OLLAMA_URL%/v1}." >&2
    echo "       Start it yourself (\`ollama serve\`, model pulled), then re-run. This script does not start it." >&2
    exit 3
  fi
elif [ "$FORGE_PROVIDER" = "claude-haiku" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "FATAL: FORGE_PROVIDER=claude-haiku but ANTHROPIC_API_KEY is not set." >&2
  exit 3
fi
say "backend provider: $FORGE_PROVIDER"

# 1. longpoll-target fixture up (the local long-poll backend stand-in). Start if needed.
STARTED_LP=0
if ! curl -fsS "$BASE/__health" >/dev/null 2>&1; then
  say "starting longpoll-target on $BASE"
  ( "$PY" "$FOUNDRY/tools/longpoll-target/server.py" --host 127.0.0.1 --port "$PORT" \
      >/tmp/longpoll-target.log 2>&1 ) &
  LPPID=$!; STARTED_LP=1
  for i in $(seq 1 20); do curl -fsS "$BASE/__health" >/dev/null 2>&1 && break; sleep 0.5; done
fi
curl -fsS "$BASE/__health" >/dev/null 2>&1 || { echo "FATAL: longpoll-target not up"; exit 2; }

# 1b. EverOS shared-memory pool (best-effort; harness degrades to file notes if absent)
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  if [ -x "$FOUNDRY/vendor/EverOS/.venv/bin/everos" ]; then
    say "starting EverOS memory pool on 127.0.0.1:8000 (best-effort)"
    ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
        --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
    EVPID=$!
    for i in $(seq 1 15); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
  fi
fi

# 2. Refresh gold from the live fixture (real behavior under real timing)
say "building gold (no-event + event long-polls, real wall-clock timing)"
"$PY" data/test-long-polling-support/build_gold.py

RUN_ID="${1:-$("$PY" -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four agents (parallel; ollama backend)
say "running four long-polling agents (parallel, ollama backend)"
"$PY" scripts/run_longpoll_agents__test-long-polling-support.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
"$PY" judge/test-long-polling-support/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
"$PY" scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-long-polling-support/metric.json \
  --out-prefix results/leaderboard-test-long-polling-support

# 5. Stop only what we started
[ "$STARTED_LP" = "1" ] && { kill ${LPPID:-0} 2>/dev/null; sleep 1; kill -9 ${LPPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
