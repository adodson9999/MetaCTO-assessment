#!/usr/bin/env bash
# CI test stage (§7.6) for the unverified-bug feature.
#
# Runs the pure-Python unit suite (no model / no backend) then the unverified-bug gate in
# dry-run. Both must be green before any model-dependent pipeline step. Exit non-zero on the
# first failure so CI blocks the merge.
#
# Usage:  scripts/run_unit_and_gate.sh [RUN_ID]
#   RUN_ID (optional): if given, the gate checks that materialised run; otherwise --dry-run.
set -euo pipefail

WS="$(cd "$(dirname "$0")/.." && pwd)"
cd "$WS"

# Prefer a python that has pytest (the .venv is for the pipeline; pytest ships with the host).
PY="${FORGE_TEST_PYTHON:-python3}"
if ! "$PY" -c 'import pytest' >/dev/null 2>&1; then
  echo "ERROR: no pytest for '$PY'. Set FORGE_TEST_PYTHON to an interpreter with pytest." >&2
  exit 2
fi

echo "== [1/2] unit suite: pytest -m unit tests/unit =="
"$PY" -m pytest -m unit tests/unit \
  agents/general/bug-reporter/forge-gate -q

echo "== [2/2] unverified-bug gate =="
GATE="agents/general/bug-reporter/forge-gate/unverified_bug_gate.py"
if [ "${1:-}" != "" ]; then
  "$PY" "$GATE" --workspace "$WS" --run-id "$1"
else
  "$PY" "$GATE" --workspace "$WS" --dry-run
fi

echo "OK: unit suite + unverified-bug gate passed."
