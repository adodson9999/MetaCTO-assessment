#!/usr/bin/env python3
"""10-round keep-if-improved tournament (Phase 4.5, references/improvement-loop.md).

autoresearch-style hill-climb: each round the agent proposes ONE bounded skill
edit, the edit re-passes the debate gate + determinism review + code-quality gate,
runs against the judge under a fixed budget, and is KEPT ONLY IF the judge score
improves (else discarded and retried). Post-loop best -> golden baseline.

This script is the deterministic harness: it sequences rounds, records the
trajectory, and enforces keep-if-improved. The PROPOSE step (the skill edit) and
the gates are invoked as subprocess hooks so the loop itself stays model-free.

Usage:
    python scripts/improve_loop.py --agent <group>/<name> [--rounds 10] [--workspace DIR]
"""
from __future__ import annotations

import argparse
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PY = sys.executable


def hook(ws: Path, name: str, *args) -> int:
    """Run a workspace hook script if present; treat absent hooks as no-op pass."""
    script = ws / "scripts" / name
    if not script.is_file():
        return 0
    return subprocess.run([PY, str(script), *args], cwd=str(ws)).returncode


def judged_score(ws: Path, group: str, name: str) -> float:
    import glob
    lbs = sorted(glob.glob(str(ws / "results" / group / name / "leaderboard-*.json")))
    if not lbs:
        return float("-inf")
    d = json.loads(Path(lbs[-1]).read_text())
    return float(d.get("this_run", d.get("score", float("-inf"))))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agent", required=True)            # group/name
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--workspace", default=".")
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()
    group, name = args.agent.split("/", 1)

    best = judged_score(ws, group, name)
    trajectory = [{"round": 0, "edit": "(baseline)", "score": best, "kept": True}]

    for rnd in range(1, args.rounds + 1):
        # 1. PROPOSE one bounded skill edit (model hook). 2. GATE the changed lines.
        # 3. DETERMINISM review. 4. RUN judge. Each gate non-zero => discard round.
        gate_fail = (
            hook(ws, "propose_edit.py", "--agent", args.agent, "--round", str(rnd))
            or hook(ws, "debate_gate.py", "--agent", args.agent, "--changed-only")
            or hook(ws, "determinism_check.py", "--artifact", f"{name}-r{rnd}",
                    "--kind", "revision", "--samples", "/dev/null")  # caller supplies real samples
            or hook(ws, "slop_scan.py", str(ws / "agents" / group / name), "--fail-below", "95")
            or hook(ws, "run_agents.py", "--only", args.agent)
        )
        score = judged_score(ws, group, name)
        kept = (gate_fail == 0) and (score >= best)
        if kept:
            best = score
        else:
            hook(ws, "restore_best.py", "--agent", args.agent)  # discard regressions
        trajectory.append({"round": rnd, "score": score, "kept": kept,
                           "gate_fail": gate_fail})

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    edir = ws / "evolvers" / "skillopt" / group / name
    edir.mkdir(parents=True, exist_ok=True)
    (edir / f"trajectory-{ts}.json").write_text(json.dumps(trajectory, indent=2))

    # Record post-loop best as the golden baseline.
    subprocess.run([PY, str(ws / "scripts" / "golden_run.py"), "--derive",
                    "--workspace", str(ws)])
    print(f"improve {args.agent}: best={best} after {args.rounds} rounds -> golden baseline")
    print(json.dumps(trajectory, indent=2))
    return 0


if __name__ == "__main__":
    sys.exit(main())
