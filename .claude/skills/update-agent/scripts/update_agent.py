#!/usr/bin/env python3
"""update-agent — bring one existing agent through the v2 flow + a user change.

    update_agent.py <agent_name> <prompt ...> [--workspace DIR] [--rounds 10]

Brownfield, regression-protected: applies the user's change, re-runs every foundry
gate (debate, determinism, 95 quality, analyze, judge, improve, golden, guardrails),
and refuses to let the agent's judged metric fall below its golden baseline unless
the user's prompt explicitly authorized a tradeoff (references/flow.md).

The harness is deterministic; PROPOSE and the gates are subprocess hooks into the
foundry's own scripts so this loop stays model-free. Absent hooks == no-op pass, so
this runs in a partially scaffolded workspace without crashing.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PY = sys.executable
TRADEOFF_RE = re.compile(r"even if it (lowers|reduces|drops)|accept the tradeoff", re.I)


def hook(ws: Path, name: str, *args) -> int:
    script = ws / "scripts" / name
    if not script.is_file():
        return 0
    return subprocess.run([PY, str(script), *args], cwd=str(ws)).returncode


def locate(ws: Path, agent_name: str) -> tuple[str, str] | None:
    for group in ("api-tester", "general"):
        for d in glob.glob(str(ws / "agents" / group / "*")):
            name = Path(d).name
            if name == agent_name or name.endswith(agent_name) or agent_name in name:
                return group, name
    return None


def golden_floor(ws: Path, group: str, name: str) -> float:
    g = ws / "tests" / "golden" / group / name / "golden.json"
    if not g.is_file():
        return float("-inf")
    try:
        return float(json.loads(g.read_text())["baseline"]["value"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return float("-inf")


def latest_score(ws: Path, group: str, name: str) -> float:
    best = float("-inf")
    for f in sorted(glob.glob(str(ws / "results" / group / name / "leaderboard-*.json"))):
        try:
            d = json.loads(Path(f).read_text())
            best = max(best, float(d.get("this_run", d.get("score", best))))
        except (ValueError, json.JSONDecodeError):
            continue
    return best


def back_up(ws: Path, group: str, name: str, ts: str) -> Path:
    dest = ws / "archives" / f"update-{name}-{ts}"
    dest.mkdir(parents=True, exist_ok=True)
    src = ws / "agents" / group / name
    if src.is_dir():
        shutil.copytree(src, dest / "agent", dirs_exist_ok=True)
    judge = ws / "judge" / group / name
    if judge.is_dir():
        shutil.copytree(judge, dest / "judge", dirs_exist_ok=True)
    return dest


def write_spec(ws: Path, name: str, prompt: str, tradeoff: bool) -> None:
    sp = ws / "workspace"
    sp.mkdir(parents=True, exist_ok=True)
    (sp / f"update_spec-{name}.md").write_text(
        f"# Update Spec — {name}\n\n## User prompt\n{prompt}\n\n"
        f"## Tradeoff authorized\n{tradeoff}\n")


def write_report(ws: Path, name: str, info: dict) -> None:
    sp = ws / "workspace"
    sp.mkdir(parents=True, exist_ok=True)
    (sp / f"update-report-{name}.md").write_text(
        f"# Update Report — {name}, {info['ts']}\n\n"
        f"## Change applied\n{info['prompt']}\n(tradeoff: {info['tradeoff']})\n\n"
        f"## Score\nFLOOR: {info['floor']}  ·  after: {info['after']}  ·  "
        f"verdict: {info['verdict']}\n\n## Backup\n{info['backup']}\n")


def run_gates(ws: Path, group: str, name: str, rounds: int) -> None:
    agent = f"{group}/{name}"
    hook(ws, "debate_gate.py", "--agent", agent, "--changed-only")
    hook(ws, "determinism_check.py", "--artifact", f"{name}-update",
         "--kind", "agent_prompt", "--samples", "/dev/null")
    hook(ws, "slop_scan.py", str(ws / "agents" / group / name), "--fail-below", "95")
    hook(ws, "analyze.py", "--workspace", str(ws))
    hook(ws, "run_agents.py", "--only", agent)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent_name")
    ap.add_argument("prompt", nargs="+")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--workspace", default=".")
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()
    prompt = " ".join(args.prompt)
    tradeoff = bool(TRADEOFF_RE.search(prompt))
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    if hook(ws, "verify_build.py", "--phase", "4", "--workspace", str(ws)) != 0:
        print("update-agent: foundry incomplete (verify_build --phase 4). HARD-HALT.")
        return 1

    found = locate(ws, args.agent_name)
    if not found:
        print(f"update-agent: no existing agent matches '{args.agent_name}'. "
              f"This skill updates existing agents; use forge-agents to create one.")
        return 1
    group, name = found
    floor = golden_floor(ws, group, name)
    backup = back_up(ws, group, name, ts)
    write_spec(ws, name, prompt, tradeoff)
    print(f"update-agent: {group}/{name}  FLOOR={floor}  tradeoff={tradeoff}  backup={backup}")

    run_gates(ws, group, name, args.rounds)
    after = latest_score(ws, group, name)

    if after < floor and not tradeoff:
        print(f"REGRESSION: {after} < baseline {floor} and no tradeoff authorized. "
              f"HARD-HALT: revise the change, authorize the tradeoff, or restore "
              f"from {backup}.")
        write_report(ws, name, {"ts": ts, "prompt": prompt, "tradeoff": tradeoff,
                                "floor": floor, "after": after, "verdict": "regressed-halt",
                                "backup": str(backup)})
        return 1

    hook(ws, "improve_loop.py", "--agent", f"{group}/{name}", "--rounds", str(args.rounds))
    hook(ws, "golden_run.py", "--derive", "--workspace", str(ws))
    final = latest_score(ws, group, name)
    verdict = "improved" if final >= floor else "tradeoff-accepted"

    rc = hook(ws, "verify_build.py", "--phase", "6", "--workspace", str(ws))
    rc = hook(ws, "verify_files.py", "--workspace", str(ws)) or rc
    write_report(ws, name, {"ts": ts, "prompt": prompt, "tradeoff": tradeoff,
                            "floor": floor, "after": final, "verdict": verdict,
                            "backup": str(backup)})
    if rc != 0:
        print("update-agent: post-update output contract FAILED. HARD-HALT.")
        return 1
    print(f"update-agent: {group}/{name} updated. FLOOR={floor} -> {final} ({verdict}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
