#!/usr/bin/env python3
"""
Run the four soft-delete-behavior agents in parallel on the current task and collect
their emitted metric JSONs. Task-scoped sibling of run_agents.py; both write to
results/runs/<run-id>/.

Each agent is launched as a subprocess with its working directory pinned to the
workspace root (sandbox). Each agent's harness runs its own case_count
create->delete->verify lifecycles; the local soft-delete target generates a unique id
per created resource and the harness namespaces the posted field values by
(run_id, agent, case), so the four agents never confuse each other's resources on one
shared DB.

Each agent writes:
    results/runs/<run-id>/<agent>.json
with at least {agent, run_id, metric_name, metric_value, raw_output_path, ts}.

Usage:
    python run_softdelete_agents__test-soft-delete-behavior.py --workspace . [--run-id auto] [--max-concurrency 4]
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

BASE = "agents/api-tester/test-soft-delete-behavior"
def _pyexe() -> str:
    # Prefer the foundry .venv (has langgraph/crewai/...); fall back to the launching interpreter.
    _venv = Path(__file__).resolve().parents[1] / ".venv" / "bin" / "python"
    return str(_venv) if _venv.exists() else (sys.executable or "python3")


PYEXE = _pyexe()
AGENTS = {
    "langgraph": [PYEXE, f"{BASE}/langgraph/run.py"],
    "crewai": [PYEXE, f"{BASE}/crewai/run.py"],
    "api-tester-test-soft-delete-behavior": [PYEXE, f"{BASE}/subagent/run.py"],
    "claude_sdk": [PYEXE, f"{BASE}/claude_sdk/run.py"],
}


def _launch(name: str, cmd: list[str], workspace: Path, run_id: str) -> dict:
    run_dir = workspace / "results" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(workspace)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_AGENT"] = name
    env["FORGE_SANDBOX_ROOT"] = str(workspace)
    started = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run(cmd, cwd=str(workspace), env=env,
                          capture_output=True, text=True)
    out_json = run_dir / f"{name}.json"
    return {
        "agent": name, "run_id": run_id, "started": started,
        "returncode": proc.returncode, "emitted": out_json.exists(),
        "json_path": str(out_json), "stderr_tail": proc.stderr.strip()[-500:],
    }


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", default="auto")
    # Default 2: the soft-delete target is a ThreadingHTTPServer and each agent's
    # lifecycles are sequential GET/POST/DELETE round-trips, so a small overlap is
    # safe. Bump down to 1 if the local LLM backend saturates.
    ap.add_argument("--max-concurrency", type=int, default=2)
    a = ap.parse_args()

    workspace = Path(a.workspace).resolve()
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
    print(f"\nNext: python judge/test-soft-delete-behavior/score.py "
          f"--workspace {workspace} --run-id {run_id}")
    return 0 if summary["all_emitted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
