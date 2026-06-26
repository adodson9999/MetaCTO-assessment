#!/usr/bin/env bash
# Phase 4 — CI/CD-Pipeline-Runner task (general position): classify the enabled
# agents of each pipeline-run fixture, run the four agents against the local scenario
# fixtures, score Pipeline-Summary Fidelity vs the deterministic gold, update the
# leaderboard.
#
# BACKEND = OLLAMA (local / air-gapped), per the owner's request. Set via the
# FORGE_PROVIDER env override so the run is explicit regardless of config.toml. All four
# agents reach Ollama through its native OpenAI-compatible /v1 endpoint: langgraph
# (langchain ChatOllama), crewai (LiteLLM "ollama/" string), and both claude_sdk + the
# subagent via the OpenAI-compatible local endpoint. No LiteLLM proxy and no Anthropic
# key needed.
#
# This script does NOT start the Ollama server, NOT install Ollama, and NOT pull a
# model — the owner asked that the server not be started. Ollama must already be running
# locally if you want the live LLM run; if it is unreachable the run exits with a clear
# message rather than launching anything. (Building the gold + the deterministic
# self-test need no server at all.)
#
# DummyJSON is NEVER touched by this task — it has no CI surface. The only network call
# is a read-only GET <ollama>/api/tags (the task's server health step).
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OLLAMA_URL="${FORGE_OLLAMA_BASE_URL:-http://127.0.0.1:11434}"
export FORGE_PROVIDER="ollama"          # <-- local Ollama backend for this task
export FORGE_OLLAMA_BASE_URL="$OLLAMA_URL"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }

# 1. Build the deterministic gold (materialises fixtures + parses them). No server needed.
say "building gold (deterministic, from local scenario fixtures)"
OLLAMA_BASE_URL="$OLLAMA_URL" python data/run-cicd-pipeline/build_gold.py >/dev/null
say "gold built: $(python -c 'import json;d=json.load(open("data/run-cicd-pipeline/gold.json"));print(d["summary"]["scenarios"],"scenarios,",d["summary"]["total_gold_fields"],"fields; block=",d["summary"]["runs_that_must_block_deployment"])')"

# 2. Ollama must already be running for the LIVE agent run (we do NOT start it).
#    Read-only reachability probe of /api/tags. If down, stop before launching agents.
if curl -fsS "${OLLAMA_URL}/api/tags" >/dev/null 2>&1; then
  say "Ollama reachable at ${OLLAMA_URL} (local, air-gapped)"
else
  echo "NOTE: Ollama is not reachable at ${OLLAMA_URL}. This script does NOT start it." >&2
  echo "      Start it yourself ('ollama serve' + 'ollama pull ${FORGE_OLLAMA_MODEL:-llama3.1:8b}')" >&2
  echo "      then re-run for the live ranking. Gold + self-test above need no server." >&2
  exit 2
fi

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel (batches of 4 — the whole panel fits one batch).
say "running four cicd-pipeline-runner agents (parallel, ollama)"
python scripts/run_cicd_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 4. Score fidelity (+ discriminators) vs gold, then build the leaderboard
say "scoring fidelity + discriminators"
python judge/run-cicd-pipeline/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"

# 5. Nothing to stop — we started no server and no DummyJSON for this task.
say "done (run $RUN_ID, run_agents rc=$RC)"
