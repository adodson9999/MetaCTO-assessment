#!/usr/bin/env python3
"""Self-evolution loop for the validate-json-schema-responses task (SkillOpt +
SkillClaw), staged — never auto-adopts. The `/evolve` body for this task and the
nightly sleep cycle's schema-task pass.

  SkillOpt (per-agent, vertical):
    For each schema agent, propose a bounded edit to its skill document, evaluate
    the candidate on the HELD-OUT endpoints (results/schema/held_out.jsonl) with
    the judge metric (Response-Validation Fidelity), and ACCEPT only if it STRICTLY
    improves held-out fidelity. Accept or reject, the proposal + decision is STAGED
    under evolvers/skillopt/schema/<agent>/staged/. best_skill.md is never
    overwritten here.

  SkillClaw (collective, horizontal):
    The shared pool (evolvers/skillclaw/schema/shared/SKILL.md, local FS,
    air-gapped) is offered to all agents; adoption stays the user's call.

Gate metric = judge/schema/metric.json (the same number that ranks the agents).
Held-out split = results/schema/held_out.jsonl (disjoint role from ranking).

Usage:
    python evolvers/evolve_schema.py [--agents langgraph,crewai,...] [--dry-run]
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
AGENTS = ["langgraph", "crewai", "claude_sdk", "api-tester-validate-json-schema-responses"]


def _held_out_slugs() -> list[str]:
    out = []
    for line in (WS / "results" / "schema" / "held_out.jsonl").read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line)["slug"])
    return out


def _gold_truth(slugs: set[str]) -> dict:
    gold = json.loads((WS / "data" / "schema" / "gold.json").read_text())
    truth = {}
    for ep in gold["endpoints"]:
        if ep["slug"] in slugs:
            truth[ep["slug"]] = {
                "actual_class": ep["actual_class"],
                "documented_schema": ep["documented_schema"],
                "conformance": ep["conformance"],
                "validation_error_count": ep["validation_error_count"],
            }
    return truth


def _matches(gold: dict, obs: dict | None) -> bool:
    if obs is None:
        return False
    return (obs.get("actual_class") == gold["actual_class"]
            and obs.get("documented_schema") == gold["documented_schema"]
            and obs.get("conformance") == gold["conformance"]
            and obs.get("validation_error_count") == gold["validation_error_count"]
            and bool(obs.get("schema_claim_correct")))


def _candidate_skill(base_doc: str) -> str:
    """Bounded add edit: reinforce honest gap-reporting (the dominant fidelity
    lever on this task) — never hallucinate a response schema."""
    addition = ('For every documented response status key you must copy '
                'has_json_schema verbatim from the endpoint description; when the '
                'description states has_json_schema=false you must output false and '
                'never true, and you must never assert that a response schema exists '
                'when the description does not say so.')
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
    subprocess.run([str(WS / ".venv" / "bin" / "python"),
                    f"agents/schema/{agent}/run.py"],
                   cwd=str(WS), env=env, capture_output=True, text=True)
    return WS / "results" / "schema" / "runs" / run_id / f"{agent}.cases.json"


def _heldout_fidelity(cases_path: Path, truth: dict) -> float:
    if not cases_path.exists():
        return 0.0
    doc = json.loads(cases_path.read_text())
    obs = {c["slug"]: c for c in doc.get("cases", []) if c.get("covered")}
    denom = len(truth)
    if not denom:
        return 0.0
    matches = sum(1 for slug, g in truth.items() if _matches(g, obs.get(slug)))
    return round(100.0 * matches / denom, 2)


def skillopt_for_agent(agent: str, slugs: list[str], truth: dict, dry: bool) -> dict:
    base_doc = (WS / "evolvers" / "skillopt" / "schema" / agent / "best_skill.md").read_text()
    staged = WS / "evolvers" / "skillopt" / "schema" / agent / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    cand_path = staged / "candidate_skill.md"
    cand_path.write_text(_candidate_skill(base_doc))

    base_cases = _run_agent_on_heldout(agent, None, f"evolve-schema-{agent}-base", slugs)
    base_fid = _heldout_fidelity(base_cases, truth)
    cand_cases = _run_agent_on_heldout(agent, cand_path, f"evolve-schema-{agent}-cand", slugs)
    cand_fid = _heldout_fidelity(cand_cases, truth)

    accepted = cand_fid > base_fid  # STRICT improvement on held-out
    decision = {
        "agent": agent, "ts": datetime.now(timezone.utc).isoformat(),
        "task": "validate-json-schema-responses",
        "metric": "response_validation_fidelity_heldout",
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
    pool = WS / "evolvers" / "skillclaw" / "schema" / "shared" / "SKILL.md"
    manifest = {"task": "validate-json-schema-responses", "shared_skill": str(pool),
                "ts": datetime.now(timezone.utc).isoformat(), "offered_to": AGENTS,
                "backend": "local_filesystem", "air_gapped": True,
                "note": "Shared skill available to all schema agents; adoption is the user's call."}
    (WS / "evolvers" / "skillclaw" / "schema" / "share_manifest.json").write_text(
        json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    slugs = _held_out_slugs()
    truth = _gold_truth(set(slugs))

    print(f"Self-evolution (staged) · held-out = {slugs} · {len(truth)} gold endpoints")
    print("SkillOpt — per-agent, gated on held-out fidelity (strict improvement):\n")
    decisions = [skillopt_for_agent(ag, slugs, truth, a.dry_run) for ag in agents]
    print(f"{'agent':42} {'baseline':>9} {'candidate':>10} {'decision':>10}")
    for d in decisions:
        verdict = "ACCEPT*" if d["accepted"] else "reject"
        print(f"{d['agent']:42} {d['baseline_fidelity']:>9} {d['candidate_fidelity']:>10} {verdict:>10}")
    man = skillclaw_share()
    print(f"\nSkillClaw — shared skill offered to {len(man['offered_to'])} agents "
          f"(local, air-gapped): {man['shared_skill']}")
    print("\n* ACCEPTED proposals are STAGED under evolvers/skillopt/schema/<agent>/staged/.")
    print("  Nothing was adopted. Review decision.json + candidate_skill.md, then adopt manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
