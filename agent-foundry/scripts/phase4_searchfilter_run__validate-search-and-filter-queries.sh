#!/usr/bin/env bash
# Phase 4 — search-and-filter-query task: run the four agents against the LOCAL seeded
# /resources SUT (READ-ONLY), score fidelity vs gold, update the leaderboard.
#
# BACKEND = CLAUDE (per the build request: "don't use ollama here, just the claude
# option"). This is set via the FORGE_PROVIDER env override so the foundry's global
# config.toml provider is honored while THIS run pins claude-haiku. langgraph + crewai
# reach claude-haiku natively (Anthropic SDK); claude_sdk + the subagent reach it
# through the central LiteLLM proxy (the documented OpenAI-compatible shim) started below.
#
# The system-under-test is a purpose-built, air-gapped local server seeded with exactly
# the task's 20 records (tools/filter-resource-server). DummyJSON is NEVER used or
# modified by this task — there is no DummyJSON in this pipeline at all.
#
# Self-contained + re-runnable; each run appends to the leaderboard.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${FORGE_TARGET_PORT:-8931}"   # override with FORGE_TARGET_PORT if this collides
BASE="http://localhost:${PORT}"
PROXY_PORT="${FORGE_LITELLM_PORT:-4000}"
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

# 1. OpenAI-compatible shim for claude_sdk + subagent.
#    Preferred: the documented LiteLLM proxy (needs litellm[proxy]/fastapi). When that
#    dependency is absent, fall back to the dependency-light stdlib OpenAI->Anthropic
#    shim (tools/openai-anthropic-shim, stdlib + the already-present anthropic SDK).
#    Both expose POST /chat/completions + /health/liveliness, so the agents are unchanged.
STARTED_PROXY=0
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

# 2. Local seeded /resources SUT up (air-gapped). Only reuse the port if it is OUR
#    SUT (health body carries service="filter-resource-server"); a foreign server
#    squatting the port is refused so the agents never test the wrong target.
is_our_sut(){ curl -fsS "$BASE/__health" 2>/dev/null | grep -q '"service": *"filter-resource-server"'; }
STARTED_SUT=0
if ! is_our_sut; then
  if curl -fsS "$BASE/__health" >/dev/null 2>&1; then
    echo "FATAL: port $PORT is occupied by a different server (not filter-resource-server)." >&2
    echo "       Set FORGE_TARGET_PORT to a free port and re-run." >&2
    exit 2
  fi
  say "starting local filter SUT on :$PORT (read-only, seeded with the 20 records)"
  nohup python tools/filter-resource-server/server.py --host 127.0.0.1 --port "$PORT" \
      >/tmp/filter_sut.log 2>&1 &
  SUTPID=$!; STARTED_SUT=1
  for i in $(seq 1 20); do is_our_sut && break; sleep 1; done
fi
is_our_sut || { echo "FATAL: local SUT not up"; exit 2; }

# 3. (Re)build gold from the live SUT (read-only) so fidelity scores against current truth
say "building gold (seed-derived counts + read-only GETs)"
BASE_URL="$BASE" python data/validate-search-and-filter-queries/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 4. Run the four in parallel
say "running four search-and-filter agents (parallel, claude-haiku)"
python scripts/run_searchfilter_agents__validate-search-and-filter-queries.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 5. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/validate-search-and-filter-queries/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/validate-search-and-filter-queries/metric.json \
  --out-prefix results/leaderboard-validate-search-and-filter-queries

# 6. Stop only what we started
[ "$STARTED_SUT" = "1" ] && { kill ${SUTPID:-0} 2>/dev/null; sleep 1; kill -9 ${SUTPID:-0} 2>/dev/null; }
[ "$STARTED_PROXY" = "1" ] && { kill ${PROXYPID:-0} 2>/dev/null; sleep 1; kill -9 ${PROXYPID:-0} 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
