#!/usr/bin/env python3
# Used by: shared — bug reporting for the full run (all agents).
"""Stage 3 of the pipeline: report bugs USING THE BUG-REPORTER AGENT on a live run.

The bug-reporter (n602) normally scores against a gold fixture. This builds a LIVE
fixture from the run — the per-feature quality outcomes (guardrails), the test-case-creator
registry, and the Postman collection — points the bug-reporter at it via FORGE_BUGREPORT_SPEC,
and runs the agent so IT emits the bug-report decision per failed feature and materializes
the report files. Confirmed doc-backed bugs from the adjudication ledger raise severity.

A feature is reported as a bug when its guardrails outcome is FAIL / EMPTY / ERROR
(real failure on a supported capability or a crash). ENV-LIMITED and PASS/PARTIAL are not.

Usage:  python report_bugs.py <RUN_ID>
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
PY = str(WS / ".venv" / "bin" / "python")
BUG_OUTCOMES = {"FAIL", "EMPTY", "ERROR"}
# Generals are pipeline machinery, not API features under test — never bug-report them.
GENERALS = {"test-case-creator", "documentation-reviewer", "run-cicd-pipeline", "bug-reporter"}


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return default


def _agent_io(run_dir: Path, full: str) -> tuple[str, str]:
    d = run_dir / "agents" / full
    out = next(iter(d.glob("*stdout.txt")), None)
    err = next(iter(d.glob("*stderr.txt")), None)
    return ((out.read_text(errors="replace") if out else ""),
            (err.read_text(errors="replace") if err else ""))


def build_live_fixture(run_id: str) -> dict:
    run_dir = WS / "results" / "runs" / run_id
    guard = _read_json(run_dir / "guardrails-report.json", {"agents": []})
    ledger = _read_json(run_dir / "adjudication-ledger.json", {"rows": []})
    # registry the producer authored (the test cases); fall back to emitted-registry
    registry = _read_json(run_dir / "general-test-case-creator.emitted-registry.json", [])
    collection = _read_json(WS / "results" / "postman-collection.json", {}) or \
        _read_json(run_dir / "api-tester-create-postman-collection.postman-collection.json", {})

    # features with a confirmed doc-backed bug (raise severity / annotate)
    bug_agents = {r["agent"] for r in ledger.get("rows", []) if r.get("outcome") == "BUG"}

    agents = []
    for a in guard.get("agents", []):
        name = a["agent"]
        if name in GENERALS:        # features only — skip pipeline machinery
            continue
        full = f"api-tester-{name}"
        outcome = a.get("outcome")
        status = "FAILED" if outcome in BUG_OUTCOMES else "PASSED"
        stdout, stderr = _agent_io(run_dir, full)
        agents.append({
            "agent_name": full,                       # matches registry 'agent' so cases attach
            "status": status,
            "exit_code": 1 if status == "FAILED" else 0,
            "spec_path": f"agents/api-tester/{name}/subagent/{full}.md",
            "stdout": stdout[:4000],
            "stderr": (stderr[:4000] or f"quality outcome={outcome}; metric={a.get('metric_pct')}"),
            "stdout_path": f"results/runs/{run_id}/agents/{full}/{run_id}-stdout.txt",
            "stderr_path": f"results/runs/{run_id}/agents/{full}/{run_id}-stderr.txt",
            "quality_outcome": outcome,
            "doc_confirmed_bug": name in bug_agents,
        })
    return {"db_available": False,
            "pipeline_summary": {"run_id": run_id, "agents": agents},
            "registry": registry if isinstance(registry, list) else [],
            "postman_collection": collection}


def run(run_id: str) -> dict:
    run_dir = WS / "results" / "runs" / run_id
    fixture = build_live_fixture(run_id)
    failed = [a for a in fixture["pipeline_summary"]["agents"] if a["status"] != "PASSED"]

    live_dir = run_dir / "bug-reporter-live"
    live_dir.mkdir(parents=True, exist_ok=True)
    fx_path = live_dir / "fixture.json"
    fx_path.write_text(json.dumps(fixture, indent=2))
    spec = {"task": "n602", "alias": "bug-reporter-live", "fixture": str(fx_path),
            "fixture_run_id": run_id,
            "bug_reports_out": f"results/runs/{run_id}/general-bug-reporter.bug-reports",
            "index_out": f"results/runs/{run_id}/general-bug-reporter.bug-reports/index.json"}
    spec_path = live_dir / "bugreport_spec.json"
    spec_path.write_text(json.dumps(spec, indent=2))

    print(f"[report_bugs] {len(failed)} failed feature(s) -> bug-reporter agent: "
          f"{[a['agent_name'] for a in failed]}", flush=True)
    if not failed:
        print("[report_bugs] no failed features; nothing to report.", flush=True)
        return {"failed": 0, "reports": 0}

    rp = WS / "agents" / "general" / "bug-reporter" / "subagent" / "run.py"
    env = dict(os.environ, FORGE_WORKSPACE=str(WS), FORGE_RUN_ID=run_id,
               FORGE_BUGREPORT_SPEC=str(spec_path))
    proc = subprocess.run([PY, str(rp)], cwd=str(WS), env=env, capture_output=True, text=True)
    (live_dir / "bug-reporter-stdout.txt").write_text(proc.stdout or "")
    (live_dir / "bug-reporter-stderr.txt").write_text(proc.stderr or "")
    print((proc.stdout or "").strip()[-300:], flush=True)
    if proc.returncode != 0:
        print(f"[report_bugs] bug-reporter rc={proc.returncode}; see {live_dir}/bug-reporter-stderr.txt", flush=True)

    reports = list((run_dir / "general-bug-reporter.bug-reports").glob("BUG-*.json"))
    print(f"[report_bugs] materialized {len(reports)} bug report(s) via the bug-reporter agent.", flush=True)
    return {"failed": len(failed), "reports": len(reports),
            "report_dir": str(run_dir / "general-bug-reporter.bug-reports")}


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python report_bugs.py <RUN_ID>", file=sys.stderr)
        sys.exit(2)
    run(sys.argv[1])


if __name__ == "__main__":
    main()
