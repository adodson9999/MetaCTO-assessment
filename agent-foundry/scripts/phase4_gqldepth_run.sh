#!/usr/bin/env bash
# Phase 4 — GraphQL-depth-limit task: run the four agents against the LOCAL GraphQL
# depth SUT (READ-ONLY queries), score fidelity vs gold, update the leaderboard.
#
# BACKEND = OLLAMA (air-gapped) per the owner's switch on 2026-06-25, reversing the
# earlier "use the claude option, not ollama" instruction for this task. FORGE_PROVIDER
# defaults to ollama below; ollama is natively OpenAI-compatible at :11434/v1, so NO
# proxy/shim is needed — langgraph (ChatOllama), crewai (ollama/<model>), and claude_sdk
# + the subagent (the /v1 chat/completions path) all reach it directly. Override per-run
# with FORGE_PROVIDER=claude-haiku to use Claude instead (that path still starts the
# LiteLLM proxy / stdlib Anthropic shim, below). Ollama is NOT started by this script —
# start it yourself (`ollama serve`) before a real run.
#
# The system-under-test is a purpose-built, air-gapped local GraphQL server that
# enforces a documented maximum query depth (tools/graphql-depth-server). DummyJSON is
# NEVER used or modified by this task — there is no DummyJSON in this pipeline at all.
#
# Self-contained + re-runnable; each run appends to the leaderboard.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8940}"   # override with FORGE_TARGET_PORT if this collides
BASE="http://localhost:${PORT}"
PROXY_PORT="${FORGE_LITELLM_PORT:-4000}"
export FORGE_TARGET_BASE_URL="$BASE"
# BACKEND switch: ollama by default (the owner's switch); override per-run with
# FORGE_PROVIDER=claude-haiku for the Claude path.
export FORGE_PROVIDER="${FORGE_PROVIDER:-ollama}"
export PATH="$FOUNDRY/.venv/bin:$PATH"
OLLAMA_BASE="${FORGE_OLLAMA_BASE_URL:-http://127.0.0.1:11434/v1}"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }

# 1. Backend reachability + (Claude only) the OpenAI-compatible shim for claude_sdk +
#    subagent. Under ollama NO shim is needed — ollama is natively OpenAI-compatible.
STARTED_PROXY=0
if [ "$FORGE_PROVIDER" = "claude-haiku" ]; then
  if [ -z "${ANTHROPIC_API_KEY:-}" ]; then
    echo "FATAL: ANTHROPIC_API_KEY is not set; the Claude backend cannot run." >&2
    exit 2
  fi
  #    Preferred: the documented LiteLLM proxy (needs litellm[proxy]/fastapi). When that
  #    dependency is absent, fall back to the dependency-light stdlib OpenAI->Anthropic
  #    shim (tools/openai-anthropic-shim, stdlib + the already-present anthropic SDK).
  #    Both expose POST /chat/completions + /health/liveliness, so the agents are unchanged.
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
else
  # ollama backend: natively OpenAI-compatible at :11434/v1 — NO shim. All four
  # frameworks reach it directly. Ollama is NOT started here (per the owner: "no reason
  # to start the ollama server right now"); this check only fires when you actually run
  # the pipeline, telling you to start ollama first.
  if ! curl -fsS "${OLLAMA_BASE%/v1}/api/tags" >/dev/null 2>&1; then
    echo "FATAL: ollama backend selected but ollama is not reachable at ${OLLAMA_BASE%/v1}." >&2
    echo "       Start it first:  ollama serve   (then: ollama pull ${FORGE_OLLAMA_MODEL:-qwen2.5:14b-instruct})" >&2
    echo "       Or run on Claude: FORGE_PROVIDER=claude-haiku bash scripts/phase4_gqldepth_run.sh" >&2
    exit 2
  fi
fi

# 2. Local GraphQL depth SUT up (air-gapped). Only reuse the port if it is OUR SUT
#    (health body carries service="graphql-depth-server"); a foreign server squatting
#    the port is refused so the agents never test the wrong target.
is_our_sut(){ curl -fsS "$BASE/__health" 2>/dev/null | grep -q '"service": *"graphql-depth-server"'; }
STARTED_SUT=0
if ! is_our_sut; then
  if curl -fsS "$BASE/__health" >/dev/null 2>&1; then
    echo "FATAL: port $PORT is occupied by a different server (not graphql-depth-server)." >&2
    echo "       Set FORGE_TARGET_PORT to a free port and re-run." >&2
    exit 2
  fi
  say "starting local GraphQL depth SUT on :$PORT (read-only, /graphql max=7, /graphql-strict max=4)"
  nohup python tools/graphql-depth-server/server.py --host 127.0.0.1 --port "$PORT" \
      >/tmp/gqldepth_sut.log 2>&1 &
  SUTPID=$!; STARTED_SUT=1
  for i in $(seq 1 20); do is_our_sut && break; sleep 1; done
fi
is_our_sut || { echo "FATAL: local SUT not up"; exit 2; }

# 3. (Re)build gold from the live SUT (read-only) so fidelity scores against current truth
say "building gold (reference 4-probe plan + read-only GraphQL queries)"
BASE_URL="$BASE" python data/validate-graphql-depth-limits/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 4. Run the four in parallel
say "running four GraphQL-depth agents (parallel, backend=$FORGE_PROVIDER)"
python scripts/run_gqldepth_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 5. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/validate-graphql-depth-limits/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/validate-graphql-depth-limits/metric.json \
  --out-prefix results/leaderboard-validate-graphql-depth-limits

# 6. Stop only what we started
[ "$STARTED_SUT" = "1" ] && { kill ${SUTPID:-0} 2>/dev/null; sleep 1; kill -9 ${SUTPID:-0} 2>/dev/null; }
[ "$STARTED_PROXY" = "1" ] && { kill ${PROXYPID:-0} 2>/dev/null; sleep 1; kill -9 ${PROXYPID:-0} 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
