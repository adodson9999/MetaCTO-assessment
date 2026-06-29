#!/usr/bin/env python3
"""Output-contract guardrail — the build cannot report "done" until this passes.

Deterministic check of the full deliverable set (references/guardrails.md). On any
failure it prints what failed and exits non-zero; the calling flow must HARD-HALT
and ask the user (constitution Article I.9, Article V). No model calls.

Usage:
    python scripts/verify_build.py --phase {4,6} [--workspace DIR]
Phase 4 = precondition (4 agents exist + emit metrics). Phase 6 = full contract.
Exit 0 = pass, 1 = contract failure.
"""
from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from pathlib import Path

QUALITY_FLOOR = 95


class Report:
    def __init__(self) -> None:
        self.fail: list[str] = []
        self.ok: list[str] = []

    def check(self, cond: bool, label: str, detail: str = "") -> None:
        (self.ok if cond else self.fail).append(label if cond else f"{label} — {detail}")


def agent_dirs(ws: Path) -> list[Path]:
    out = []
    for group in ("api-tester", "general"):
        gdir = ws / "agents" / group
        if gdir.is_dir():
            out += [d for d in gdir.iterdir() if d.is_dir()]
    return out


def check_agents(ws: Path, r: Report) -> None:
    agents = agent_dirs(ws)
    r.check(bool(agents), "agents-present", "no agent folders under agents/<group>/")
    for a in agents:
        for fw in ("langgraph", "crewai", "claude_sdk", "subagent"):
            r.check((a / fw / "run.py").is_file(), f"{a.name}:{fw}/run.py", "missing run.py")
        md = a / "subagent" / f"{a.name}.md"
        r.check(md.is_file(), f"{a.name}:subagent prompt", "missing gated <name>.md")
        group = a.parent.name
        jdir = ws / "judge" / group / a.name
        r.check((jdir / "metric.json").is_file(), f"{a.name}:metric.json", "missing")
        r.check((jdir / "score.py").is_file(), f"{a.name}:score.py", "missing")


def check_leaderboards(ws: Path, r: Report) -> None:
    for a in agent_dirs(ws):
        rdir = ws / "results" / a.parent.name / a.name
        lbs = glob.glob(str(rdir / "leaderboard-*.json"))
        r.check(bool(lbs), f"{a.name}:leaderboard", "no timestamped leaderboard-*.json")
        bare = (rdir / "leaderboard.json").exists()
        r.check(not bare, f"{a.name}:no-bare-leaderboard", "bare leaderboard.json forbidden")


def check_runs(ws: Path, r: Report) -> None:
    runs = sorted(glob.glob(str(ws / "results" / "runs" / "*")))
    r.check(bool(runs), "results/runs present", "no run directories")
    needed = {"agent", "run_id", "metric_name", "metric_value", "raw_output_path", "ts"}
    for run in runs[-1:]:
        for f in glob.glob(str(Path(run) / "*.json")):
            if f.endswith(".cases.json"):
                continue
            try:
                data = json.loads(Path(f).read_text())
            except Exception as e:
                r.check(False, f"run json {Path(f).name}", f"unparseable: {e}")
                continue
            missing = needed - set(data)
            r.check(not missing, f"run json {Path(f).name}", f"missing fields {missing}")
            r.check(isinstance(data.get("metric_value"), (int, float)),
                    f"run metric {Path(f).name}", "metric_value not numeric")


def check_phase6_extras(ws: Path, r: Report) -> None:
    r.check((ws / "workspace" / "SELF_REVIEW.md").is_file() or (ws / "SELF_REVIEW.md").is_file(),
            "SELF_REVIEW.md", "missing self-review")
    r.check(bool(glob.glob(str(ws / "results" / "_global" / "analyze-*.json"))),
            "analyze report", "no analyze-*.json (Phase 3.5 gate not run)")
    r.check(bool(glob.glob(str(ws / "results" / "_global" / "determinism" / "*.json"))),
            "determinism receipts", "no determinism receipts")
    for a in agent_dirs(ws):
        g = ws / "tests" / "golden" / a.parent.name / a.name / "golden.json"
        r.check(g.is_file(), f"{a.name}:golden.json", "no golden baseline")


def check_quality(ws: Path, r: Report) -> None:
    scan = ws / "scripts" / "slop_scan.py"
    if not scan.is_file():
        r.check(False, "quality-gate", "slop_scan.py missing")
        return
    proc = subprocess.run([sys.executable, str(scan), str(ws), "--json",
                           "--fail-below", str(QUALITY_FLOOR)],
                          capture_output=True, text=True)
    try:
        overall = json.loads(proc.stdout).get("overall", 0)
    except Exception:
        overall = 0
    r.check(proc.returncode == 0 and overall >= QUALITY_FLOOR,
            f"code-quality>={QUALITY_FLOOR}", f"score {overall} — files below 95 must be rewritten")


def check_files(ws: Path, r: Report) -> None:
    vf = ws / "scripts" / "verify_files.py"
    if not vf.is_file():
        r.check(False, "file-completeness", "verify_files.py missing")
        return
    rc = subprocess.run([sys.executable, str(vf), "--workspace", str(ws)],
                        capture_output=True).returncode
    r.check(rc == 0, "file-completeness (every created file present + correct)",
            "missing or bad-content files; see results/_global/files-*.json")


def check_config(ws: Path, r: Report) -> None:
    cfg = ws / "config.toml"
    r.check(cfg.is_file(), "config.toml", "missing")
    if cfg.is_file():
        text = cfg.read_text()
        r.check('provider = "auto"' in text or "provider='auto'" in text,
                "backend provider=auto", "provider must be 'auto'")
    vc = ws / "scripts" / "verify_llm_config.py"
    if vc.is_file():
        rc = subprocess.run([sys.executable, str(vc)], capture_output=True).returncode
        r.check(rc == 0, "verify_llm_config", "llm config check failed")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--phase", type=int, choices=[4, 6], required=True)
    ap.add_argument("--workspace", default=".")
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()
    r = Report()

    check_agents(ws, r)
    check_runs(ws, r)
    check_config(ws, r)
    if args.phase == 6:
        check_leaderboards(ws, r)
        check_phase6_extras(ws, r)
        check_files(ws, r)
        check_quality(ws, r)

    print(f"verify_build --phase {args.phase}  ({ws})")
    for ok in r.ok:
        print(f"  PASS  {ok}")
    for f in r.fail:
        print(f"  FAIL  {f}")
    if r.fail:
        print(f"\n{len(r.fail)} contract failure(s). HARD-HALT: fix and re-run; "
              f"do not report 'done'.")
        return 1
    print("\noutput contract satisfied.")
    return 0


if __name__ == "__main__":
    sys.exit(main())
