#!/usr/bin/env python3
# Used by: shared — per-agent handoff helper; used by handoff_all across ALL agents.
"""Agent -> test-case-creator handoff.

The architecture: each api-tester agent RUNS its flow, recording the steps it took and the
result of each step (its <agent>.cases.json). That output is the agent's INFORMATION. This
module hands that information to the test-case-creator by rendering it as the How-section the
creator consumes, then the producer formats it into the canonical registry. The agent invents
nothing for the registry; the test-case-creator is the sole author of the formatted cases.

Per agent:
  1. run the agent executor (subagent) over all endpoints -> api-tester-<agent>.cases.json
  2. build_handoff() -> results/runs/<RUN>/handoff/<agent>.md  (steps taken + result, as a How-section)
  3. run the test-case-creator scoped to that agent against a run-manifest of the handoffs
     -> the registry slice for that agent (test-case-registry/<agent>/cases.json)

Usage:  python agent_handoff.py <RUN_ID> --agents a,b      # run+handoff+produce for these agents
        python agent_handoff.py <RUN_ID> --build-only <agent>   # just (re)build a handoff from existing cases
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
TCC_TIMEOUT = int(os.environ.get("FORGE_TESTCASE_AGENT_TIMEOUT", "300"))


def _iter_scenarios(obj):
    if isinstance(obj, dict):
        if isinstance(obj.get("scenarios"), list):
            for s in obj["scenarios"]:
                if isinstance(s, dict):
                    yield s
        for v in obj.values():
            yield from _iter_scenarios(v)
    elif isinstance(obj, list):
        for v in obj:
            yield from _iter_scenarios(v)


def build_handoff(agent: str, cases_data: dict) -> str:
    """Render the agent's recorded steps + results as the test-case-creator's How-section.
    Each step the agent took becomes one numbered step whose Assert states the documented
    expected result; the observed result is carried as context. Nothing is invented."""
    scen = list(_iter_scenarios(cases_data))
    lines = [f"# api-tester-{agent} — agent handoff: steps taken in the flow + results", "",
             "- **How:**"]
    n = 0
    for s in scen:
        label = str(s.get("scenario") or s.get("label") or f"step{n+1}")
        ep = s.get("endpoint") or s.get("collection") or s.get("path") or ""
        ideal = s.get("ideal")
        observed = s.get("observed_token")
        if ideal is None and observed is None:
            continue
        n += 1
        where = f" on {ep}" if ep else ""
        lines.append(
            f"  {n}. Step '{label}'{where}: the agent sent the request and observed "
            f"result '{observed}'. Assert the result is {ideal}.")
    if n == 0:
        lines.append("  1. The agent recorded no step results for this flow. "
                     "Assert the agent produced an empty result set.")
    lines.append("- **Tools:** http")
    lines.append("- **Metric:** Pass: every step's result matches its asserted value. "
                 "Fail: a step result differs from its asserted value.")
    return "\n".join(lines) + "\n"


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
                              capture_output=True, text=True, timeout=2400)
        (adir / f"{run_id}-stdout.txt").write_text(proc.stdout) if proc.stdout else None
        (adir / f"{run_id}-stderr.txt").write_text(proc.stderr) if proc.stderr else None
    except subprocess.TimeoutExpired:
        return False
    return (run_dir / f"api-tester-{agent}.cases.json").exists()


def write_handoff(run_dir: Path, agent: str) -> tuple[Path | None, int]:
    cf = run_dir / f"api-tester-{agent}.cases.json"
    try:
        data = json.loads(cf.read_text())
    except (OSError, json.JSONDecodeError):
        return None, 0
    section = build_handoff(agent, data)
    hdir = run_dir / "handoff"
    hdir.mkdir(parents=True, exist_ok=True)
    hp = hdir / f"{agent}.md"
    hp.write_text(section)
    steps = section.count("\n  ")  # rough; precise count below
    import re
    steps = len(re.findall(r"(?m)^\s*\d+\.\s", section))
    return hp, steps


def run_producer(run_dir: Path, run_id: str, agent: str) -> dict:
    """test-case-creator scoped to this agent, reading the run handoff manifest."""
    # build a one-entry manifest pointing at this agent's handoff
    target = f"api-tester-{agent}"
    man = run_dir / "handoff" / "manifest.json"
    entries = []
    try:
        entries = json.loads(man.read_text())
    except (OSError, json.JSONDecodeError):
        entries = []
    rel = f"results/runs/{run_id}/handoff/{agent}.md"
    entries = [e for e in entries if e.get("name") != target]
    entries.append({"name": target, "spec_path": rel, "enabled": True})
    man.write_text(json.dumps(entries, indent=2))

    rp = WS / "agents" / "general" / "test-case-creator" / "subagent" / "run.py"
    env = dict(os.environ, FORGE_WORKSPACE=str(WS), FORGE_RUN_ID=run_id,
               FORGE_TESTCASE_MANIFEST=str(man), FORGE_TESTCASE_AGENT=target)
    try:
        subprocess.run([PY, str(rp)], cwd=str(WS), env=env,
                       capture_output=True, text=True, timeout=TCC_TIMEOUT)
    except subprocess.TimeoutExpired:
        pass
    try:
        emitted = json.loads((run_dir / "general-test-case-creator.emitted-registry.json").read_text())
    except (OSError, json.JSONDecodeError):
        emitted = []
    mine = [c for c in emitted if c.get("agent") == target or str(c.get("tc_id", "")).startswith(target)]
    real = [c for c in mine if c.get("outcome") != "ERROR"]
    slot = run_dir / "test-case-registry" / agent
    slot.mkdir(parents=True, exist_ok=True)
    (slot / "cases.json").write_text(json.dumps(mine, indent=2))
    return {"agent": target, "cases": len(real), "sentinel": len(real) == 0}


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python agent_handoff.py <RUN_ID> [--agents a,b] [--build-only <agent>]", file=sys.stderr)
        sys.exit(2)
    run_id = sys.argv[1]
    run_dir = WS / "results" / "runs" / run_id
    if "--build-only" in sys.argv:
        agent = sys.argv[sys.argv.index("--build-only") + 1]
        hp, steps = write_handoff(run_dir, agent)
        print(f"handoff {agent}: {steps} steps -> {hp}")
        return
    agents = [a.strip() for a in sys.argv[sys.argv.index("--agents") + 1].split(",")] if "--agents" in sys.argv else []
    for a in agents:
        ran = run_executor(run_dir, run_id, a)
        hp, steps = write_handoff(run_dir, a) if ran else (None, 0)
        prod = run_producer(run_dir, run_id, a) if hp else {"cases": 0, "sentinel": True}
        print(f"{a}: executor={'ok' if ran else 'FAIL'} handoff_steps={steps} "
              f"producer_cases={prod['cases']}", flush=True)


if __name__ == "__main__":
    main()
