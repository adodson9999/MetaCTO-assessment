#!/usr/bin/env bash
# Phase 4 — create-postman-collection (n601) task: build the deterministic gold, run the
# four agents, score Postman Contract Fidelity vs gold, update the leaderboard.
# Self-contained. Re-runnable; each run appends.
#
# Fully air-gapped on the DATA side: n601 is a pure JSON->JSON transform — NO HTTP target,
# DummyJSON never touched or modified. The four agents read the registry FIXTURE
# (data/create-postman-collection/registry_fixture.json), each EMITS a Postman Generation
# Contract, and the shared harness applies it + builds + recursively counts the collection
# + runs Newman (isolated tools/newman). The LLM backend is OLLAMA per config.toml (the
# owner's explicit request).
#
# IMPORTANT (owner constraint): this script NEVER starts the Ollama server. It probes the
# configured endpoint and FATALs with instructions if it is not already running. Start it
# yourself first:  ollama serve   (with the configured model pulled).
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$FOUNDRY/.venv/bin:$PATH"
cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# 0. Backend sanity: this build uses ollama. Confirm provider + that the server is ALREADY
#    up. We do not launch it.
read -r PROVIDER OLLAMA_URL OLLAMA_MODEL < <(python - <<'PY'
import sys; sys.path.insert(0, "scripts")
import backend_config as b
s = b.resolve(".")
print(s["provider"], s["base_url"], s["native"]["model"])
PY
)
say "backend provider: ${PROVIDER}  model: ${OLLAMA_MODEL}"
if [ "$PROVIDER" = "ollama" ]; then
  PING_URL="${OLLAMA_URL%/v1}/api/tags"
  if ! curl -fsS "$PING_URL" >/dev/null 2>&1; then
    echo "FATAL: Ollama is not reachable at ${OLLAMA_URL}."
    echo "       This script does not start it. Run 'ollama serve' (and 'ollama pull ${OLLAMA_MODEL}') first."
    exit 2
  fi
elif [ "$PROVIDER" = "claude-haiku" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "FATAL: provider=claude-haiku but ANTHROPIC_API_KEY is not set."; exit 3
fi

# 0b. EverOS shared-memory pool (loopback, best-effort; harness has a local-file fallback).
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  if [ -x "$FOUNDRY/vendor/EverOS/.venv/bin/everos" ]; then
    say "starting EverOS memory pool on 127.0.0.1:8000"
    ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
        --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
    EVPID=$!
    for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
  fi
fi

# 1. Build / refresh the deterministic gold (no network).
say "building gold (deterministic reference; pure JSON->JSON, no network)"
python data/create-postman-collection/build_gold.py >/dev/null

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID  ·  backend: $PROVIDER"

# 2. Run the four agents in parallel.
say "running four create-postman-collection agents (parallel)"
python scripts/run_postman_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --max-concurrency "${FORGE_CONCURRENCY:-4}"
RC=$?

# 3. Score fidelity vs gold, then build the leaderboard.
say "scoring fidelity"
python judge/create-postman-collection/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/create-postman-collection/metric.json \
  --out-prefix results/leaderboard-create-postman-collection

# 4. Stop only what we started.
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, agents rc=$RC)"
