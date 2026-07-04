#!/usr/bin/env python3
# Used by: shared — generic multi-agent runner; used by phase4_run.sh.
"""
Run all four agents in parallel on the current task and collect their emitted
metric JSONs.

Each agent is launched as a subprocess with its working directory pinned to the
workspace root (sandbox). Parallel is the default; --max-concurrency caps it if
the local backend saturates.

Each agent is expected to write:
    results/runs/<run-id>/<agent>.json
with at least {agent, run_id, metric_name, metric_value, raw_output_path, ts}.

Usage:
    python run_agents.py --workspace . [--run-id auto] [--max-concurrency 4]
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

def _pyexe() -> str:
    # Prefer the foundry .venv (has langgraph/crewai/...); fall back to the launching interpreter.
    _venv = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"
    return str(_venv) if _venv.exists() else (sys.executable or "python3")


PYEXE = _pyexe()
AGENTS = {
    "langgraph": [PYEXE, "agents/api-tester/validate-request-payloads/langgraph/run.py"],
    "crewai": [PYEXE, "agents/api-tester/validate-request-payloads/crewai/run.py"],
    "api-tester-validate-request-payloads": [PYEXE, "agents/api-tester/validate-request-payloads/subagent/run.py"],
    "claude_sdk": [PYEXE, "agents/api-tester/validate-request-payloads/claude_sdk/run.py"],
}


def _launch(name: str, cmd: list[str], workspace: Path, run_id: str) -> dict:
    run_dir = workspace / "results" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(workspace)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_AGENT"] = name
    env["FORGE_SANDBOX_ROOT"] = str(workspace)  # agents must not write above this
    started = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(cmd, cwd=str(workspace), env=env,
                          capture_output=True, text=True)
    out_json = run_dir / f"{name}.json"
    result = {
        "agent": name,
        "run_id": run_id,
        "started": started,
        "returncode": proc.returncode,
        "emitted": out_json.exists(),
        "json_path": str(out_json),
        "stderr_tail": proc.stderr.strip()[-500:],
    }
    return result


def _run_only(workspace: Path, only: str) -> int:
    """Re-judge ONE agent by <group>/<name> (or bare <name>): dispatch to its
    per-lane runner, score it, and write the nested timestamped leaderboard that
    update_agent.py reads. The foundry uses per-lane runners (run_<x>_agents__*.py),
    not this module's generic AGENTS table, so this delegates to regen_outputs —
    the single nested-aware driver — rather than the hardwired flat AGENTS above."""
    sys.path.insert(0, str(Path(__file__).resolve().parent))
    import regen_outputs as ro
    group, _, name = only.partition("/")
    if not name:              # bare name -> resolve its group from the judge tree
        name = group
        matches = [(g, n) for g, n in ro.judged_agents() if n == name]
        if not matches:
            print(f"run_agents --only: no judged agent named {name!r}")
            return 1
        group, name = matches[0]
    res = ro.regen_one(group, name, force=True)
    print(json.dumps(res, indent=2))
    return 0 if res.get("status") == "ok" else 1


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", default="auto")
    ap.add_argument("--max-concurrency", type=int, default=4)
    ap.add_argument("--only", default=None,
                    help="re-judge exactly one agent by <group>/<name> (or bare <name>) "
                         "via its per-lane runner + scorer + leaderboard")
    a = ap.parse_args()

    workspace = Path(a.workspace).resolve()
    if a.only:
        return _run_only(workspace, a.only)
    run_id = (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")
              + "-" + uuid.uuid4().hex[:6]) if a.run_id == "auto" else a.run_id

    results = []
    with ThreadPoolExecutor(max_workers=max(1, a.max_concurrency)) as ex:
        futs = {ex.submit(_launch, n, c, workspace, run_id): n
                for n, c in AGENTS.items()}
        for fut in as_completed(futs):
            results.append(fut.result())

    summary = {"run_id": run_id, "agents": results,
               "all_emitted": all(r["emitted"] for r in results)}
    print(json.dumps(summary, indent=2))
    print(f"\nNext: python judge_score.py --workspace {workspace} --run-id {run_id}")
    return 0 if summary["all_emitted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
