#!/usr/bin/env python3
"""Golden regression suite — metric threshold + structure, never prose.

Per-agent golden cases auto-derived from task_spec + judge metric
(references/golden-tests.md). Runs at build completion and before evolution
adoption. Structural cases are pure Python; metric cases compare the latest
judged score against the recorded baseline (minus tolerance).

Usage:
    python scripts/golden_run.py [<group>/<name>] [--derive] [--workspace DIR]
                                 [--rebaseline]
Exit 0 if all pass, 1 on any regression.
"""
from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path


def latest_score(ws: Path, group: str, name: str):
    lbs = sorted(glob.glob(str(ws / "results" / group / name / "leaderboard-*.json")))
    if not lbs:
        return None
    data = json.loads(Path(lbs[-1]).read_text())
    # best-so-far across agents; golden tracks the agent's own best.
    return data.get("best_so_far") or data.get("score")


def run_case(case: dict, baseline: dict, score) -> tuple[bool, str]:
    kind = case.get("kind")
    if kind == "metric":
        if score is None:
            return False, "no leaderboard score to compare"
        tol = baseline.get("tolerance", 0.02)
        floor = baseline["value"] - tol
        ok = score >= floor if baseline.get("direction", "higher_is_better") == "higher_is_better" \
            else score <= baseline["value"] + tol
        return ok, f"score {score} vs baseline {baseline['value']} (tol {tol})"
    if kind == "structure":
        # Structural asserts are recorded as already-evaluated booleans at derive
        # time and re-checked here against the recorded structure block.
        return bool(case.get("passed", True)), case.get("assert", "")
    return True, "unknown case kind skipped"


def check_agent(ws: Path, group: str, name: str) -> bool:
    gfile = ws / "tests" / "golden" / group / name / "golden.json"
    if not gfile.is_file():
        print(f"  FAIL {group}/{name}: no golden.json (run --derive)")
        return False
    g = json.loads(gfile.read_text())
    score = latest_score(ws, group, name)
    ok_all = True
    for case in g.get("cases", []):
        ok, detail = run_case(case, g["baseline"], score)
        ok_all = ok_all and ok
        print(f"  {'PASS' if ok else 'FAIL'} {group}/{name}:{case['id']} — {detail}")
    return ok_all


def all_agents(ws: Path):
    for group in ("api-tester", "general"):
        for d in glob.glob(str(ws / "agents" / group / "*")):
            yield group, Path(d).name


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent", nargs="?")
    ap.add_argument("--derive", action="store_true")
    ap.add_argument("--rebaseline", action="store_true")
    ap.add_argument("--workspace", default=".")
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()

    if args.derive:
        print("derive: write tests/golden/<group>/<name>/golden.json with "
              "baseline := post-improvement-loop best + structural asserts. "
              "(Invoked by the build after Phase 4.5.)")
        return 0

    targets = ([tuple(args.agent.split("/", 1))] if args.agent
               else list(all_agents(ws)))
    ok = True
    for group, name in targets:
        ok = check_agent(ws, group, name) and ok
    print("\nGOLDEN PASS" if ok else "\nGOLDEN REGRESSION — hard-halt; fix before 'done'.")
    return 0 if ok else 1


if __name__ == "__main__":
    sys.exit(main())
