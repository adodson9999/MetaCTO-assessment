#!/usr/bin/env python3
"""forge — thin CLI wrapper over the foundry scripts (references/cli.md).

The skill is the brain; this CLI just dispatches to the same deterministic scripts
so the workflow runs from a terminal or CI. Routine commands run without asking
permission; only the debate gate and a guardrail failure halt (constitution
Article V). Exit code is the contract: 0 = pass, non-zero = a gate/guardrail
failure that should hard-halt the caller.

Usage: forge <command> [args]   (run `forge help` for the table)
"""
from __future__ import annotations

import subprocess
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
PY = sys.executable

# command -> (script, default args). None script = handled inline.
MAP = {
    "init":        ("init_workspace.py", []),
    "data":        ("data_profile.py", []),
    "analyze":     ("analyze.py", []),
    "judge":       ("run_agents.py", []),
    "improve":     ("improve_loop.py", []),
    "verify":      ("verify_build.py", []),
    "test":        ("golden_run.py", []),
    "determinism": ("determinism_check.py", []),
    "quality":     ("slop_scan.py", ["--fail-below", "95"]),
    "files":       ("verify_files.py", []),
    "fight-camp":  ("fight_camp.py", []),
    "evolve":      ("evolve.py", []),
}

PIPELINE = ["init", "data", "build", "analyze", "judge", "improve", "verify", "test"]


def run(cmd: str, rest: list[str]) -> int:
    if cmd in ("help", "-h", "--help", ""):
        print(__doc__)
        for k, (s, _) in MAP.items():
            print(f"  forge {k:<12} -> scripts/{s}")
        print("  forge build         -> author agents through the debate gate (model-driven)")
        print("  forge build-all     -> run the full pipeline, stop on first failure")
        return 0
    if cmd == "build":
        print("forge build: author the four agents one line at a time through the "
              "debate gate (references/debate-gate.md). Model-driven; run inside the skill.")
        return 0
    if cmd == "build-all":
        for step in PIPELINE:
            rc = run(step, [])
            if rc != 0:
                print(f"\nforge build-all halted at '{step}' (exit {rc}).")
                return rc
        return 0
    if cmd not in MAP:
        print(f"unknown command: {cmd}. Try `forge help`.")
        return 2
    script, default = MAP[cmd]
    path = HERE / script
    if not path.is_file():
        print(f"forge {cmd}: {script} not found in workspace scripts/.")
        return 1
    return subprocess.run([PY, str(path), *default, *rest]).returncode


def main() -> int:
    args = sys.argv[1:]
    cmd = args[0] if args else "help"
    return run(cmd, args[1:])


if __name__ == "__main__":
    sys.exit(main())
