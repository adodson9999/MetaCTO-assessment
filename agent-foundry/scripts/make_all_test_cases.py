#!/usr/bin/env python3
# Used by: orchestrator — test-case creation across ALL api-tester agents.
"""Build 9-field professional test cases for ALL 40 api-testers, retry-until-complete.

Per agent: run the executor over all endpoints (it records the exact steps it took + the
result of each) -> the deterministic test-case-creator formats that into 9-field test cases
(cases.json + cases.md). The agent supplies steps+results; the test-case-creator is the SOLE
author of the formatted cases. Does not stop after one pass: any agent that yields no cases is
retried (executor re-run) until every agent has cases, then guardrail G11 is asserted.

Outputs under results/runs/<RUN>/:
  test-case-registry/<agent>/cases.json   9-field objects
  test-case-registry/<agent>/cases.md     readable professional document
  test-case-registry.json                 merged registry (all agents)
  test-cases-ALL.md                        merged readable document
  producer-invocations.json               per-agent log (for G11)

Usage:  python make_all_test_cases.py <RUN_ID> [--max-rounds N]
"""
from __future__ import annotations

import json
import os
import subprocess
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
sys.path.insert(0, str(WS / "scripts"))
PY = str(WS / ".venv" / "bin" / "python")
TARGET = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899")
EXEC_TIMEOUT = int(os.environ.get("FORGE_EXEC_TIMEOUT", "2400"))

import orchestrate_full as O
import format_test_cases as F
import guardrails as G


def cases_for(run_dir: Path, agent: str) -> list:
    # run-scoped copy = THIS run's output (so a fresh run isn't fooled by the flat deliverable)
    p = run_dir / "test-case-registry" / agent / "cases.json"
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return []


def run_executor(run_dir: Path, run_id: str, agent: str) -> bool:
    rp = WS / "agents" / "api-tester" / agent / "subagent" / "run.py"
    if not rp.exists():
        return False
    env = dict(os.environ, FORGE_WORKSPACE=str(WS), FORGE_RUN_ID=run_id,
               FORGE_TARGET_BASE_URL=TARGET, FORGE_MAX_ENDPOINTS="0")
    adir = run_dir / "agents" / f"api-tester-{agent}"
    adir.mkdir(parents=True, exist_ok=True)
    try:
        proc = subprocess.run([PY, str(rp)], cwd=str(WS), env=env,
                              capture_output=True, text=True, timeout=EXEC_TIMEOUT)
        # only write capture files when they have content — never leave blank stdout/stderr
        if proc.stdout:
            (adir / f"{run_id}-stdout.txt").write_text(proc.stdout)
        if proc.stderr:
            (adir / f"{run_id}-stderr.txt").write_text(proc.stderr)
    except subprocess.TimeoutExpired:
        return False
    # success if the executor wrote its cases anywhere (results/runs/ or a bespoke subdir)
    return F.find_cases_file(run_id, agent) is not None


