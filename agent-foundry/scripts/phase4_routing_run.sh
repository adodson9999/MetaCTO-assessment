#!/usr/bin/env bash
# Phase 4 — api-gateway-routing task: run the four agents against the local routing
# fixture, score plan-fidelity vs gold, update the leaderboard. Re-runnable; each run
# appends to the leaderboard. DummyJSON is NEVER touched — this task uses a separate,
# purpose-built, air-gapped local fixture (a gateway + 3 WireMock-equivalent mock
# backends with /__admin/requests journals) under tools/routing-gateway/.
#
# Backend: the CENTRAL switch in config.toml ([backend].provider) is authoritative —
# this script derives FORGE_PROVIDER from it (override by exporting FORGE_PROVIDER).
#   - ollama      : local/air-gapped; this script does NOT start the Ollama server
#                   (start it yourself: `ollama serve`).
#   - claude-cli  : claude.ai SUBSCRIPTION via `claude -p` behind an OpenAI-compatible
#                   shim (scripts/claude_cli_shim.py) — used when ANTHROPIC_API_KEY has
#                   no credit; this script starts the shim.
#   - claude-haiku: funded Anthropic API key.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
GW_PORT="${FORGE_GATEWAY_PORT:-8920}"
SHIM_PORT="${FORGE_SHIM_PORT:-8787}"
BASE="http://127.0.0.1:${GW_PORT}"
export FORGE_TARGET_BASE_URL="$BASE"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }

# Provider comes from config.toml unless explicitly overridden in the environment.
CFG_PROVIDER="$(python -c "import tomllib,pathlib;print(tomllib.loads(pathlib.Path('config.toml').read_text()).get('backend',{}).get('provider','ollama'))" 2>/dev/null || echo ollama)"
export FORGE_PROVIDER="${FORGE_PROVIDER:-$CFG_PROVIDER}"
export FORGE_CLAUDE_CLI_SHIM_URL="http://127.0.0.1:${SHIM_PORT}/v1"
say "backend provider = $FORGE_PROVIDER (from ${FORGE_PROVIDER:+env or }config.toml)"

# 0a. Backend precondition.
if [ "$FORGE_PROVIDER" = "claude-haiku" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "FATAL: FORGE_PROVIDER=claude-haiku but ANTHROPIC_API_KEY is not set."; exit 3
fi
if [ "$FORGE_PROVIDER" = "claude-cli" ] && ! command -v claude >/dev/null 2>&1; then
  echo "FATAL: FORGE_PROVIDER=claude-cli but the claude CLI is not on PATH."; exit 3
fi
if [ "$FORGE_PROVIDER" = "ollama" ] && ! curl -fsS http://127.0.0.1:11434/api/tags >/dev/null 2>&1; then
  echo "WARN: FORGE_PROVIDER=ollama but the Ollama server is not reachable at :11434."
  echo "      This script does NOT start it — run \`ollama serve\` first, then re-run."
fi

# 0b. Claude-CLI shim up (only for the claude-cli provider; wraps `claude -p` subscription).
STARTED_SHIM=0
if [ "$FORGE_PROVIDER" = "claude-cli" ]; then
  if ! curl -fsS "http://127.0.0.1:${SHIM_PORT}/v1/models" >/dev/null 2>&1; then
    say "starting claude-cli shim on 127.0.0.1:${SHIM_PORT} (wraps \`claude -p\` subscription)"
    ( python scripts/claude_cli_shim.py --port "$SHIM_PORT" --model claude-haiku-4-5 \
        >/tmp/claude_shim.log 2>&1 ) &
    SHIMPID=$!; STARTED_SHIM=1
    for i in $(seq 1 20); do curl -fsS "http://127.0.0.1:${SHIM_PORT}/v1/models" >/dev/null 2>&1 && break; sleep 1; done
  fi
  curl -fsS "http://127.0.0.1:${SHIM_PORT}/v1/models" >/dev/null 2>&1 || { echo "FATAL: shim not up"; exit 4; }
fi

# 1. EverOS shared-memory pool up (loopback, best-effort — note-writing is non-fatal)
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  say "starting EverOS memory pool on 127.0.0.1:8000 (best-effort)"
  ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
      --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
  EVPID=$!
  for i in $(seq 1 15); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
fi

# 2. Local routing fixture up (gateway + 3 mock backends). Only started if not running.
STARTED_FX=0
if ! curl -fsS "$BASE/__health" >/dev/null 2>&1; then
  say "starting routing-gateway fixture on :$GW_PORT (gateway + users/orders/payments mocks)"
  ( "$FOUNDRY/.venv/bin/python" "$FOUNDRY/tools/routing-gateway/run_fixture.py" \
      --gateway-port "$GW_PORT" >/tmp/routing_fixture.log 2>&1 ) &
  FXPID=$!; STARTED_FX=1
  for i in $(seq 1 20); do curl -fsS "$BASE/__health" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "$BASE/__health" >/dev/null 2>&1 || { echo "FATAL: routing fixture not up"; exit 2; }

# 2b. Refresh gold from the live fixture (real execution + journal reads) so fidelity
#     scores against current truth.
say "building gold (reference plans -> gateway -> backend journals)"
FORGE_TARGET_BASE_URL="$BASE" python data/test-api-gateway-routing/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four agents SEQUENTIALLY (--max-concurrency 1). They share ONE stateful
#    fixture whose backend journals are reset before each call; concurrent agents would
#    reset each other's journals mid-call (a cross-agent race). FORGE_CONCURRENCY can
#    override if each agent is ever given its own fixture.
CONC="${FORGE_CONCURRENCY:-1}"
say "running four routing agents (concurrency=$CONC)"
python scripts/run_routing_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency "$CONC"
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/test-api-gateway-routing/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-api-gateway-routing/metric.json \
  --out-prefix results/leaderboard-test-api-gateway-routing

# 5. Stop only what we started
[ "$STARTED_FX" = "1" ] && { kill ${FXPID:-0} 2>/dev/null; sleep 1; kill -9 ${FXPID:-0} 2>/dev/null; }
[ "$STARTED_SHIM" = "1" ] && { kill ${SHIMPID:-0} 2>/dev/null; sleep 1; kill -9 ${SHIMPID:-0} 2>/dev/null; }
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
