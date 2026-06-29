#!/usr/bin/env python3
"""Self-evolution loop (SkillOpt + SkillClaw) for the
api-tester / validate-search-and-filter-queries workflow. Staged — never auto-adopts.

The manual `/evolve` trigger and the body the nightly sleep cycle runs for THIS
workflow, wired to the central backend and the judge metric (Search-and-Filter Test
Fidelity).

  SkillOpt (per-agent, vertical):
    For each agent, propose a bounded edit to its skill document, evaluate the
    candidate on the HELD-OUT collection
    (results/validate-search-and-filter-queries/held_out.jsonl -> /widgets) using the
    judge metric, and ACCEPT only on STRICT improvement of held-out fidelity. Accept
    or reject, the proposal + decision is STAGED under
    evolvers/skillopt/validate-search-and-filter-queries/<agent>/staged/. best_skill.md
    is never overwritten here.

  SkillClaw (collective, horizontal):
    The shared pool (evolvers/skillclaw/searchfilter-shared/SKILL.md, local filesystem,
    air-gapped) is offered to all agents. This records the share manifest; adoption
    stays the user's call.

All target HTTP is read-only GET against the local seeded SUT; DummyJSON is never used.

Usage:
    python evolvers/evolve_searchfilter.py [--agents langgraph,crewai,...] [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
WF = "validate-search-and-filter-queries"
AGENTS = ["langgraph", "crewai", "claude_sdk", "api-tester-validate-search-and-filter-queries"]
BASE = f"agents/api-tester-{WF}"
AGENT_DIR = {
    "langgraph": f"{BASE}/langgraph/run.py",
    "crewai": f"{BASE}/crewai/run.py",
    "claude_sdk": f"{BASE}/claude_sdk/run.py",
    "api-tester-validate-search-and-filter-queries": f"{BASE}/subagent/run.py",
}


def _held_out_collections() -> list[str]:
    out = []
    p = WS / "results" / WF / "held_out.jsonl"
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line)["collection"])
    return out


def _gold_truth(cols: set[str]) -> dict:
    gold = json.loads((WS / "data" / WF / "gold.json").read_text())
    truth = {}
    for col in gold["collections"]:
        if col["collection"] in cols:
            for s in col["scenarios"]:
                truth[(col["collection"], s["scenario"])] = s["observed_token"]
    return truth


def _candidate_skill(base_doc: str) -> str:
    """Bounded add edit distilled from the SkillClaw shared pool: reinforce all five
    cases, the two-filter AND request, the out-of-enum invalid probe, the unknown
    parameter probe, and the empty-result probe — addressing the plausible failures
    where a model collapses a case, degrades the multi-filter to one filter, 'fixes'
    the invalid value, or expects a 404 for the empty result."""
    addition = ("Always emit all five cases in order and never drop or collapse one; keep every "
                "params value and parameter name a literal JSON string exactly as specified; keep "
                "the multi_filter case carrying both status and category so the AND of two filters "
                "is exercised; keep the invalid_value status exactly \"unknown_value\" so enum "
                "validation is triggered; keep the unknown_param name exactly \"bogus_filter\"; and "
                "keep the empty_result case as status=active with category=C so the empty-match path "
                "is exercised and expected to return 200, never 404.")
    return base_doc.rstrip() + "\n" + addition + "\n"


def _run_agent_on_heldout(agent: str, skill_doc: Path | None, run_id: str,
                          cols: list[str]) -> Path:
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(WS)
    env["FORGE_SANDBOX_ROOT"] = str(WS)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_TARGET_BASE_URL"] = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8920")
    env["FORGE_ONLY_COLLECTIONS"] = ",".join(cols)
    env["PATH"] = str(WS / ".venv" / "bin") + os.pathsep + env.get("PATH", "")
    if skill_doc is not None:
        env["FORGE_SKILL_DOC"] = str(skill_doc)
    else:
        env.pop("FORGE_SKILL_DOC", None)
    subprocess.run([str(WS / ".venv" / "bin" / "python"), AGENT_DIR[agent]],
                   cwd=str(WS), env=env, capture_output=True, text=True)
    return WS / "results" / "runs" / run_id / f"{agent}.cases.json"


def _heldout_fidelity(cases_path: Path, truth: dict) -> float:
    if not cases_path.exists():
        return 0.0
    doc = json.loads(cases_path.read_text())
    obs = {}
    for col in doc.get("collections", []):
        for s in col.get("scenarios", []):
            obs[(col["collection"], s["scenario"])] = s.get("observed_token")
    denom = len(truth)
    if not denom:
        return 0.0
    matches = sum(1 for k, g in truth.items()
                  if obs.get(k) == g and obs.get(k) not in (None, "missing"))
    return round(100.0 * matches / denom, 2)


def skillopt_for_agent(agent: str, cols: list[str], truth: dict) -> dict:
    base = WS / "evolvers" / "skillopt" / WF / agent / "best_skill.md"
    staged = WS / "evolvers" / "skillopt" / WF / agent / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    cand_path = staged / "candidate_skill.md"
    cand_path.write_text(_candidate_skill(base.read_text()))

    base_cases = _run_agent_on_heldout(agent, None, f"evolve-sf-{agent}-base", cols)
    base_fid = _heldout_fidelity(base_cases, truth)
    cand_cases = _run_agent_on_heldout(agent, cand_path, f"evolve-sf-{agent}-cand", cols)
    cand_fid = _heldout_fidelity(cand_cases, truth)

    accepted = cand_fid > base_fid
    decision = {"agent": agent, "ts": datetime.now(timezone.utc).isoformat(),
                "metric": "search_filter_test_fidelity_heldout", "held_out_collections": cols,
                "baseline_fidelity": base_fid, "candidate_fidelity": cand_fid,
                "accepted": accepted, "candidate_skill_path": str(cand_path),
                "note": ("STRICT-improvement gate. ACCEPTED candidate is STAGED only — "
                         "best_skill.md is NOT overwritten. Adopt manually after review.")}
    (staged / "decision.json").write_text(json.dumps(decision, indent=2))
    return decision


def skillclaw_share() -> dict:
    pool = WS / "evolvers" / "skillclaw" / "searchfilter-shared" / "SKILL.md"
    manifest = {"shared_skill": str(pool), "ts": datetime.now(timezone.utc).isoformat(),
                "offered_to": AGENTS, "backend": "local_filesystem", "air_gapped": True,
                "note": "Shared skill available to all agents; adoption is the user's call."}
    (WS / "evolvers" / "skillclaw" / "searchfilter_share_manifest.json").write_text(
        json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    cols = _held_out_collections()
    truth = _gold_truth(set(cols))

    print(f"Self-evolution (staged) · held-out = {cols} · {len(truth)} gold scenarios")
    if a.dry_run:
        print("[dry-run] would run SkillOpt held-out gate + SkillClaw share; no agent calls made.")
        skillclaw_share()
        return 0
    print("SkillOpt — per-agent, gated on held-out fidelity (strict improvement):\n")
    decisions = [skillopt_for_agent(ag, cols, truth) for ag in agents]
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
