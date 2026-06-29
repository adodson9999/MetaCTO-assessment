#!/usr/bin/env python3
"""Fight Camp — one independent keep-if-improved experiment per framework.

Four sealed corners (langgraph, crewai, claude_sdk, claude_subagent). Same task,
same judge metric, same budget; INDEPENDENT prompt state. Each framework keeps an
edit only if ITS OWN judged score improves, so prompts diverge by design
(references/experiments.md). The harness is deterministic; PROPOSE and the gates are
subprocess hooks into the foundry's scripts so the loop itself stays model-free.

Usage:
    python scripts/fight_camp.py [--framework NAME] [--rounds 10] [--workspace DIR]
With no --framework, trains all four. Writes per-framework best_prompt + trajectory
and a cross-framework leaderboard (results/_global/fight-camp-<ts>.{json,md}).
"""
from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PY = sys.executable
FRAMEWORKS = ["langgraph", "crewai", "claude_sdk", "claude_subagent"]


def hook(ws: Path, name: str, *args) -> int:
    """Run a foundry script if present; absent hook == no-op pass (exit 0)."""
    script = ws / "scripts" / name
    if not script.is_file():
        return 0
    return subprocess.run([PY, str(script), *args], cwd=str(ws)).returncode


def framework_score(ws: Path, framework: str) -> float:
    """Latest judged score for this framework from any run json it wrote."""
    best = float("-inf")
    for f in sorted(glob.glob(str(ws / "results" / "runs" / "*" / f"{framework}.json"))):
        try:
            v = float(json.loads(Path(f).read_text()).get("metric_value", float("-inf")))
            best = max(best, v)
        except Exception:
            continue
    return best


def train_one(ws: Path, framework: str, rounds: int) -> dict:
    best = framework_score(ws, framework)
    traj = [{"round": 0, "edit": "(baseline)", "score": best, "kept": True}]
    camp = ws / "evolvers" / "fight-camp" / framework
    camp.mkdir(parents=True, exist_ok=True)

    for rnd in range(1, rounds + 1):
        gate_fail = (
            hook(ws, "propose_edit.py", "--framework", framework, "--round", str(rnd))
            or hook(ws, "debate_gate.py", "--framework", framework, "--changed-only")
            or hook(ws, "determinism_check.py", "--artifact", f"{framework}-r{rnd}",
                    "--kind", "revision", "--samples", "/dev/null")
            or hook(ws, "slop_scan.py", str(ws / "agents"), "--fail-below", "95")
            or hook(ws, "run_agents.py", "--only-framework", framework)
        )
        score = framework_score(ws, framework)
        kept = (gate_fail == 0) and (score >= best)
        if kept:
            best = score
        else:
            hook(ws, "restore_best.py", "--framework", framework)
        traj.append({"round": rnd, "score": score, "kept": kept, "gate_fail": gate_fail})

    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    (camp / f"trajectory-{ts}.json").write_text(json.dumps(traj, indent=2))
    if not (camp / "best_prompt.md").exists():
        (camp / "best_prompt.md").write_text(
            f"# best_prompt for {framework}\n\n(written by the build after PROPOSE; "
            f"this fighter's divergent winning prompt)\n")
    return {"framework": framework, "baseline": traj[0]["score"], "best": best,
            "rounds": rounds, "prompt": f"evolvers/fight-camp/{framework}/best_prompt.md"}


def write_leaderboard(ws: Path, results: list[dict]) -> None:
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
    out = ws / "results" / "_global"
    out.mkdir(parents=True, exist_ok=True)
    ranked = sorted(results, key=lambda r: r["best"], reverse=True)
    (out / f"fight-camp-{ts}.json").write_text(json.dumps(ranked, indent=2))
    lines = ["# Fight Camp — cross-framework best-achievable",
             f"Updated: {ts}  ·  Each fighter trained independently; prompts diverge by design.",
             "", "| Rank | Framework | Baseline | Best evolved | Rounds | Prompt |",
             "|------|-----------|----------|--------------|--------|--------|"]
    for i, r in enumerate(ranked, 1):
        lines.append(f"| {i} | {r['framework']} | {r['baseline']} | {r['best']} | "
                     f"{r['rounds']} | {r['prompt']} |")
    (out / f"fight-camp-{ts}.md").write_text("\n".join(lines) + "\n")
    print("\n".join(lines))


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--framework", choices=FRAMEWORKS)
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--workspace", default=".")
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()

    # Require a built foundry before training.
    if hook(ws, "verify_build.py", "--phase", "4", "--workspace", str(ws)) != 0:
        print("fight-camp: foundry incomplete (verify_build --phase 4 failed). "
              "Run forge-agents first. HARD-HALT.")
        return 1

    targets = [args.framework] if args.framework else FRAMEWORKS
    results = [train_one(ws, fw, args.rounds) for fw in targets]
    write_leaderboard(ws, results)

    # Winners written back -> re-derive golden + re-verify the full contract.
    hook(ws, "golden_run.py", "--derive", "--workspace", str(ws))
    rc = hook(ws, "verify_build.py", "--phase", "6", "--workspace", str(ws))
    if rc != 0:
        print("fight-camp: post-training output contract FAILED. HARD-HALT.")
        return 1
    return 0


if __name__ == "__main__":
    sys.exit(main())
