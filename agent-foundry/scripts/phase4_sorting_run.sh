#!/usr/bin/env bash
# Phase 4 — sorting-behavior task: run the four agents, each seeding an ISOLATED
# in-process reference resource and verifying ordering with read-only GETs, score
# fidelity vs gold, update the leaderboard.
#
# BACKEND = OLLAMA (local, air-gapped). Set via the FORGE_PROVIDER env override so the
# foundry's global config.toml default is unaffected for other tasks. All four agents
# reach Ollama's native OpenAI-compatible endpoint: langgraph via ChatOllama, crewai
# via "ollama/<model>", and claude_sdk + the subagent via the local /v1 chat endpoint.
# No LiteLLM proxy and no ANTHROPIC_API_KEY are needed on this path.
#
# This script does NOT start the Ollama server. Start it yourself (e.g. `ollama serve`)
# before running; the script only checks reachability and stops with a clear message if
# Ollama is not up.
#
# DummyJSON is NOT used or started by this task — it cannot be seeded read-only and
# has no created_at field, so seeding it would violate the read-only-target invariant.
# The reference resource is in-process, loopback-only, GET-only, and torn down per run.
#
# Self-contained + re-runnable; each run appends to the leaderboard.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
OLLAMA_BASE="${FORGE_OLLAMA_BASE_URL:-http://127.0.0.1:11434/v1}"
export PATH="$FOUNDRY/.venv/bin:$PATH"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# 1. Ollama reachability — checked, NOT started. (Server start is the user's job.)
OLLAMA_ROOT="${OLLAMA_BASE%/v1}"
if [ "$FORGE_PROVIDER" = "ollama" ]; then
  if ! curl -fsS "${OLLAMA_ROOT}/api/tags" >/dev/null 2>&1; then
    echo "FATAL: Ollama is not reachable at ${OLLAMA_ROOT}." >&2
    echo "       This script does not start it — run 'ollama serve' (and pull the model" >&2
    echo "       in config.toml [backend].ollama_model), then re-run." >&2
    exit 2
  fi
fi
say "Ollama reachable at ${OLLAMA_ROOT} (server not started by this script)"

# 2. Refresh gold (seeds an isolated reference resource; no external target, no LLM).
say "building gold (isolated reference resource, read-only GETs)"
python data/verify-sorting-behavior/build_gold.py

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 3. Run the four in parallel
say "running four sorting agents (parallel, ollama)"
python scripts/run_sorting_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 4. Score fidelity vs gold, then build the leaderboard
say "scoring fidelity"
python judge/verify-sorting-behavior/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/verify-sorting-behavior/metric.json \
  --out-prefix results/leaderboard-verify-sorting-behavior

say "done (run $RUN_ID, run_agents rc=$RC)"
