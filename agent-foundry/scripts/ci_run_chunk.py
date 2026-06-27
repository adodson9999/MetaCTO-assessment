#!/usr/bin/env python3
"""Run one chunk of agents sequentially: G1 (harness) → G1b (test-case-creator) → gate.

Each agent in the chunk runs to completion before the next starts.
All failures are collected and reported at the end; the job exits 1 if any failed.

Env vars (all required in CI):
  FORGE_WORKSPACE    path to agent-foundry root
  FORGE_RUN_ID       run identifier (e.g. github.run_id)
  FORGE_KIND         agent kind directory (default: "api-tester")
  FORGE_CHUNK_INDEX  zero-based index of this chunk (default: 0)
  FORGE_CHUNK_SIZE   number of agents per chunk (default: 20)
  FORGE_PROVIDER     backend provider (e.g. "claude-haiku")
  ANTHROPIC_API_KEY  Anthropic API key (required when FORGE_PROVIDER=claude-haiku)
"""
from __future__ import annotations

import os
import subprocess
import sys
from pathlib import Path

WORKSPACE   = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
RUN_ID      = os.environ.get("FORGE_RUN_ID", "manual")
KIND        = os.environ.get("FORGE_KIND", "api-tester")
CHUNK_INDEX = int(os.environ.get("FORGE_CHUNK_INDEX", "0"))
CHUNK_SIZE  = int(os.environ.get("FORGE_CHUNK_SIZE", "20"))

# Discover agents from the filesystem — same sort order as ci_gen_chunks.py.
agents_dir = WORKSPACE / "agents" / KIND
all_agents = sorted(p.name for p in agents_dir.iterdir() if p.is_dir())
start      = CHUNK_INDEX * CHUNK_SIZE
chunk      = all_agents[start : start + CHUNK_SIZE]

if not chunk:
    print(f"[ci_run_chunk] chunk {CHUNK_INDEX} is empty — nothing to do", file=sys.stderr)
    sys.exit(0)

print(
    f"[ci_run_chunk] chunk {CHUNK_INDEX}: {len(chunk)} agent(s) "
    f"(agents {start}–{start + len(chunk) - 1} of {len(all_agents)})"
)

base_env = {**os.environ, "FORGE_WORKSPACE": str(WORKSPACE), "FORGE_RUN_ID": RUN_ID}
failures: list[str] = []


def run(cmd: list[str], env: dict) -> int:
    """Run a subprocess and return its exit code."""
    result = subprocess.run(cmd, env=env)
    return result.returncode


for agent in chunk:
    full_name = f"{KIND}-{agent}"
    print(f"\n── {full_name} ──────────────────────────────────────")

    # ------------------------------------------------------------------
    # G1: run the api-tester agent harness.
    # Writes staging findings to results/runs/{RUN_ID}/staging/{full_name}/
    # ------------------------------------------------------------------
    g1_rc = run(
        [sys.executable, str(WORKSPACE / "agents" / KIND / agent / "subagent" / "run.py")],
        env=base_env,
    )
    if g1_rc != 0:
        failures.append(f"{full_name}: G1 agent run failed (exit {g1_rc})")
        continue   # skip G1b and gate — no staging files were written

    # ------------------------------------------------------------------
    # G1b: run test-case-creator scoped to this agent.
    # FORGE_TESTCASE_AGENT (Change D1) limits agent_cfgs() to one entry.
    # Change D3 auto-loads staged findings as staging_prefix.
    # Change B2 retries up to 3 times; writes ERROR sentinel on total failure.
    # We do not abort on non-zero exit — the gate step captures the outcome.
    # ------------------------------------------------------------------
    tc_env = {**base_env, "FORGE_TESTCASE_AGENT": full_name}
    run(
        [sys.executable,
         str(WORKSPACE / "agents/general/test-case-creator/subagent/run.py")],
        env=tc_env,
    )

    # ------------------------------------------------------------------
    # Gate: ci_report_cases.py reads test-case-registry.json filtered to
    # this agent. Exits 1 if an ERROR sentinel is present or cases == 0.
    # ------------------------------------------------------------------
    gate_rc = run(
        [sys.executable, str(WORKSPACE / "scripts" / "ci_report_cases.py")],
        env=tc_env,
    )
    if gate_rc != 0:
        failures.append(f"{full_name}: test-case gate failed")


# ------------------------------------------------------------------
# Summary
# ------------------------------------------------------------------
passed = len(chunk) - len(failures)
print(f"\n[ci_run_chunk] chunk {CHUNK_INDEX} complete: {passed}/{len(chunk)} passed")

if failures:
    print(f"[ci_run_chunk] FAILURES in chunk {CHUNK_INDEX}:", file=sys.stderr)
    for f in failures:
        print(f"  {f}", file=sys.stderr)
    sys.exit(1)

sys.exit(0)
