#!/usr/bin/env bash
# Phase 4 — test-case-creator (n600) task: build the deterministic gold + the
# build-manifest fixtures, run the four agents on them, score Test Case Coverage Rate
# vs gold, update the leaderboard. Self-contained. Re-runnable; each run appends.
#
# Fully air-gapped on the DATA side: no HTTP target — the manifest + agent-node spec
# cards are local files and DummyJSON is never touched or modified. The LLM backend is
# OLLAMA per config.toml (the owner's explicit request).
#
# IMPORTANT (owner constraint): this script NEVER starts the Ollama server. It probes
# the configured endpoint and FATALs with instructions if it is not already running.
# Start it yourself first:  ollama serve   (with the configured model pulled).
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$FOUNDRY/.venv/bin:$PATH"
cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# 0. Backend sanity: this build uses ollama. Confirm provider + that the server is
#    ALREADY up. We do not launch it.
read -r PROVIDER OLLAMA_URL OLLAMA_MODEL < <(python - <<'PY'
import sys; sys.path.insert(0, "scripts")
import backend_config as b
s = b.resolve(".")
print(s["provider"], s["base_url"], s["native"]["model"])
PY
)
say "backend provider: ${PROVIDER}  model: ${OLLAMA_MODEL}"
if [ "$PROVIDER" != "ollama" ]; then
  echo "NOTE: provider is '${PROVIDER}', not ollama. Proceeding with the configured backend."
fi
if [ "$PROVIDER" = "ollama" ]; then
  PING_URL="${OLLAMA_URL%/v1}/api/tags"
  if ! curl -fsS "$PING_URL" >/dev/null 2>&1; then
    echo "FATAL: Ollama is not reachable at ${OLLAMA_URL}."
    echo "       This script does not start it. Run 'ollama serve' (and 'ollama pull ${OLLAMA_MODEL}') first."
    exit 2
  fi
fi

# 0b. EverOS shared-memory pool (loopback, best-effort; the harness has a local-file
#     fallback so a missing pool never fails the run).
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  if [ -x "$FOUNDRY/vendor/EverOS/.venv/bin/everos" ]; then
    say "starting EverOS memory pool on 127.0.0.1:8000"
    ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
        --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
    EVPID=$!
    for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
  fi
fi

# 1. Build / refresh the deterministic gold + fixtures (no network).
say "building gold + fixtures (deterministic reference; no network)"
python data/test-case-creator/build_gold.py >/dev/null

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 2. Run the four agents in parallel against the local manifest. Each emits
#    results/runs/<run>/<agent>.json and the harness writes the deterministic n600
#    deliverable (results/test-case-registry*.json).
say "running four test-case-creator agents (parallel)"
export FORGE_WORKSPACE="$FOUNDRY" FORGE_RUN_ID="$RUN_ID" FORGE_SANDBOX_ROOT="$FOUNDRY"
declare -A RUNNERS=(
  [langgraph]="agents/general-test-case-creator/langgraph/run.py"
  [crewai]="agents/general-test-case-creator/crewai/run.py"
  [claude_sdk]="agents/general-test-case-creator/claude_sdk/run.py"
  [general-test-case-creator]="agents/general-test-case-creator/subagent/run.py"
)
pids=()
for name in "${!RUNNERS[@]}"; do
  ( FORGE_AGENT="$name" python "${RUNNERS[$name]}" >"results/runs/$RUN_ID.$name.log" 2>&1 ) &
  pids+=($!)
done
RC=0
for p in "${pids[@]}"; do wait "$p" || RC=1; done

# 3. Build the leaderboard from the four emitted metric JSONs.
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-case-creator/metric.json \
  --out-prefix results/leaderboard-test-case-creator

# 4. Stop only what we started.
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, agents rc=$RC). Deliverable: results/test-case-registry.json"
