#!/usr/bin/env bash
# Phase 4 — SSL/TLS-enforcement task: start the local TLS fixture in front of the
# unmodified DummyJSON, build gold (handshake + read-only GET), run the four agents,
# score fidelity vs gold, and update the leaderboard.
#
# BACKEND = OLLAMA (local/air-gapped) per the user's request after the Anthropic credit
# balance was exhausted. The four agents elicit plans from the local Ollama endpoint
# (config.toml [backend].provider = "ollama", model qwen2.5:14b-instruct). The provider is
# taken from config.toml; override per-run with FORGE_PROVIDER if needed.
#
# IMPORTANT: this script does NOT start the Ollama server — start it yourself first
# (`ollama serve`, with the model pulled) before running. The script only checks it is up.
#
# DummyJSON is NEVER modified — only handshakes + read-only GETs hit the local fixture.
set -uo pipefail

FOUNDRY="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
TARGET_REPO="$(cd "$FOUNDRY/.." && pwd)"
UPSTREAM_PORT="${FORGE_UPSTREAM_PORT:-8899}"
# Honor an explicit FORGE_PROVIDER override; otherwise let config.toml drive (ollama).
export PATH="$FOUNDRY/.venv/bin:$PATH"
PY="$FOUNDRY/.venv/bin/python"
FX="$FOUNDRY/data/test-ssl-tls-enforcement/tls_fixture.py"

cd "$FOUNDRY"
say(){ printf "\033[1;36m▸ %s\033[0m\n" "$*"; }
# ── LLM provider (single source: scripts/llm_config.py) ──────────────────
eval "$(python scripts/llm_config.py --export)"
say "LLM backend: $FORGE_PROVIDER  model: $FORGE_MODEL"
# ──────────────────────────────────────────────────────────────

# Backend preflight (does NOT start anything). For the local Ollama backend, just confirm
# the server is reachable; for an explicit claude-haiku override, require the API key.
PROVIDER="$(FORGE_PROVIDER="${FORGE_PROVIDER:-}" "$PY" -c 'import sys; sys.path.insert(0,"scripts"); import backend_config; print(backend_config.resolve(__import__("pathlib").Path(".")).get("provider"))')"
say "backend provider: $PROVIDER"
if [ "$PROVIDER" = "ollama" ]; then
  OLLAMA_URL="$(grep -E '^ollama_base_url' config.toml | sed -E 's/.*"(.*)".*/\1/')"
  if ! curl -fsS "${OLLAMA_URL%/v1}/api/tags" >/dev/null 2>&1; then
    echo "FATAL: Ollama is not reachable at ${OLLAMA_URL}. Start it first: ollama serve" >&2
    echo "       (this script does not start the Ollama server)." >&2
    exit 2
  fi
elif [ "$PROVIDER" = "claude-haiku" ] && [ -z "${ANTHROPIC_API_KEY:-}" ]; then
  echo "FATAL: provider is claude-haiku but ANTHROPIC_API_KEY is not set." >&2
  exit 2
fi

# 1. Upstream DummyJSON up (air-gapped: no Mongo). Only started if not already running.
STARTED_DJ=0
if ! curl -fsS "http://localhost:${UPSTREAM_PORT}/test" >/dev/null 2>&1; then
  say "starting DummyJSON on :$UPSTREAM_PORT (read-only upstream)"
  ( cd "$TARGET_REPO" && JWT_SECRET=forge_test_secret MONGODB_URI= NODE_ENV=development \
      PORT="$UPSTREAM_PORT" LOG_ENABLED=false node index.js >/tmp/dummyjson.log 2>&1 ) &
  DJPID=$!; STARTED_DJ=1
  for i in $(seq 1 20); do curl -fsS "http://localhost:${UPSTREAM_PORT}/test" >/dev/null 2>&1 && break; sleep 1; done
fi
curl -fsS "http://localhost:${UPSTREAM_PORT}/test" >/dev/null 2>&1 || { echo "FATAL: upstream not up"; exit 2; }

# 2. TLS fixture up (CA + leaf cert generated on first run).
say "starting local TLS fixture (TLS 1.2/1.3 only, CA-signed, HTTP->HTTPS redirect)"
"$PY" "$FX" start

# 3. Refresh gold from the live fixture (handshake + read-only GET).
say "building gold"
"$PY" data/test-ssl-tls-enforcement/build_gold.py

RUN_ID="${1:-$($PY -c 'import uuid,datetime;print(datetime.datetime.utcnow().strftime("%Y%m%dT%H%M%S")+"-"+uuid.uuid4().hex[:6])')}"
say "run id: $RUN_ID"

# 4. Run the four in parallel.
say "running four SSL/TLS agents (parallel, $PROVIDER)"
"$PY" scripts/run_tls_agents__test-ssl-tls-enforcement.py --workspace "$FOUNDRY" --run-id "$RUN_ID" --max-concurrency 4
RC=$?

# 5. Score fidelity vs gold, then build the over-time leaderboard.
say "scoring TLS-Test Fidelity vs gold"
"$PY" judge/test-ssl-tls-enforcement/score.py --workspace "$FOUNDRY" --run-id "$RUN_ID"
"$PY" scripts/judge_score.py --workspace "$FOUNDRY" --run-id "$RUN_ID" \
  --metric judge/test-ssl-tls-enforcement/metric.json \
  --out-prefix results/test-ssl-tls-enforcement/leaderboard

# 6. Stop only what we started (leave the fixture up for re-runs unless we own DummyJSON).
[ "$STARTED_DJ" = "1" ] && { kill ${DJPID:-0} 2>/dev/null; sleep 1; kill -9 ${DJPID:-0} 2>/dev/null; }
say "done (run $RUN_ID, run_agents rc=$RC). Fixture left running; stop with: $PY $FX stop"
