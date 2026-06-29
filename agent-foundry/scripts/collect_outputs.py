#!/usr/bin/env python3
# Used by: shared — collects agent outputs across all agents.
"""Collect every agent's test-case outputs into a per-agent, per-framework folder tree so
you can see what was sent through the test cases and validate the responses.

Layout written under results/runs/<RUN_ID>/framework-outputs/:

    <agent>/
        subagent.json      raw cases.json the subagent framework produced
        crewai.json        (when that framework has run / is --run)
        langgraph.json
        claude_sdk.json
        combined.json      per-scenario validation view across the available frameworks:
                           {scenario, ideal, observed_by{fw}, api_correct_by{fw}, frameworks_agree}
    _ALL-COMBINED.json     every agent x every framework + per-agent agreement summary

Two modes:
  (default) ORGANIZE  — snapshot whatever each framework already wrote into the tree.
  --run               — execute the chosen frameworks per agent first (they overwrite the
                        shared <agent>.cases.json, so each is snapshotted immediately), then
                        organize. Needs the backend up; bounded per call.

Usage:
  python collect_outputs.py <RUN_ID> [--frameworks subagent,crewai,langgraph,claude_sdk]
                                     [--agents a,b,c] [--run]
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
PY = str(WS / ".venv" / "bin" / "python")
TARGET = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899")
FW_TIMEOUT = int(os.environ.get("FORGE_FRAMEWORK_TIMEOUT", "1800"))
FRAMEWORKS = ["subagent", "crewai", "langgraph", "claude_sdk"]

API_TESTERS = [
    "validate-request-payloads", "verify-response-status-codes", "test-authentication-flows",
    "check-authorization-rules", "validate-json-schema-responses", "test-pagination-behavior",
    "verify-error-message-clarity", "test-rate-limit-enforcement", "validate-query-parameter-handling",
    "test-idempotency-of-endpoints", "verify-content-type-negotiation", "validate-null-empty-fields",
    "test-timeout-handling", "verify-crud-operation-integrity", "test-concurrent-request-handling",
    "validate-header-propagation", "test-webhook-delivery", "run-regression-suite",
    "track-defect-density", "validate-api-versioning-behavior", "test-ssl-tls-enforcement",
    "verify-caching-headers", "validate-correlation-id-propagation", "test-bulk-operation-endpoints",
    "verify-audit-log-generation", "validate-search-and-filter-queries", "test-file-upload-and-download",
    "verify-sorting-behavior", "test-event-driven-api-triggers", "test-ip-allowlist-enforcement",
    "test-api-gateway-routing", "verify-third-party-oauth-integration", "test-multipart-form-data-handling",
    "validate-retry-after-header-compliance", "test-soft-delete-behavior", "validate-graphql-depth-limits",
    "test-long-polling-support", "verify-enum-value-restrictions", "measure-api-consumer-satisfaction",
    "create-postman-collection",
]


def _iter_scenarios(obj):
    if isinstance(obj, dict):
        scns = obj.get("scenarios")
        if isinstance(scns, list):
            for s in scns:
                if isinstance(s, dict):
                    yield s
        for v in obj.values():
            yield from _iter_scenarios(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_scenarios(v)


def _scen_key(s: dict) -> str:
    return f"{s.get('endpoint') or s.get('collection') or ''}::{s.get('scenario','')}"


def run_framework(run_dir: Path, run_id: str, agent: str, fw: str) -> dict:
    """Run one framework's run.py for one agent; snapshot its cases.json to <agent>/<fw>.json."""
    rp = WS / "agents" / "api-tester" / agent / fw / "run.py"
    out_dir = run_dir / "framework-outputs" / agent
    out_dir.mkdir(parents=True, exist_ok=True)
    rec = {"framework": fw, "ran": False, "seconds": 0.0, "timed_out": False, "error": None}
    if not rp.exists():
        rec["error"] = "run.py missing"
        return rec
    env = dict(os.environ, FORGE_WORKSPACE=str(WS), FORGE_RUN_ID=run_id,
               FORGE_TARGET_BASE_URL=TARGET, FORGE_MAX_ENDPOINTS="0")
    t0 = datetime.now(timezone.utc)
    try:
        proc = subprocess.run([PY, str(rp)], cwd=str(WS), env=env,
                              capture_output=True, text=True, timeout=FW_TIMEOUT)
        (out_dir / f"{fw}.stdout.txt").write_text(proc.stdout or "")
        (out_dir / f"{fw}.stderr.txt").write_text(proc.stderr or "")
        rec["ran"] = True
        rec["returncode"] = proc.returncode
    except subprocess.TimeoutExpired:
        rec["timed_out"] = True
    rec["seconds"] = round((datetime.now(timezone.utc) - t0).total_seconds(), 1)
    cases = run_dir / f"api-tester-{agent}.cases.json"
    if cases.exists():
        shutil.copyfile(cases, out_dir / f"{fw}.json")
    return rec


