#!/usr/bin/env python3
# Used by: orchestrator — run-scoped test-case producer across ALL agents.
"""Retry-until-complete producer: keep running the test-case-creator (the SOLE producer,
per-agent) until it has successfully authored the test cases for EVERY api-tester — no
sentinels, no gaps. Does NOT stop after one pass; retries only the still-missing agents
each round until all 40 succeed (or a hard safety cap).

Layout — a folder per agent:
    results/runs/<RUN_ID>/test-case-registry/<agent>/cases.json   (that agent's cases)
    results/runs/<RUN_ID>/test-case-registry.json                 (merged, all agents)
    results/runs/<RUN_ID>/producer-invocations.json               (per-agent log)

Guardrail G11 (per-agent producer) is asserted at the end; success == every executed
api-tester has cases > 0 and G11 == PASS.

Usage:  python produce_all_testcases.py <RUN_ID> [--max-rounds N]
Env:    FORGE_TESTCASE_AGENT_TIMEOUT (per-call bound, default 300s)
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
sys.path.insert(0, str(WS / "scripts"))
import orchestrate_full as O  # run_scoped_producer + API_TESTERS
import guardrails as G


def agent_folder(run_dir: Path, agent: str) -> Path:
    d = run_dir / "test-case-registry" / agent
    d.mkdir(parents=True, exist_ok=True)
    return d


def cases_for(run_dir: Path, agent: str) -> list:
    """Real (non-ERROR) cases recorded for an agent — ONLY the canonical per-agent FOLDER
    layout counts as 'done', so every agent ends with a folder AND an invocation record
    (G11). A stray file-only slice from an earlier pass does NOT count as complete."""
    p = run_dir / "test-case-registry" / agent / "cases.json"
    try:
        data = json.loads(p.read_text())
        return [c for c in data if c.get("outcome") != "ERROR"]
    except (OSError, json.JSONDecodeError):
        return []


def produce_one(run_dir: Path, run_id: str, agent: str) -> dict:
    """One scoped producer call for an agent; mirror its slice into the per-agent folder."""
    rec = O.run_scoped_producer(run_dir, run_id, agent)
    src = run_dir / "test-case-registry" / f"{agent}.json"
    try:
        slice_cases = json.loads(src.read_text())
    except (OSError, json.JSONDecodeError):
        slice_cases = []
    (agent_folder(run_dir, agent) / "cases.json").write_text(json.dumps(slice_cases, indent=2))
    return rec


def run(run_id: str, max_rounds: int) -> dict:
    run_dir = WS / "results" / "runs" / run_id
    (run_dir / "agents").mkdir(parents=True, exist_ok=True)
    agents = list(O.API_TESTERS)
    # carry forward any invocations already logged (so re-runs accumulate to all 40)
    try:
        prior = json.loads((run_dir / "producer-invocations.json").read_text()).get("invocations", [])
    except (OSError, json.JSONDecodeError):
        prior = []
    invocations, rounds = list(prior), []
    rnd = 0
    while True:
        rnd += 1
        pending = [a for a in agents if not cases_for(run_dir, a)]
        if not pending:
            print(f"[round {rnd}] all {len(agents)} agents have cases — DONE.", flush=True)
            break
        if rnd > max_rounds:
            print(f"[round {rnd}] SAFETY CAP hit; still missing: {pending}", flush=True)
            break
        print(f"[round {rnd}] {len(agents)-len(pending)}/{len(agents)} done; "
              f"producing {len(pending)} pending: {pending[:6]}{'...' if len(pending)>6 else ''}", flush=True)
        done_this = 0
        for a in pending:
            rec = produce_one(run_dir, run_id, a)
            rec["round"] = rnd
            invocations.append(rec)
            ok = rec["cases"] > 0
            done_this += int(ok)
            print(f"    {a}: {rec['cases']} cases {rec['seconds']}s"
                  + (" TIMEOUT" if rec["timed_out"] else "") + ("" if ok else " <-- retry next round"), flush=True)
        rounds.append({"round": rnd, "attempted": len(pending), "succeeded": done_this})

    # merge folders -> single registry
    combined = []
    for a in agents:
        combined.extend(cases_for(run_dir, a))
    (run_dir / "test-case-registry.json").write_text(json.dumps(
        {"run_id": run_id, "writer": "test-case-creator (per-agent, retry-until-complete)",
         "agents_covered": len({c.get("agent") for c in combined}),
         "agents_total": len(agents), "total_cases": len(combined),
         "rounds": rounds, "cases": combined}, indent=2))
    # producer-invocations.json in the shape G11 expects (last call per agent wins)
    last = {}
    for rec in invocations:
        last[rec["agent"]] = rec
    inv_list = list(last.values())
    (run_dir / "producer-invocations.json").write_text(json.dumps(
        {"run_id": run_id, "mode": "per-agent", "rounds": rounds,
         "invocations": inv_list,
         "agents_with_cases": sum(1 for a in agents if cases_for(run_dir, a)),
         "sentinels": sum(1 for a in agents if not cases_for(run_dir, a)),
         "timeouts": sum(1 for i in inv_list if i.get("timed_out"))}, indent=2))

    covered = sum(1 for a in agents if cases_for(run_dir, a))
    g11 = G.g11_per_agent_producer(run_dir)
    print(f"\nRESULT: {covered}/{len(agents)} agents have test cases | total {len(combined)} cases "
          f"| rounds={rnd} | G11={g11['status']}", flush=True)
    print(f"G11: {g11['detail']}", flush=True)
    if covered < len(agents):
        missing = [a for a in agents if not cases_for(run_dir, a)]
        print(f"INCOMPLETE — missing: {missing}", flush=True)
    return {"covered": covered, "total": len(agents), "g11": g11["status"], "rounds": rnd}


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python produce_all_testcases.py <RUN_ID> [--max-rounds N]", file=sys.stderr)
        sys.exit(2)
    mr = 25
    if "--max-rounds" in sys.argv:
        mr = int(sys.argv[sys.argv.index("--max-rounds") + 1])
    res = run(sys.argv[1], mr)
    sys.exit(0 if res["covered"] == res["total"] and res["g11"] == "PASS" else 1)


if __name__ == "__main__":
    main()
