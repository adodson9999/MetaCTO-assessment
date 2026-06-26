#!/usr/bin/env python3
"""Run all four authorization-rules agents in parallel and collect their emitted
metric JSONs (results/authz/runs/<run-id>/<agent>.json).

Each agent is launched as a subprocess with its working directory pinned to the
workspace root (sandbox). Parallel is the default; --max-concurrency caps it if
the local backend saturates.

Usage:
    python run_agents_authz.py --workspace . [--run-id auto] [--max-concurrency 2]
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from datetime import datetime, timezone
from pathlib import Path

AGENTS = {
    "langgraph": ["python", "agents/langgraph/run_authz.py"],
    "crewai": ["python", "agents/crewai/run_authz.py"],
    "api-tester-check-authorization-rules": ["python", "agents/api-tester/check-authorization-rules/run.py"],
    "claude_sdk": ["python", "agents/claude_sdk/run_authz.py"],
}


def _launch(name: str, cmd: list[str], workspace: Path, run_id: str) -> dict:
    run_dir = workspace / "results" / "authz" / "runs" / run_id
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
    return {"agent": name, "run_id": run_id, "started": started,
            "returncode": proc.returncode, "emitted": out_json.exists(),
            "json_path": str(out_json), "stderr_tail": proc.stderr.strip()[-500:]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", default="auto")
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
    print(f"\nNext: python judge/score_authz.py --workspace {workspace} --run-id {run_id}")
    return 0 if summary["all_emitted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
