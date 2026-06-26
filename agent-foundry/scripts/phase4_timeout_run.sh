#!/usr/bin/env bash
# Phase 4 — timeout-handling task: stand up the local timeout-gateway, refresh gold
# (real behavior under the injected 60s upstream delay), run the four agents on the
# local Ollama backend (config.toml [backend].provider), score fidelity vs gold, update
# the leaderboard. Re-runnable; each run appends to the leaderboard.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8911}"
BASE="http://127.0.0.1:${PORT}"
export FORGE_TARGET_BASE_URL="$BASE"
PY="$FOUNDRY/.venv/bin/python"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }

# 1. Timeout-gateway up (the local WireMock+Toxiproxy stand-in). Start if needed.
STARTED_GW=0
if ! curl -fsS "$BASE/__health" >/dev/null 2>&1; then
  say "starting timeout-gateway on $BASE"
  ( "$PY" "$FOUNDRY/tools/timeout-gateway/gateway.py" --host 127.0.0.1 --port "$PORT" \
      >/tmp/timeout-gateway.log 2>&1 ) &
  GWPID=$!; STARTED_GW=1
  for i in $(seq 1 20); do curl -fsS "$BASE/__health" >/dev/null 2>&1 && break; sleep 0.5; done
fi
curl -fsS "$BASE/__health" >/dev/null 2>&1 || { echo "FATAL: gateway not up"; exit 2; }

# 1a. Ollama backend must be running (NOT started here — start it separately per the
#     config note: `ollama serve`, with the ollama_model pulled). The four agents elicit
#     plans from the local Ollama endpoint; gold + harness validation need no LLM.
if ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "FATAL: Ollama not reachable at http://127.0.0.1:11434 — start it first:" >&2
  echo "       ollama serve   (then: ollama pull qwen2.5:14b-instruct)" >&2
  exit 3
fi

# 1b. EverOS shared-memory pool (best-effort; harness degrades to file notes if absent)
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  if [ -x "$FOUNDRY/vendor/EverOS/.venv/bin/everos" ]; then
    say "starting EverOS memory pool on 127.0.0.1:8000"
    ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
        --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
    EVPID=$!
    for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
  fi
fi

# 2. Refresh gold from the live gateway (real behavior under the injected delay)
say "building gold (inject 60s delay, probe, restore)"
"$PY" data/test-timeout-handling/build_gold.py

RUN_ID="${1:-$("$PY" -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four agents (parallel; local Ollama backend)
say "running four timeout agents (parallel, ollama backend)"
"$PY" scripts/run_timeout_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 2
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
"$PY" judge/test-timeout-handling/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
"$PY" scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-timeout-handling/metric.json \
  --out-prefix results/leaderboard-test-timeout-handling

# 5. Stop only what we started
[ "$STARTED_GW" = "1" ] && { kill ${GWPID:-0} 2>/dev/null; sleep 1; kill -9 ${GWPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
