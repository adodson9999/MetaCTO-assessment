#!/usr/bin/env python3
# Used by: shared — CI chunk planner across all agents.
"""Generate the chunk-index JSON array for a GitHub Actions dynamic matrix.

Usage:
  python ci_gen_chunks.py <kind> [chunk_size]

Prints a JSON array of integers [0, 1, 2, ..., n_chunks-1] to stdout.
GHA reads this via: echo "chunks=$(python ci_gen_chunks.py api-tester 20)" >> $GITHUB_OUTPUT

Args:
  kind        Agent kind directory name under agents/ (e.g. "api-tester").
  chunk_size  Number of agents per chunk (default: 20).

Env vars:
  FORGE_WORKSPACE  path to agent-foundry root (default: current directory).
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WORKSPACE  = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
KIND       = sys.argv[1] if len(sys.argv) > 1 else "api-tester"
CHUNK_SIZE = int(sys.argv[2]) if len(sys.argv) > 2 else 20

agents_dir = WORKSPACE / "agents" / KIND
if not agents_dir.is_dir():
    print(f"[ci_gen_chunks] ERROR: directory not found: {agents_dir}", file=sys.stderr)
    sys.exit(1)

agents   = sorted(p.name for p in agents_dir.iterdir() if p.is_dir())
n_chunks = max(1, (len(agents) + CHUNK_SIZE - 1) // CHUNK_SIZE)

print(json.dumps(list(range(n_chunks))))
