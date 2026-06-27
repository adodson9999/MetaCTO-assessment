#!/usr/bin/env bash
# Phase 4 — track-defect-density task: build the deterministic gold, run the four
# agents on the local sprint fixtures, score Report Accuracy vs gold, update the
# leaderboard. Self-contained. Re-runnable; each run appends to the leaderboard.
#
# Fully air-gapped on the DATA side: no Jira, no Git, no HTTP target — the fixtures
# are local files and DummyJSON is never touched. The only non-local element is the
# LLM backend, set to claude-haiku per config.toml (the user's explicit opt-in:
# "don't use ollama here, just the claude option").
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
export PATH="$FOUNDRY/.venv/bin:$PATH"
cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# 0. Backend sanity: this build requires claude-haiku (no ollama).
PROVIDER="$(python -c 'import sys;sys.path.insert(0,"scripts");import backend_config as b;print(b.resolve(".")["provider"])' 2>/dev/null)"
say "backend provider: ${PROVIDER}"
if [ "$PROVIDER" = "claude-haiku" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "FATAL: provider=claude-haiku but ANTHROPIC_API_KEY is unset."; exit 2
fi

# 0b. EverOS shared-memory pool up (loopback, best-effort; the harness also has a
#     local-file fallback so a missing pool never fails the run).
if ! curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1; then
  if [ -x "$FOUNDRY/vendor/EverOS/.venv/bin/everos" ]; then
    say "starting EverOS memory pool on 127.0.0.1:8000"
    ( cd "$FOUNDRY/vendor/EverOS" && .venv/bin/everos server start --host 127.0.0.1 \
        --port 8000 --log-level ERROR >/tmp/everos.log 2>&1 ) &
    EVPID=$!
    for i in $(seq 1 20); do curl -fsS http://127.0.0.1:8000/health >/dev/null 2>&1 && break; sleep 1; done
  fi
fi

# 1. Build / refresh the deterministic gold (authors fixtures + reference records).
say "building gold (deterministic reference; no network)"
python data/track-defect-density/build_gold.py >/dev/null

RUN_ID="${1:-$(python -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 2. Run the four in parallel (Claude Haiku is contention-free at concurrency 4).
say "running four defect-density agents (parallel)"
python scripts/run_defectdensity_agents.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --max-concurrency "${FORGE_CONCURRENCY:-4}"
RC=$?

# 3. Score accuracy vs gold, then build the leaderboard.
say "scoring accuracy vs gold"
python judge/track-defect-density/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
say "updating leaderboard"
python scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/track-defect-density/metric.json \
  --out-prefix results/leaderboard-track-defect-density

# 4. Stop only what we started.
[ -n "${EVPID:-}" ] && { kill $EVPID 2>/dev/null; sleep 1; kill -9 $EVPID 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC)"
