#!/usr/bin/env python3
"""Run all four response-schema-validation agents in parallel and collect their
emitted metric JSONs.

Each agent is launched as a subprocess with its working directory pinned to the
workspace root (sandbox). Parallel is the default; --max-concurrency caps it if the
local backend saturates.

Each agent writes:
    results/schema/runs/<run-id>/<agent>.json
with at least {agent, run_id, metric_name, metric_value, raw_output_path, ts}.

Usage:
    python scripts/run_schema_agents__validate-json-schema-responses.py --workspace . [--run-id auto] [--max-concurrency 2]
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

AGENTS = {
    "langgraph": ["agents/api-tester/validate-json-schema-responses/langgraph/run.py"],
    "crewai": ["agents/api-tester/validate-json-schema-responses/crewai/run.py"],
    "claude_sdk": ["agents/api-tester/validate-json-schema-responses/claude_sdk/run.py"],
    "api-tester-validate-json-schema-responses":
        ["agents/api-tester/validate-json-schema-responses/subagent/run.py"],
}


def _python(workspace: Path) -> str:
    venv = workspace / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else sys.executable


def _launch(name: str, script: list[str], workspace: Path, run_id: str) -> dict:
    run_dir = workspace / "results" / "schema" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(workspace)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_AGENT"] = name
    env["FORGE_SANDBOX_ROOT"] = str(workspace)
    started = datetime.now(timezone.utc).isoformat()
    proc = subprocess.run([_python(workspace)] + script, cwd=str(workspace), env=env,
                          capture_output=True, text=True)
    out_json = run_dir / f"{name}.json"
    return {"agent": name, "run_id": run_id, "started": started,
            "returncode": proc.returncode, "emitted": out_json.exists(),
            "json_path": str(out_json), "stdout_tail": proc.stdout.strip()[-300:],
            "stderr_tail": proc.stderr.strip()[-600:]}


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", default="auto")
    ap.add_argument("--max-concurrency", type=int, default=2)
    a = ap.parse_args()

    workspace = Path(a.workspace).resolve()
    run_id = (datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S") + "-" + uuid.uuid4().hex[:6]
              if a.run_id == "auto" else a.run_id)

    results = []
    with ThreadPoolExecutor(max_workers=max(1, a.max_concurrency)) as ex:
        futs = {ex.submit(_launch, n, c, workspace, run_id): n for n, c in AGENTS.items()}
        for fut in as_completed(futs):
            results.append(fut.result())

    summary = {"run_id": run_id, "agents": sorted(results, key=lambda r: r["agent"]),
               "all_emitted": all(r["emitted"] for r in results)}
    print(json.dumps(summary, indent=2))
    print(f"\nNext: python judge/schema/score.py --workspace {workspace} --run-id {run_id}")
    return 0 if summary["all_emitted"] else 1


if __name__ == "__main__":
    raise SystemExit(main())
