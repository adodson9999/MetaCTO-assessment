#!/usr/bin/env python3
# Used by: orchestrator — agent handoff across ALL agents.
"""Run the handoff flow for ALL 40 api-testers, retry-until-complete.

For each agent: run its executor (records steps + results) -> hand that off as the
test-case-creator's How-section -> the test-case-creator formats it into the registry slice.
The agent supplies steps+results; the test-case-creator is the SOLE author of the cases.
Does not stop after one pass: any agent whose producer yields no cases is retried (executor
output is reused; only the producer re-runs) until every agent has cases, then G11 is asserted.

Layout:  results/runs/<RUN>/handoff/<agent>.md            (the agent's handed-off steps+results)
         results/runs/<RUN>/test-case-registry/<agent>/cases.json
         results/runs/<RUN>/test-case-registry.json        (merged)
         results/runs/<RUN>/producer-invocations.json

Usage:  python handoff_all.py <RUN_ID> [--max-rounds N]
"""
from __future__ import annotations

import json
import os
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
sys.path.insert(0, str(WS / "scripts"))
import agent_handoff as H
import orchestrate_full as O
import guardrails as G


def cases_for(run_dir: Path, agent: str) -> list:
    p = run_dir / "test-case-registry" / agent / "cases.json"
    try:
        return [c for c in json.loads(p.read_text()) if c.get("outcome") != "ERROR"]
    except (OSError, json.JSONDecodeError):
        return []


def run(run_id: str, max_rounds: int) -> dict:
    run_dir = WS / "results" / "runs" / run_id
    (run_dir / "agents").mkdir(parents=True, exist_ok=True)
    agents = list(O.API_TESTERS)
    invocations, rounds = [], []
    rnd = 0
    while True:
        rnd += 1
        pending = [a for a in agents if not cases_for(run_dir, a)]
        if not pending:
            print(f"[round {rnd}] all {len(agents)} agents have cases — DONE.", flush=True)
            break
        if rnd > max_rounds:
            print(f"[round {rnd}] SAFETY CAP; still missing: {pending}", flush=True)
            break
        print(f"[round {rnd}] {len(agents)-len(pending)}/{len(agents)} done; {len(pending)} pending", flush=True)
        for a in pending:
            # executor only needs to run once (reuse its cases.json on retries)
            cf = run_dir / f"api-tester-{a}.cases.json"
            ran = cf.exists() or H.run_executor(run_dir, run_id, a)
            hp, steps = H.write_handoff(run_dir, a) if ran else (None, 0)
            prod = H.run_producer(run_dir, run_id, a) if hp else {"agent": f"api-tester-{a}",
                                                                  "cases": 0, "sentinel": True}
            prod.update({"round": rnd, "handoff_steps": steps, "executor_ok": bool(ran),
                         "mode": "per-agent", "timed_out": False})
            invocations.append(prod)
            print(f"    {a}: exec={'ok' if ran else 'FAIL'} steps={steps} "
                  f"cases={prod['cases']}" + ("" if prod["cases"] else " <-- retry"), flush=True)

    # merge + invocations + G11
    combined = []
    for a in agents:
        combined.extend(cases_for(run_dir, a))
    (run_dir / "test-case-registry.json").write_text(json.dumps(
        {"run_id": run_id, "writer": "test-case-creator (from agent handoff: steps+results)",
         "agents_covered": len({c.get("agent") for c in combined}), "agents_total": len(agents),
         "total_cases": len(combined), "cases": combined}, indent=2))
    last = {}
    for r in invocations:
        last[r["agent"]] = r
    inv_list = list(last.values())
    (run_dir / "producer-invocations.json").write_text(json.dumps(
        {"run_id": run_id, "mode": "per-agent", "source": "agent-handoff", "rounds": rounds,
         "invocations": inv_list,
         "agents_with_cases": sum(1 for a in agents if cases_for(run_dir, a)),
         "sentinels": sum(1 for a in agents if not cases_for(run_dir, a)),
         "timeouts": 0}, indent=2))

    covered = sum(1 for a in agents if cases_for(run_dir, a))
    g11 = G.g11_per_agent_producer(run_dir)
    print(f"\nRESULT: {covered}/{len(agents)} agents | {len(combined)} cases | "
          f"rounds={rnd} | G11={g11['status']}", flush=True)
    print(f"G11: {g11['detail']}", flush=True)
    if covered < len(agents):
        print(f"INCOMPLETE — missing: {[a for a in agents if not cases_for(run_dir, a)]}", flush=True)
    return {"covered": covered, "total": len(agents), "g11": g11["status"]}


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python handoff_all.py <RUN_ID> [--max-rounds N]", file=sys.stderr)
        sys.exit(2)
    mr = 25
    if "--max-rounds" in sys.argv:
        mr = int(sys.argv[sys.argv.index("--max-rounds") + 1])
    res = run(sys.argv[1], mr)
    sys.exit(0 if res["covered"] == res["total"] and res["g11"] == "PASS" else 1)


if __name__ == "__main__":
    main()
