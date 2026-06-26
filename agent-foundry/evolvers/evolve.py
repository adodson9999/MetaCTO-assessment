#!/usr/bin/env python3
"""Self-evolution loop (SkillOpt + SkillClaw), staged — never auto-adopts.

This is the manual `/evolve` trigger and the body the nightly sleep cycle runs.
It embodies the two mechanisms from references/evolution.md, wired to THIS
foundry's task, the central backend, and the judge metric:

  SkillOpt (per-agent, vertical):
    For each agent, propose a bounded edit to its skill document, evaluate the
    candidate on the HELD-OUT endpoints (results/held_out.jsonl) using the judge
    metric (Contract-Test Fidelity), and ACCEPT the edit only if it STRICTLY
    improves held-out fidelity. Accept or reject, the proposal + decision is
    STAGED under evolvers/skillopt/<agent>/staged/ for the user to review.
    best_skill.md is never overwritten here.

  SkillClaw (collective, horizontal):
    The shared skill pool (evolvers/skillclaw/shared/SKILL.md, local filesystem,
    air-gapped) is distilled from run artifacts and offered to all agents. This
    step records the share manifest; adoption stays the user's call.

Gate metric = judge/metric.json (the same number that ranks the agents).
Held-out split = results/held_out.jsonl (disjoint role from the ranking purpose,
so optimization cannot tune the exact items it is graded on at rank time).

Usage:
    python evolvers/evolve.py [--agents langgraph,crewai,...] [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
AGENTS = ["langgraph", "crewai", "claude_sdk", "api-tester-validate-request-payloads"]


def _held_out_slugs() -> list[str]:
    out = []
    for line in (WS / "results" / "held_out.jsonl").read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line)["slug"])
    return out


def _gold_truth(slugs: set[str]) -> dict:
    gold = json.loads((WS / "data" / "gold.json").read_text())
    truth = {}
    for ep in gold["endpoints"]:
        if ep["slug"] in slugs:
            for c in ep["cases"]:
                if c["applicable"]:
                    truth[(ep["slug"], c["variant"])] = c["actual_class"]
    return truth


def _candidate_skill(base_doc: str) -> str:
    """Bounded add edit: append one targeted clarification distilled from the
    SkillClaw shared pool, addressing the observed inv_maxlength coverage gap."""
    addition = ('When maxLength_string_field is not null you must always produce the '
                '"inv_maxlength" body as a string of length maxLength+1 for that field, '
                'and never output null for "inv_maxlength" in that case.')
    return base_doc.rstrip() + "\n" + addition + "\n"


def _run_agent_on_heldout(agent: str, skill_doc: Path | None, run_id: str,
                          slugs: list[str]) -> Path:
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(WS)
    env["FORGE_SANDBOX_ROOT"] = str(WS)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_TARGET_BASE_URL"] = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899")
    env["FORGE_ONLY_SLUGS"] = ",".join(slugs)
    env["PATH"] = str(WS / ".venv" / "bin") + os.pathsep + env.get("PATH", "")
    if skill_doc is not None:
        env["FORGE_SKILL_DOC"] = str(skill_doc)
    else:
        env.pop("FORGE_SKILL_DOC", None)
    subprocess.run([str(WS / ".venv" / "bin" / "python"), f"agents/{agent}/run.py"],
                   cwd=str(WS), env=env, capture_output=True, text=True)
    return WS / "results" / "runs" / run_id / f"{agent}.cases.json"


def _heldout_fidelity(cases_path: Path, truth: dict) -> float:
    if not cases_path.exists():
        return 0.0
    doc = json.loads(cases_path.read_text())
    obs = {(c["slug"], c["variant"]): c["actual_class"]
           for c in doc.get("cases", []) if c.get("applicable") and c.get("covered")}
    denom = len(truth)
    if not denom:
        return 0.0
    matches = sum(1 for k, g in truth.items() if obs.get(k) == g)
    return round(100.0 * matches / denom, 2)


def skillopt_for_agent(agent: str, slugs: list[str], truth: dict, dry: bool) -> dict:
    base_doc = (WS / "evolvers" / "skillopt" / agent / "best_skill.md").read_text()
    staged = WS / "evolvers" / "skillopt" / agent / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    cand_path = staged / "candidate_skill.md"
    cand_path.write_text(_candidate_skill(base_doc))

    base_cases = _run_agent_on_heldout(agent, None, f"evolve-{agent}-base", slugs)
    base_fid = _heldout_fidelity(base_cases, truth)
    cand_cases = _run_agent_on_heldout(agent, cand_path, f"evolve-{agent}-cand", slugs)
    cand_fid = _heldout_fidelity(cand_cases, truth)

    accepted = cand_fid > base_fid  # STRICT improvement on held-out
    decision = {
        "agent": agent, "ts": datetime.now(timezone.utc).isoformat(),
        "metric": "contract_test_fidelity_heldout",
        "held_out_endpoints": slugs,
        "baseline_fidelity": base_fid, "candidate_fidelity": cand_fid,
        "accepted": accepted,
        "candidate_skill_path": str(cand_path),
        "note": ("STRICT-improvement gate. ACCEPTED candidate is STAGED only — "
                 "best_skill.md is NOT overwritten. Adopt manually after review."),
    }
    (staged / "decision.json").write_text(json.dumps(decision, indent=2))
    return decision


def skillclaw_share() -> dict:
    pool = WS / "evolvers" / "skillclaw" / "shared" / "SKILL.md"
    manifest = {"shared_skill": str(pool), "ts": datetime.now(timezone.utc).isoformat(),
                "offered_to": AGENTS, "backend": "local_filesystem", "air_gapped": True,
                "note": "Shared skill available to all agents; adoption is the user's call."}
    (WS / "evolvers" / "skillclaw" / "share_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    slugs = _held_out_slugs()
    truth = _gold_truth(set(slugs))

    print(f"Self-evolution (staged) · held-out = {slugs} · {len(truth)} gold cases")
    print("SkillOpt — per-agent, gated on held-out fidelity (strict improvement):\n")
    decisions = [skillopt_for_agent(ag, slugs, truth, a.dry_run) for ag in agents]
    print(f"{'agent':24} {'baseline':>9} {'candidate':>10} {'decision':>10}")
    for d in decisions:
        verdict = "ACCEPT*" if d["accepted"] else "reject"
        print(f"{d['agent']:24} {d['baseline_fidelity']:>9} {d['candidate_fidelity']:>10} {verdict:>10}")
    man = skillclaw_share()
    print(f"\nSkillClaw — shared skill offered to {len(man['offered_to'])} agents "
          f"(local, air-gapped): {man['shared_skill']}")
    print("\n* ACCEPTED proposals are STAGED under evolvers/skillopt/<agent>/staged/.")
    print("  Nothing was adopted. Review decision.json + candidate_skill.md, then adopt manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
