#!/usr/bin/env bash
# Phase 4 — Measure-API-Consumer-Satisfaction task: run the four agents, each rendering the
# documented NPS-survey-measurement contract into a JSON measurement plan; the deterministic
# harness executes every plan against the LOCAL seeded usage fixture, computes the dashboard,
# scores fidelity vs gold, and updates the leaderboard.
#
# BACKEND = OLLAMA (owner switched this workflow to Ollama). Set via FORGE_PROVIDER, so the
# value here drives the whole run regardless of config.toml; override per-run by exporting
# FORGE_PROVIDER=claude-haiku before invoking. Under ollama all four frameworks reach the
# LOCAL Ollama OpenAI-compatible endpoint directly (langgraph via ChatOllama, crewai via
# ollama/<model>, claude_sdk + the subagent via the Ollama /v1 path) — NO proxy/shim and NO
# ANTHROPIC_API_KEY are needed. Under claude-haiku the LiteLLM/stdlib shim is started for the
# two OpenAI-path agents.
#
# This script does NOT start the Ollama server (owner instruction: "do not start the
# server"). Start it yourself first — `ollama serve` with the configured model pulled — or
# the four agents will fail to reach it. The script only health-warns if it is unreachable.
#
# The system under measurement is a purpose-built, air-gapped local SQLite fixture seeded
# with an api_request_logs table + collected survey responses (tools/satisfaction-fixture).
# DummyJSON is NEVER used or modified by this task — there is no DummyJSON in this pipeline,
# and no HTTP system-under-test (the fixture is queried directly).
#
# Self-contained + re-runnable; each run appends to the leaderboard.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PROXY_PORT="${FORGE_LITELLM_PORT:-4000}"
DATASET="${FORGE_NPS_DATASET:-current}"
PROVIDER="${FORGE_PROVIDER:-ollama}"          # <-- Ollama backend for this task (owner switch)
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

STARTED_PROXY=0
if [ "$PROVIDER" = "claude-haiku" ]; then
  if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "FATAL: ANTHROPIC_API_KEY is not set; the Claude backend cannot run." >&2
    exit 2
  fi
  # 1. OpenAI-compatible shim for claude_sdk + subagent (LiteLLM proxy if present, else the
  #    dependency-light stdlib OpenAI->Anthropic shim). Both expose /chat/completions +
  #    /health/liveliness, so the agents are unchanged.
  if ! curl -fsS "http://127.0.0.1:${PROXY_PORT}/health/liveliness" >/dev/null 2>&1; then
    if python -c "import fastapi" >/dev/null 2>&1 && command -v litellm >/dev/null 2>&1; then
      say "starting LiteLLM proxy on 127.0.0.1:${PROXY_PORT} (claude-haiku-4-5 -> anthropic)"
      cat > /tmp/forge_litellm_claude.yaml <<'YAML'
model_list:
  - model_name: claude-haiku-4-5
    litellm_params:
      model: anthropic/claude-haiku-4-5
      api_key: os.environ/ANTHROPIC_API_KEY
YAML
      nohup litellm --config /tmp/forge_litellm_claude.yaml --host 127.0.0.1 \
          --port "$PROXY_PORT" >/tmp/forge_litellm.log 2>&1 &
      PROXYPID=$!; STARTED_PROXY=1
    else
      say "litellm[proxy] unavailable -> starting stdlib OpenAI->Anthropic shim on 127.0.0.1:${PROXY_PORT}"
      nohup python tools/openai-anthropic-shim/shim.py --host 127.0.0.1 \
          --port "$PROXY_PORT" >/tmp/forge_shim.log 2>&1 &
      PROXYPID=$!; STARTED_PROXY=1
    fi
    for i in $(seq 1 40); do
      curl -fsS "http://127.0.0.1:${PROXY_PORT}/health/liveliness" >/dev/null 2>&1 && break; sleep 1
    done
  fi
elif [ "$FORGE_PROVIDER" = "ollama" ]; then
  # 1. Ollama backend: NO proxy needed. Do NOT start the server (owner instruction) — only
  #    health-warn so a misconfiguration is visible rather than silent.
  OLLAMA_URL="$(python -c "import tomllib;print(tomllib.load(open('config.toml','rb'))['backend']['ollama_base_url'])" 2>/dev/null || echo http://127.0.0.1:11434/v1)"
  OLLAMA_HOST="${OLLAMA_URL%/v1}"
  if curl -fsS "${OLLAMA_HOST}/api/tags" >/dev/null 2>&1; then
    say "ollama backend reachable at ${OLLAMA_HOST} (server NOT started by this script)"
  else
    say "WARNING: ollama not reachable at ${OLLAMA_HOST}. This script does not start it "
    say "         (owner instruction). Start it with 'ollama serve' + pull the model, then re-run."
  fi
fi

# 2. (Re)build gold from the seeded fixture (deterministic; pure local Python). No SUT,
#    no DummyJSON, no network.
say "building gold (seeded fixture -> canonical plan -> dashboard, dataset=$DATASET)"
python data/measure-api-consumer-satisfaction/build_gold.py >/tmp/nps_gold.log 2>&1 || {
  echo "FATAL: gold build failed"; cat /tmp/nps_gold.log; exit 2; }
grep -E '"nps_score"|"empirical_plan_accuracy_pct"' /tmp/nps_gold.log | head

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel
say "running four NPS-measurement agents (parallel, provider=$PROVIDER)"
python scripts/run_nps_agents__measure-api-consumer-satisfaction.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --max-concurrency 4 --dataset "$DATASET"
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/measure-api-consumer-satisfaction/score.py --workspace "$FOUNDRY" \
  --run-id "$RUN_ID" --dataset "$DATASET"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/measure-api-consumer-satisfaction/metric.json \
  --out-prefix results/leaderboard-measure-api-consumer-satisfaction

# 5. Stop only what we started
[ "$STARTED_PROXY" = "1" ] && { kill ${PROXYPID:-0} 2>/dev/null; sleep 1; kill -9 ${PROXYPID:-0} 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