def organize_agent(run_dir: Path, agent: str, frameworks: list[str]) -> dict:
    """Snapshot any already-written cases.json for `subagent` if missing, then build the
    per-agent combined validation view across whatever framework files exist."""
    out_dir = run_dir / "framework-outputs" / agent
    out_dir.mkdir(parents=True, exist_ok=True)
    # the subagent run (the one the driver does) leaves <agent>.cases.json — capture it
    base = run_dir / f"api-tester-{agent}.cases.json"
    if base.exists() and not (out_dir / "subagent.json").exists():
        shutil.copyfile(base, out_dir / "subagent.json")

    present = {}
    for fw in frameworks:
        fp = out_dir / f"{fw}.json"
        if fp.exists():
            try:
                present[fw] = json.loads(fp.read_text())
            except json.JSONDecodeError:
                pass

    # per-scenario, per-framework: ideal + each framework's observed + correctness
    scen = {}
    for fw, data in present.items():
        for s in _iter_scenarios(data):
            k = _scen_key(s)
            row = scen.setdefault(k, {"scenario": s.get("scenario"),
                                      "endpoint": s.get("endpoint") or s.get("collection"),
                                      "ideal": s.get("ideal"), "observed_by": {}, "api_correct_by": {}})
            row["observed_by"][fw] = s.get("observed_token")
            row["api_correct_by"][fw] = s.get("api_correct")
    for row in scen.values():
        obs = [v for v in row["observed_by"].values()]
        row["frameworks_agree"] = len(set(map(str, obs))) <= 1 if obs else None

    combined = {"agent": agent, "frameworks_present": sorted(present.keys()),
                "frameworks_missing": [f for f in frameworks if f not in present],
                "scenario_count": len(scen), "scenarios": list(scen.values())}
    (out_dir / "combined.json").write_text(json.dumps(combined, indent=2))
    return combined


def run(run_id: str, frameworks: list[str], agents: list[str], do_run: bool) -> dict:
    run_dir = WS / "results" / "runs" / run_id
    grand = {"run_id": run_id, "frameworks": frameworks, "agents": {}}
    for i, agent in enumerate(agents, 1):
        if do_run:
            for fw in frameworks:
                rec = run_framework(run_dir, run_id, agent, fw)
                print(f"[{i}/{len(agents)}] {agent} / {fw}: ran={rec['ran']} "
                      f"{rec['seconds']}s" + (" TIMEOUT" if rec["timed_out"] else ""), flush=True)
        combined = organize_agent(run_dir, agent, frameworks)
        agree = sum(1 for s in combined["scenarios"] if s["frameworks_agree"])
        grand["agents"][agent] = {
            "frameworks_present": combined["frameworks_present"],
            "scenario_count": combined["scenario_count"],
            "scenarios_all_frameworks_agree": agree}
        print(f"[{i}/{len(agents)}] {agent}: frameworks={combined['frameworks_present']} "
              f"scenarios={combined['scenario_count']} agree={agree}", flush=True)
    out = run_dir / "framework-outputs" / "_ALL-COMBINED.json"
    out.write_text(json.dumps(grand, indent=2))
    print(f"\nwrote {out}", flush=True)
    return grand


def main() -> None:
    argv = sys.argv[1:]
    if not argv or argv[0].startswith("-"):
        print("usage: python collect_outputs.py <RUN_ID> [--frameworks ...] [--agents ...] [--run]", file=sys.stderr)
        sys.exit(2)
    run_id = argv[0]
    do_run = "--run" in argv
    fws = FRAMEWORKS
    if "--frameworks" in argv:
        fws = [f.strip() for f in argv[argv.index("--frameworks") + 1].split(",") if f.strip()]
    agents = API_TESTERS
    if "--agents" in argv:
        agents = [a.strip() for a in argv[argv.index("--agents") + 1].split(",") if a.strip()]
    run(run_id, fws, agents, do_run)


if __name__ == "__main__":
    main()
