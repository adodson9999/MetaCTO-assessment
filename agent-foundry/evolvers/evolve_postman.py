#!/usr/bin/env python3
"""Self-evolution loop (SkillOpt + SkillClaw) for the api-tester /
create-postman-collection ("n601") workflow. Staged — never auto-adopts.

The manual `/evolve` trigger and the body the nightly sleep cycle runs for THIS workflow,
wired to the central backend and the judge metric (Postman Contract Fidelity).

  SkillOpt (per-agent, vertical):
    For each agent, propose a bounded edit to its skill document, evaluate the candidate
    on a HELD-OUT registry (results/create-postman-collection/held_out.jsonl — a different
    agent/case mix the skill was NOT tuned on) using the judge metric, and ACCEPT only on
    STRICT improvement of held-out fidelity. Accept or reject, the proposal + decision is
    STAGED under evolvers/skillopt/create-postman-collection/<agent>/staged/.
    best_skill.md is never overwritten here.

  SkillClaw (collective, horizontal):
    The shared pool (evolvers/skillclaw/postman-shared/SKILL.md, local filesystem,
    air-gapped) is offered to all agents. This records the share manifest; adoption stays
    the user's call.

n601 is a pure JSON->JSON transform: no server, no HTTP target, DummyJSON never touched.

Usage:
    python evolvers/evolve_postman.py [--agents langgraph,crewai,...] [--dry-run]
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
AGENTS = ["langgraph", "crewai", "claude_sdk", "api-tester-create-postman-collection"]
BASE = "agents/api-tester-create-postman-collection"
AGENT_DIR = {
    "langgraph": f"{BASE}/langgraph/run.py",
    "crewai": f"{BASE}/crewai/run.py",
    "claude_sdk": f"{BASE}/claude_sdk/run.py",
    "api-tester-create-postman-collection": f"{BASE}/subagent/run.py",
}
WORKFLOW = "create-postman-collection"


def _held_out_variant() -> dict:
    p = WS / "results" / WORKFLOW / "held_out.jsonl"
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            return json.loads(line)
    return {}


def _heldout_env(variant: dict) -> dict:
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(WS)
    env["FORGE_SANDBOX_ROOT"] = str(WS)
    env["PATH"] = str(WS / ".venv" / "bin") + os.pathsep + env.get("PATH", "")
    if "registry_fixture" in variant:
        env["FORGE_HELDOUT_REGISTRY"] = variant["registry_fixture"]
    if "summary_fixture" in variant:
        env["FORGE_HELDOUT_SUMMARY"] = variant["summary_fixture"]
    return env


def _heldout_gold(variant: dict) -> dict:
    """Build the held-out gold IN-PROCESS via the shared building path, so the candidate is
    graded against truth for the exact held-out registry."""
    env = _heldout_env(variant)
    for k in ("FORGE_HELDOUT_REGISTRY", "FORGE_HELDOUT_SUMMARY"):
        if k in env:
            os.environ[k] = env[k]
    sys.path.insert(0, str(WS / "agents" / "common"))
    import importlib
    import postman  # noqa
    import postman_spec  # noqa
    importlib.reload(postman)
    cfg = postman.run_cfg()
    registry, summary = postman.load_registry(cfg)
    ref = postman_spec.reference_contract(cfg)
    coll = postman_spec.build_collection(
        postman_spec.filter_http(registry, ref), ref, "2026-06-26", "gold")
    observed = postman_spec.evaluate(coll, registry, summary, cfg)
    return {lbl: observed.get(lbl, "missing") for lbl in postman_spec.SCENARIO_LABELS}


def _candidate_skill(base_doc: str) -> str:
    """Bounded add edit distilled from the SkillClaw shared pool: reinforce the
    thirteen-key contract, the verbatim-regex rule, and the no-action reading."""
    addition = ("Always emit exactly the thirteen contract keys; copy every regex and "
                "trigger substring character-for-character (backslashes, braces, and the "
                "→ arrow included) and never rewrite/escape/simplify/correct them; keep "
                "the five header_triggers and five variables complete and in order; and "
                "never read the registry, build the collection, run Newman, or report any "
                "count — the harness does all of that.")
    return base_doc.rstrip() + "\n" + addition + "\n"


def _run_agent_heldout(agent: str, skill_doc: Path | None, run_id: str, variant: dict) -> Path:
    env = _heldout_env(variant)
    env["FORGE_RUN_ID"] = run_id
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
    obs = {s["scenario"]: s.get("observed_token") for s in doc.get("scenarios", [])}
    denom = len(truth)
    if not denom:
        return 0.0
    matches = sum(1 for k, g in truth.items()
                  if obs.get(k) == g and obs.get(k) not in (None, "missing"))
    return round(100.0 * matches / denom, 2)


def skillopt_for_agent(agent: str, variant: dict, truth: dict) -> dict:
    base = WS / "evolvers" / "skillopt" / WORKFLOW / agent / "best_skill.md"
    staged = WS / "evolvers" / "skillopt" / WORKFLOW / agent / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    cand_path = staged / "candidate_skill.md"
    cand_path.write_text(_candidate_skill(base.read_text()))

    base_cases = _run_agent_heldout(agent, None, f"evolve-pm-{agent}-base", variant)
    base_fid = _heldout_fidelity(base_cases, truth)
    cand_cases = _run_agent_heldout(agent, cand_path, f"evolve-pm-{agent}-cand", variant)
    cand_fid = _heldout_fidelity(cand_cases, truth)

    accepted = cand_fid > base_fid
    decision = {"agent": agent, "ts": datetime.now(timezone.utc).isoformat(),
                "metric": "postman_contract_fidelity_heldout", "held_out_variant": variant,
                "baseline_fidelity": base_fid, "candidate_fidelity": cand_fid,
                "accepted": accepted, "candidate_skill_path": str(cand_path),
                "note": ("STRICT-improvement gate. ACCEPTED candidate is STAGED only — "
                         "best_skill.md is NOT overwritten. Adopt manually after review.")}
    (staged / "decision.json").write_text(json.dumps(decision, indent=2))
    return decision


def skillclaw_share() -> dict:
    pool = WS / "evolvers" / "skillclaw" / "postman-shared" / "SKILL.md"
    manifest = {"shared_skill": str(pool), "ts": datetime.now(timezone.utc).isoformat(),
                "offered_to": AGENTS, "backend": "local_filesystem", "air_gapped": True,
                "note": "Shared skill available to all agents; adoption is the user's call."}
    (WS / "evolvers" / "skillclaw" / "postman_share_manifest.json").write_text(
        json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    variant = _held_out_variant()

    print(f"Self-evolution (staged) · held-out variant = {variant}")
    if a.dry_run:
        print("[dry-run] would build held-out gold + run SkillOpt gate + SkillClaw share; "
              "no agent calls made.")
        skillclaw_share()
        return 0

    truth = _heldout_gold(variant)
    print(f"held-out gold tokens: {truth}\n")
    print("SkillOpt — per-agent, gated on held-out fidelity (strict improvement):\n")
    decisions = [skillopt_for_agent(ag, variant, truth) for ag in agents]
    print(f"{'agent':44} {'baseline':>9} {'candidate':>10} {'decision':>10}")
    for d in decisions:
        verdict = "ACCEPT*" if d["accepted"] else "reject"
        print(f"{d['agent']:44} {d['baseline_fidelity']:>9} {d['candidate_fidelity']:>10} {verdict:>10}")
    man = skillclaw_share()
    print(f"\nSkillClaw — shared skill offered to {len(man['offered_to'])} agents "
          f"(local, air-gapped): {man['shared_skill']}")
    print("\n* ACCEPTED proposals are STAGED under "
          "evolvers/skillopt/create-postman-collection/<agent>/staged/.")
    print("  Nothing was adopted. Review decision.json + candidate_skill.md, then adopt manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
