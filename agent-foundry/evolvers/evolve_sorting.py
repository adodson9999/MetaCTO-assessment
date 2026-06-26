#!/usr/bin/env python3
"""Self-evolution loop (SkillOpt + SkillClaw) for the
api-tester / verify-sorting-behavior workflow. Staged — never auto-adopts.

The manual `/evolve` trigger and the body the nightly sleep cycle runs for THIS
workflow, wired to the central backend and the judge metric (Sort-Test Fidelity).

  SkillOpt (per-agent, vertical):
    For each agent, propose a bounded edit to its skill document, evaluate the
    candidate against the gold scenarios using the judge metric, and ACCEPT only on
    STRICT improvement of fidelity. Unlike the multi-collection tasks, this workflow
    has a SINGLE seeded reference resource, so there are no held-out collections to
    split on; the gate evaluates fidelity over the full 12-scenario gold set. Accept
    or reject, the proposal + decision is STAGED under
    evolvers/skillopt/verify-sorting-behavior/<agent>/staged/. best_skill.md is never
    overwritten here.

  SkillClaw (collective, horizontal):
    The shared pool (evolvers/skillclaw/sorting-shared/SKILL.md, local filesystem,
    air-gapped) is offered to all agents. This records the share manifest; adoption
    stays the user's call.

DummyJSON is never used or modified by this task — the harness seeds an isolated,
in-process, loopback-only reference resource and issues read-only GETs to it.

Usage:
    python evolvers/evolve_sorting.py [--agents langgraph,crewai,...] [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
WF = "verify-sorting-behavior"
AGENTS = ["langgraph", "crewai", "claude_sdk", "api-tester-verify-sorting-behavior"]
BASE = f"agents/api-tester-{WF}"
AGENT_DIR = {
    "langgraph": f"{BASE}/langgraph/run.py",
    "crewai": f"{BASE}/crewai/run.py",
    "claude_sdk": f"{BASE}/claude_sdk/run.py",
    "api-tester-verify-sorting-behavior": f"{BASE}/subagent/run.py",
}


def _gold_truth() -> dict:
    gold = json.loads((WS / "data" / WF / "gold.json").read_text())
    return {s["scenario"]: s["observed_token"] for s in gold.get("scenarios", [])}


def _candidate_skill(base_doc: str) -> str:
    """Bounded add edit distilled from the SkillClaw shared pool: reinforce the
    twenty-record seed, the non-alphabetical name order, the fixed created_at base +
    two-second step, full ordering coverage, and the two precise negative probes —
    addressing the plausible failures where a model shortens the seed, alphabetises
    the names, drifts the timestamps, or mis-constructs the 400 probes."""
    addition = ("Always emit exactly twenty seed records each with both name and "
                "created_at, keep the twenty names in the given non-alphabetical order, set the "
                "first created_at to \"2026-06-25T12:00:00Z\" with a strict two-second step in "
                "ISO-8601 UTC with a trailing Z, emit all six sort cases with the correct field and "
                "direction on each order case, and construct invalid_sort_field as only "
                "sort=\"nonexistent_field\" expecting 400 and invalid_order_direction as "
                "sort=\"name\" with order=\"sideways\" expecting 400.")
    return base_doc.rstrip() + "\n" + addition + "\n"


def _run_agent(agent: str, skill_doc: Path | None, run_id: str) -> Path:
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(WS)
    env["FORGE_SANDBOX_ROOT"] = str(WS)
    env["FORGE_RUN_ID"] = run_id
    env["PATH"] = str(WS / ".venv" / "bin") + os.pathsep + env.get("PATH", "")
    if skill_doc is not None:
        env["FORGE_SKILL_DOC"] = str(skill_doc)
    else:
        env.pop("FORGE_SKILL_DOC", None)
    subprocess.run([str(WS / ".venv" / "bin" / "python"), AGENT_DIR[agent]],
                   cwd=str(WS), env=env, capture_output=True, text=True)
    return WS / "results" / "runs" / run_id / f"{agent}.cases.json"


def _fidelity(cases_path: Path, truth: dict) -> float:
    if not cases_path.exists():
        return 0.0
    doc = json.loads(cases_path.read_text())
    obs = {s["scenario"]: s.get("observed_token") for s in doc.get("scenarios", [])}
    denom = len(truth)
    if not denom:
        return 0.0
    matches = sum(1 for k, g in truth.items()
                  if obs.get(k) == g and obs.get(k) not in (None, "missing"))
    return round(100.0 * matches / denom, 2)


def skillopt_for_agent(agent: str, truth: dict) -> dict:
    base = WS / "evolvers" / "skillopt" / WF / agent / "best_skill.md"
    staged = WS / "evolvers" / "skillopt" / WF / agent / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    cand_path = staged / "candidate_skill.md"
    cand_path.write_text(_candidate_skill(base.read_text()))

    base_cases = _run_agent(agent, None, f"evolve-sort-{agent}-base")
    base_fid = _fidelity(base_cases, truth)
    cand_cases = _run_agent(agent, cand_path, f"evolve-sort-{agent}-cand")
    cand_fid = _fidelity(cand_cases, truth)

    accepted = cand_fid > base_fid
    decision = {"agent": agent, "ts": datetime.now(timezone.utc).isoformat(),
                "metric": "sort_test_fidelity_gold", "scenarios": len(truth),
                "baseline_fidelity": base_fid, "candidate_fidelity": cand_fid,
                "accepted": accepted, "candidate_skill_path": str(cand_path),
                "note": ("STRICT-improvement gate. ACCEPTED candidate is STAGED only — "
                         "best_skill.md is NOT overwritten. Adopt manually after review.")}
    (staged / "decision.json").write_text(json.dumps(decision, indent=2))
    return decision


def skillclaw_share() -> dict:
    pool = WS / "evolvers" / "skillclaw" / "sorting-shared" / "SKILL.md"
    manifest = {"shared_skill": str(pool), "ts": datetime.now(timezone.utc).isoformat(),
                "offered_to": AGENTS, "backend": "local_filesystem", "air_gapped": True,
                "note": "Shared skill available to all agents; adoption is the user's call."}
    (WS / "evolvers" / "skillclaw" / "sorting_share_manifest.json").write_text(
        json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    truth = _gold_truth()

    print(f"Self-evolution (staged) · single seeded resource · {len(truth)} gold scenarios")
    if a.dry_run:
        print("[dry-run] would run SkillOpt fidelity gate + SkillClaw share; no agent calls made.")
        skillclaw_share()
        return 0
    print("SkillOpt — per-agent, gated on gold fidelity (strict improvement):\n")
    decisions = [skillopt_for_agent(ag, truth) for ag in agents]
    print(f"{'agent':46} {'baseline':>9} {'candidate':>10} {'decision':>10}")
    for d in decisions:
        verdict = "ACCEPT*" if d["accepted"] else "reject"
        print(f"{d['agent']:46} {d['baseline_fidelity']:>9} {d['candidate_fidelity']:>10} {verdict:>10}")
    man = skillclaw_share()
    print(f"\nSkillClaw — shared skill offered to {len(man['offered_to'])} agents "
          f"(local, air-gapped): {man['shared_skill']}")
    print(f"\n* ACCEPTED proposals are STAGED under evolvers/skillopt/{WF}/<agent>/staged/.")
    print("  Nothing was adopted. Review decision.json + candidate_skill.md, then adopt manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