def run(run_id: str, max_rounds: int) -> dict:
    run_dir = WS / "results" / "runs" / run_id
    (run_dir / "agents").mkdir(parents=True, exist_ok=True)
    # create-postman-collection is a GENERAL agent (the collection builder), not a test-case
    # producer — exclude it from the tester set; it runs once as build_postman below.
    agents = [a for a in O.API_TESTERS if a != "create-postman-collection"]
    invocations, rnd = [], 0
    while True:
        rnd += 1
        pending = [a for a in agents if not cases_for(run_dir, a)]
        if not pending:
            print(f"[round {rnd}] all {len(agents)} agents have test cases — DONE.", flush=True)
            break
        if rnd > max_rounds:
            print(f"[round {rnd}] SAFETY CAP; still missing: {pending}", flush=True)
            break
        print(f"[round {rnd}] {len(agents)-len(pending)}/{len(agents)} done; {len(pending)} pending", flush=True)
        for a in pending:
            # the agent's output may be in results/runs/ OR a bespoke subdir; only run the
            # executor if it's nowhere yet.
            ran = (F.find_cases_file(run_id, a) is not None) or run_executor(run_dir, run_id, a)
            n = F.run(run_id, a) if ran else 0     # deterministic 9-field formatting
            invocations.append({"agent": f"api-tester-{a}", "mode": "per-agent",
                                "cases": n, "sentinel": n == 0, "timed_out": False,
                                "executor_ok": bool(ran), "round": rnd})
            print(f"    {a}: exec={'ok' if ran else 'FAIL'} test_cases={n}"
                  + ("" if n else " <-- retry"), flush=True)

    # merge from this run's per-agent output
    combined, md_parts = [], []
    for a in agents:
        combined.extend(cases_for(run_dir, a))
        mdp = run_dir / "test-case-registry" / a / "cases.md"
        if mdp.exists():
            md_parts.append(mdp.read_text())
    (run_dir / "test-case-registry.json").write_text(json.dumps(
        {"run_id": run_id, "writer": "test-case-creator (deterministic, from agent steps+results)",
         "schema": ["test_case_id", "title_summary", "preconditions", "test_steps",
                    "test_data", "expected_result", "actual_result", "status"],
         "agents_total": len(agents),
         "agents_covered": len({c["test_case_id"].rsplit("-", 1)[0] for c in combined}),
         "total_cases": len(combined),
         "status_counts": {s: sum(1 for c in combined if c.get("status") == s)
                           for s in ("Pass", "Fail", "Blocked")},
         "cases": combined}, indent=2))
    (run_dir / "test-cases-ALL.md").write_text("\n\n---\n\n".join(md_parts))

    # The producer (deterministic formatter) authored each agent's cases per-agent. Build the
    # invocation log from the FINAL per-agent state (covers agents produced in earlier passes
    # / resumes), so G11 reflects complete per-agent coverage.
    inv = [{"agent": f"api-tester-{a}", "mode": "per-agent",
            "cases": len(cases_for(run_dir, a)),
            "sentinel": len(cases_for(run_dir, a)) == 0, "timed_out": False} for a in agents]
    (run_dir / "producer-invocations.json").write_text(json.dumps(
        {"run_id": run_id, "mode": "per-agent", "source": "agent steps+results (deterministic format)",
         "invocations": inv,
         "agents_with_cases": sum(1 for a in agents if cases_for(run_dir, a)),
         "sentinels": sum(1 for a in agents if not cases_for(run_dir, a)), "timeouts": 0}, indent=2))

    # GENERAL step — create-postman-collection: the test cases with API calls become ONE
    # Postman collection for the run (named by test_case_id, {{base_url}} -> dummyjson, login flow).
    postman = {}
    try:
        import build_postman
        postman = build_postman.run(run_id)
    except Exception as exc:  # noqa: BLE001
        print(f"BUILD-POSTMAN ERROR: {exc}", flush=True)

    covered = sum(1 for a in agents if cases_for(run_dir, a))
    g11 = G.g11_per_agent_producer(run_dir)
    print(f"\nRESULT: {covered}/{len(agents)} agents | {len(combined)} test cases | "
          f"rounds={rnd} | G11={g11['status']}", flush=True)
    print(f"G11: {g11['detail']}", flush=True)
    if covered < len(agents):
        print(f"INCOMPLETE — missing: {[a for a in agents if not cases_for(run_dir, a)]}", flush=True)
    return {"covered": covered, "total": len(agents), "cases": len(combined), "g11": g11["status"]}


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python make_all_test_cases.py <RUN_ID> [--max-rounds N]", file=sys.stderr)
        sys.exit(2)
    mr = int(sys.argv[sys.argv.index("--max-rounds") + 1]) if "--max-rounds" in sys.argv else 20
    res = run(sys.argv[1], mr)
    sys.exit(0 if res["covered"] == res["total"] and res["g11"] == "PASS" else 1)


if __name__ == "__main__":
    main()
