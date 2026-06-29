#!/usr/bin/env python3
"""Self-evolution loop for the authorization workflow (SkillOpt + SkillClaw),
staged — never auto-adopts. This is the manual `/evolve` trigger / nightly body
for the api-tester/check-authorization-rules build.

  SkillOpt (per-agent, vertical):
    For each agent, propose a bounded edit to its skill document, evaluate the
    candidate on a HELD-OUT subset of sub_tests (results/authz/held_out.jsonl)
    using the judge metric (Authorization-Test Fidelity), and ACCEPT the edit only
    if it STRICTLY improves held-out fidelity. Accept or reject, the proposal +
    decision is STAGED under evolvers/skillopt_authz/<agent>/staged/. best_skill.md
    is never overwritten here.

  SkillClaw (collective, horizontal):
    The shared pool (evolvers/skillclaw_authz/shared/SKILL.md, local FS, air-gapped)
    is offered to all agents; adoption stays the user's call.

Gate metric = judge/metric_authz.json. Held-out split = a disjoint subset of
sub_tests, so optimization cannot tune the exact items it is graded on at rank
time. The agent always emits all eight cases; the gate grades only the held-out
subset.

Usage:
    python evolvers/evolve_authz.py [--agents langgraph,crewai,...] [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
AGENTS = ["langgraph", "crewai", "claude_sdk", "api-tester-check-authorization-rules"]
# per-agent runner (the subagent uses run.py; the others use run_authz.py)
RUNNER = {ag: ("agents/%s/run_authz.py" % ag) for ag in AGENTS}
RUNNER["api-tester-check-authorization-rules"] = "agents/api-tester-check-authorization-rules/run.py"


def _held_out_sub_tests() -> list[str]:
    out = []
    for line in (WS / "results" / "authz" / "held_out.jsonl").read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line)["sub_test"])
    return out


def _gold_truth(sub_tests: set[str]) -> dict:
    gold = json.loads((WS / "data" / "authz" / "gold.json").read_text())
    truth = {}
    for c in gold["sub_tests"]:
        if c["sub_test"] in sub_tests:
            truth[c["sub_test"]] = (c.get("expected_code"), c.get("actual_class"),
                                    bool(c.get("data_exposed")), bool(c.get("leak_safe")))
    return truth


def _candidate_skill(base_doc: str) -> str:
    """Bounded add edit distilled from the SkillClaw pool: reinforce contract-based
    expected_code assignment (the most failure-prone reasoning step)."""
    addition = ("Always assign expected_code by the security contract and never by "
                "what the API returns: 403 for a viewer against the owner resource or "
                "an admin-only endpoint, 200 for ADMIN_GET and VIEWER_LIST, 401 for "
                "the no-token and malformed-token controls.")
    return base_doc.rstrip() + "\n" + addition + "\n"


def _run_agent_heldout(agent: str, skill_doc: Path | None, run_id: str) -> Path:
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(WS)
    env["FORGE_SANDBOX_ROOT"] = str(WS)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_TARGET_BASE_URL"] = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899")
    env["PATH"] = str(WS / ".venv" / "bin") + os.pathsep + env.get("PATH", "")
    if skill_doc is not None:
        env["FORGE_SKILL_DOC"] = str(skill_doc)
    else:
        env.pop("FORGE_SKILL_DOC", None)
    subprocess.run([str(WS / ".venv" / "bin" / "python"), RUNNER[agent]],
                   cwd=str(WS), env=env, capture_output=True, text=True)
    return WS / "results" / "authz" / "runs" / run_id / f"{agent}.cases.json"


def _heldout_fidelity(cases_path: Path, truth: dict) -> float:
    if not cases_path.exists():
        return 0.0
    doc = json.loads(cases_path.read_text())
    obs = {}
    for c in doc.get("cases", []):
        st = c.get("sub_test")
        if st in truth and c.get("actual_class") not in (None, "none"):
            obs[st] = (c.get("expected_code"), c.get("actual_class"),
                       bool(c.get("data_exposed")), bool(c.get("leak_safe")))
    denom = len(truth)
    if not denom:
        return 0.0
    matches = sum(1 for k, g in truth.items() if obs.get(k) == g)
    return round(100.0 * matches / denom, 2)


def skillopt_for_agent(agent: str, sub_tests: list[str], truth: dict) -> dict:
    base_doc = (WS / "evolvers" / "skillopt_authz" / agent / "best_skill.md").read_text()
    staged = WS / "evolvers" / "skillopt_authz" / agent / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    cand_path = staged / "candidate_skill.md"
    cand_path.write_text(_candidate_skill(base_doc))

    base_fid = _heldout_fidelity(_run_agent_heldout(agent, None, f"evolve-authz-{agent}-base"), truth)
    cand_fid = _heldout_fidelity(_run_agent_heldout(agent, cand_path, f"evolve-authz-{agent}-cand"), truth)
    accepted = cand_fid > base_fid

    decision = {"agent": agent, "ts": datetime.now(timezone.utc).isoformat(),
                "metric": "authorization_test_fidelity_heldout",
                "held_out_sub_tests": sub_tests,
                "baseline_fidelity": base_fid, "candidate_fidelity": cand_fid,
                "accepted": accepted, "candidate_skill_path": str(cand_path),
                "note": ("STRICT-improvement gate. ACCEPTED candidate is STAGED only — "
                         "best_skill.md is NOT overwritten. Adopt manually after review.")}
    (staged / "decision.json").write_text(json.dumps(decision, indent=2))
    return decision


def skillclaw_share() -> dict:
    pool = WS / "evolvers" / "skillclaw_authz" / "shared" / "SKILL.md"
    manifest = {"shared_skill": str(pool), "ts": datetime.now(timezone.utc).isoformat(),
                "offered_to": AGENTS, "backend": "local_filesystem", "air_gapped": True,
                "note": "Shared skill available to all agents; adoption is the user's call."}
    (WS / "evolvers" / "skillclaw_authz" / "share_manifest.json").write_text(json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    sub_tests = _held_out_sub_tests()
    truth = _gold_truth(set(sub_tests))

    print(f"Self-evolution (staged) · held-out sub_tests = {sub_tests} · {len(truth)} gold cases")
    print("SkillOpt — per-agent, gated on held-out fidelity (strict improvement):\n")
    decisions = [skillopt_for_agent(ag, sub_tests, truth) for ag in agents]
    print(f"{'agent':40} {'baseline':>9} {'candidate':>10} {'decision':>10}")
    for d in decisions:
        verdict = "ACCEPT*" if d["accepted"] else "reject"
        print(f"{d['agent']:40} {d['baseline_fidelity']:>9} {d['candidate_fidelity']:>10} {verdict:>10}")
    man = skillclaw_share()
    print(f"\nSkillClaw — shared skill offered to {len(man['offered_to'])} agents "
          f"(local, air-gapped): {man['shared_skill']}")
    print("\n* ACCEPTED proposals are STAGED under evolvers/skillopt_authz/<agent>/staged/.")
    print("  Nothing was adopted. Review decision.json + candidate_skill.md, then adopt manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
