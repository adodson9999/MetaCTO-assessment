#!/usr/bin/env python3
"""Self-evolution loop (SkillOpt + SkillClaw) for the api-tester /
test-soft-delete-behavior workflow. Staged — never auto-adopts.

The manual `/evolve` trigger and the body the nightly sleep cycle runs for THIS
workflow, wired to the central backend and the judge metric (Soft-Delete-Test Fidelity).

  SkillOpt (per-agent, vertical):
    For each agent, propose a bounded edit to its skill document, evaluate the candidate
    on a HELD-OUT VARIANT config (results/test-soft-delete-behavior/held_out.jsonl — a
    case_count/tolerance combination the skill was NOT tuned on) using the judge metric,
    and ACCEPT only on STRICT improvement of held-out fidelity. Accept or reject, the
    proposal + decision is STAGED under
    evolvers/skillopt/test-soft-delete-behavior/<agent>/staged/. best_skill.md is never
    overwritten here.

  SkillClaw (collective, horizontal):
    The shared pool (evolvers/skillclaw/softdelete-shared/SKILL.md, local filesystem,
    air-gapped) is offered to all agents. This records the share manifest; adoption stays
    the user's call.

The local soft-delete target must be up (the phase4 script starts it). DummyJSON is not
used and not modified.

Usage:
    python evolvers/evolve_softdelete.py [--agents langgraph,crewai,...] [--dry-run]
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
AGENTS = ["langgraph", "crewai", "claude_sdk", "api-tester-test-soft-delete-behavior"]
BASE = "agents/api-tester-test-soft-delete-behavior"
AGENT_DIR = {
    "langgraph": f"{BASE}/langgraph/run.py",
    "crewai": f"{BASE}/crewai/run.py",
    "claude_sdk": f"{BASE}/claude_sdk/run.py",
    "api-tester-test-soft-delete-behavior": f"{BASE}/subagent/run.py",
}


def _held_out_variant() -> dict:
    p = WS / "results" / "test-soft-delete-behavior" / "held_out.jsonl"
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
    env.setdefault("FORGE_BASE_URL", os.environ.get("FORGE_BASE_URL", "http://127.0.0.1:8950"))
    if "case_count" in variant:
        env["FORGE_HELDOUT_CASE_COUNT"] = str(variant["case_count"])
    if "resource_endpoint" in variant:
        env["FORGE_HELDOUT_RESOURCE_ENDPOINT"] = variant["resource_endpoint"]
    if "deleted_at_tolerance_s" in variant:
        env["FORGE_HELDOUT_TOLERANCE_S"] = str(variant["deleted_at_tolerance_s"])
    return env


def _heldout_gold(variant: dict) -> dict:
    """Build the held-out gold IN-PROCESS via the shared execution path, so the
    candidate is graded against truth for the exact variant config."""
    env = _heldout_env(variant)
    for k in ("FORGE_HELDOUT_CASE_COUNT", "FORGE_HELDOUT_RESOURCE_ENDPOINT",
              "FORGE_HELDOUT_TOLERANCE_S", "FORGE_BASE_URL"):
        if k in env:
            os.environ[k] = env[k]
    os.environ["FORGE_RUN_ID"] = "evolve-sd-gold"
    sys.path.insert(0, str(WS / "agents" / "common"))
    import importlib
    import softdelete  # noqa
    import softdelete_spec  # noqa
    importlib.reload(softdelete)
    cfg = softdelete.run_cfg()
    case_count = cfg.get("case_count", softdelete_spec.CASE_COUNT)
    plan = softdelete_spec.build_reference_plan(cfg)
    case_results, _ = softdelete._exec_plan("gold", cfg, plan)
    observed = softdelete_spec.evaluate(case_results, case_count)
    return {lbl: observed.get(lbl, "missing") for lbl in softdelete_spec.SCENARIO_LABELS}


def _candidate_skill(base_doc: str) -> str:
    """Bounded add edit distilled from the SkillClaw shared pool: reinforce the
    {RESOURCE_ID}-verbatim rule, the exact per-descriptor key counts, and the
    no-DB-mutation reading of the db_query assertions."""
    addition = ("Always keep {RESOURCE_ID} a literal token inside each path_template "
                "(never substitute an id), always emit all seven top-level keys with "
                "create=3 / delete=3 / get_deleted=4 / collection=4 / db_query=8 / "
                "include_deleted=5 keys, treat every db_query assert_* key as an inert "
                "read expectation (never a DB mutation), and write every numeric field "
                "as a bare JSON number.")
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
    base = WS / "evolvers" / "skillopt" / "test-soft-delete-behavior" / agent / "best_skill.md"
    staged = WS / "evolvers" / "skillopt" / "test-soft-delete-behavior" / agent / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    cand_path = staged / "candidate_skill.md"
    cand_path.write_text(_candidate_skill(base.read_text()))

    base_cases = _run_agent_heldout(agent, None, f"evolve-sd-{agent}-base", variant)
    base_fid = _heldout_fidelity(base_cases, truth)
    cand_cases = _run_agent_heldout(agent, cand_path, f"evolve-sd-{agent}-cand", variant)
    cand_fid = _heldout_fidelity(cand_cases, truth)

    accepted = cand_fid > base_fid
    decision = {"agent": agent, "ts": datetime.now(timezone.utc).isoformat(),
                "metric": "soft_delete_test_fidelity_heldout", "held_out_variant": variant,
                "baseline_fidelity": base_fid, "candidate_fidelity": cand_fid,
                "accepted": accepted, "candidate_skill_path": str(cand_path),
                "note": ("STRICT-improvement gate. ACCEPTED candidate is STAGED only — "
                         "best_skill.md is NOT overwritten. Adopt manually after review.")}
    (staged / "decision.json").write_text(json.dumps(decision, indent=2))
    return decision


def skillclaw_share() -> dict:
    pool = WS / "evolvers" / "skillclaw" / "softdelete-shared" / "SKILL.md"
    manifest = {"shared_skill": str(pool), "ts": datetime.now(timezone.utc).isoformat(),
                "offered_to": AGENTS, "backend": "local_filesystem", "air_gapped": True,
                "note": "Shared skill available to all agents; adoption is the user's call."}
    (WS / "evolvers" / "skillclaw" / "softdelete_share_manifest.json").write_text(
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
          "evolvers/skillopt/test-soft-delete-behavior/<agent>/staged/.")
    print("  Nothing was adopted. Review decision.json + candidate_skill.md, then adopt manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
