#!/usr/bin/env bash
# Phase 4 — event-driven-api-triggers task: start the LOCAL air-gapped event-driven
# substrate, build gold from it (real publish/poll/DLQ timing), run the four agents
# against it, score fidelity vs gold, update the leaderboard. Re-runnable; each run
# appends to the leaderboard.
#
# DummyJSON is NEVER started or modified here: it consumes no events, so the system under
# test is the purpose-built substrate (tools/eventbus_target/app.py). The honest
# "DummyJSON => 0%" finding is recorded inside gold.json by the gold builder.
#
# Backend is read from config.toml [backend].provider: "ollama" (local/air-gapped — needs a
# reachable `ollama serve`, this script does NOT start it) or "claude-haiku" (cloud, needs
# ANTHROPIC_API_KEY). The substrate + memory (EverOS) are always local.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
EVENTBUS_PORT="${EVENTBUS_PORT:-8930}"
export EVENTBUS_BASE_URL="http://127.0.0.1:${EVENTBUS_PORT}"
export FORGE_EVENTBUS_BASE_URL="$EVENTBUS_BASE_URL"
export EVENTBUS_DB_PATH="$FOUNDRY/data/test-event-driven-api-triggers/eventbus.db"
export EVENTBUS_LOG_PATH="$FOUNDRY/data/test-event-driven-api-triggers/consumer_log.jsonl"
export EVENTBUS_TOPICS_PATH="$FOUNDRY/data/test-event-driven-api-triggers/topics.json"
export EVENTDRIVEN_HEALTH_SETTLE_SECONDS="${EVENTDRIVEN_HEALTH_SETTLE_SECONDS:-3}"
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

# 1b. Write the substrate's topic contract from the single source of truth BEFORE it boots
#     (the gold builder also rewrites it, but the substrate needs it at startup).
say "writing substrate topic contract"
python - <<'PY'
import json, sys
from pathlib import Path
sys.path.insert(0, "agents/common")
import eventdriven_spec as s
out = Path("data/test-event-driven-api-triggers/topics.json")
out.parent.mkdir(parents=True, exist_ok=True)
out.write_text(json.dumps({"topics": [
    {"topic": t["topic"], "event_type": t["event_type"], "resource": t["resource"],
     "resource_id": t["resource_id"], "state_field": t["state_field"],
     "pre_state": t["pre_state"], "expected_state": t["expected_state"],
     "required_fields": list(t["required_fields"])} for t in s.TOPICS]}, indent=2))
print("topics.json written")
PY

# 2. Start the local event-driven substrate (the system under test). Fresh DB each run so
#    gold + agents see a clean state. Only started if not already running.
STARTED_BUS=0
if ! curl -fsS "$EVENTBUS_BASE_URL/health" >/dev/null 2>&1; then
  say "starting event-driven substrate on :$EVENTBUS_PORT (local, air-gapped)"
  rm -f "$EVENTBUS_DB_PATH" "$EVENTBUS_DB_PATH"-wal "$EVENTBUS_DB_PATH"-shm "$EVENTBUS_LOG_PATH" 2>/dev/null
  ( python tools/eventbus_target/app.py >/tmp/eventbus.log 2>&1 ) &
  BUSPID=$!; STARTED_BUS=1
  for i in $(seq 1 20); do curl -fsS "$EVENTBUS_BASE_URL/health" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$EVENTBUS_BASE_URL/health" >/dev/null 2>&1 || { echo "FATAL: substrate not up"; exit 2; }

# 2b. Build gold from the live substrate (real publish/poll/DLQ timing)
say "building gold (publish/poll/DLQ, real timing)"
python data/test-event-driven-api-triggers/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel
say "running four event-trigger agents (parallel)"
python scripts/run_eventdriven_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/test-event-driven-api-triggers/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-event-driven-api-triggers/metric.json \
  --out-prefix results/leaderboard-test-event-driven-api-triggers

# 5. Stop only what we started
[ "$STARTED_BUS" = "1" ] && { kill ${BUSPID:-0} 2>/dev/null; sleep 1; kill -9 ${BUSPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
