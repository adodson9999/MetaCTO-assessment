#!/usr/bin/env python3
"""Self-evolution loop (SkillOpt + SkillClaw) for the
api-tester / measure-api-consumer-satisfaction workflow. Staged — never auto-adopts.

The manual `/evolve` trigger and the body the nightly sleep cycle runs for THIS workflow,
wired to the central backend and the judge metric (NPS-Measurement Plan Fidelity).

  SkillOpt (per-agent, vertical):
    For each agent, propose a bounded edit to its skill document, evaluate the candidate
    on the HELD-OUT dataset (results/measure-api-consumer-satisfaction/held_out.jsonl ->
    "q_prev") using the judge metric, and ACCEPT only on STRICT improvement of held-out
    fidelity. Accept or reject, the proposal + decision is STAGED under
    evolvers/skillopt/measure-api-consumer-satisfaction/<agent>/staged/. best_skill.md is
    never overwritten here.

  SkillClaw (collective, horizontal):
    The shared pool (evolvers/skillclaw/nps-shared/SKILL.md, local filesystem, air-gapped)
    is offered to all agents. This records the share manifest; adoption stays the user's call.

The held-out axis is the DATASET (a different quarter), so an edit cannot overfit the
ranking quarter's numbers. The fixture is a local seeded SQLite DB; DummyJSON is never used.

Usage:
    python evolvers/evolve_nps.py [--agents langgraph,crewai,...] [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
WF = "measure-api-consumer-satisfaction"
AGENTS = ["langgraph", "crewai", "claude_sdk", "api-tester-measure-api-consumer-satisfaction"]
BASE = f"agents/api-tester-{WF}"
AGENT_DIR = {
    "langgraph": f"{BASE}/langgraph/run.py",
    "crewai": f"{BASE}/crewai/run.py",
    "claude_sdk": f"{BASE}/claude_sdk/run.py",
    "api-tester-measure-api-consumer-satisfaction": f"{BASE}/subagent/run.py",
}


def _held_out_dataset() -> str:
    p = WS / "results" / WF / "held_out.jsonl"
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            return json.loads(line)["dataset"]
    return "q_prev"


def _gold_truth(dataset: str) -> dict:
    gold = json.loads((WS / "data" / WF / "gold.json").read_text())
    for ds in gold.get("datasets", []):
        if ds.get("dataset") == dataset:
            return {s["scenario"]: s["observed_token"] for s in ds["scenarios"]}
    return {}


def _candidate_skill(base_doc: str) -> str:
    """Bounded add edit distilled from the SkillClaw shared pool: reinforce the eight
    plan keys, the verbatim integers and survey questions, the standard NPS bands and
    integer formula, the clustering config, and the no-execution clause — addressing the
    plausible failures where a model drifts a window, rebands the scores, swaps the
    rounding, shrinks k, or starts reporting numbers itself."""
    addition = ("Always emit exactly the eight plan keys and never any other; keep the integers "
                "verbatim (recipient window 90, collection window 14 with close on Day 15, validity "
                "threshold 30); copy the four survey questions character-for-character in order with "
                "ids nps/painpoint/improvement/other; keep the NPS bands promoter [9,10], passive "
                "[7,8], detractor [0,6]; keep nps_formula exactly \"round(promoter_pct - "
                "detractor_pct)\" (over respondents, nearest integer, halves up); keep clustering "
                "exactly {kmeans, tfidf, k=10, select_top=3, max_label_words=5}; emit the ten "
                "dashboard fields in order; and never query, send, collect, cluster, or report any "
                "number — the harness executes the plan and records the real figures.")
    return base_doc.rstrip() + "\n" + addition + "\n"


def _run_agent_on_heldout(agent: str, skill_doc: Path | None, run_id: str, dataset: str) -> Path:
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(WS)
    env["FORGE_SANDBOX_ROOT"] = str(WS)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_NPS_DATASET"] = dataset
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
    obs = {s["scenario"]: s.get("observed_token") for s in doc.get("scenarios", [])}
    denom = len(truth)
    if not denom:
        return 0.0
    matches = sum(1 for k, g in truth.items()
                  if obs.get(k) == g and obs.get(k) not in (None, "missing"))
    return round(100.0 * matches / denom, 2)


def skillopt_for_agent(agent: str, dataset: str, truth: dict) -> dict:
    base = WS / "evolvers" / "skillopt" / WF / agent / "best_skill.md"
    staged = WS / "evolvers" / "skillopt" / WF / agent / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    cand_path = staged / "candidate_skill.md"
    cand_path.write_text(_candidate_skill(base.read_text()))

    base_cases = _run_agent_on_heldout(agent, None, f"evolve-nps-{agent}-base", dataset)
    base_fid = _heldout_fidelity(base_cases, truth)
    cand_cases = _run_agent_on_heldout(agent, cand_path, f"evolve-nps-{agent}-cand", dataset)
    cand_fid = _heldout_fidelity(cand_cases, truth)

    accepted = cand_fid > base_fid
    decision = {"agent": agent, "ts": datetime.now(timezone.utc).isoformat(),
                "metric": "nps_measurement_plan_fidelity_heldout", "held_out_dataset": dataset,
                "baseline_fidelity": base_fid, "candidate_fidelity": cand_fid,
                "accepted": accepted, "candidate_skill_path": str(cand_path),
                "note": ("STRICT-improvement gate. ACCEPTED candidate is STAGED only — "
                         "best_skill.md is NOT overwritten. Adopt manually after review.")}
    (staged / "decision.json").write_text(json.dumps(decision, indent=2))
    return decision


def skillclaw_share() -> dict:
    pool = WS / "evolvers" / "skillclaw" / "nps-shared" / "SKILL.md"
    manifest = {"shared_skill": str(pool), "ts": datetime.now(timezone.utc).isoformat(),
                "offered_to": AGENTS, "backend": "local_filesystem", "air_gapped": True,
                "note": "Shared skill available to all agents; adoption is the user's call."}
    (WS / "evolvers" / "skillclaw" / "nps_share_manifest.json").write_text(
        json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    dataset = _held_out_dataset()
    truth = _gold_truth(dataset)

    print(f"Self-evolution (staged) · held-out dataset = {dataset} · {len(truth)} gold scenarios")
    if a.dry_run:
        print("[dry-run] would run SkillOpt held-out gate + SkillClaw share; no agent calls made.")
        skillclaw_share()
        return 0
    print("SkillOpt — per-agent, gated on held-out fidelity (strict improvement):\n")
    decisions = [skillopt_for_agent(ag, dataset, truth) for ag in agents]
    print(f"{'agent':50} {'baseline':>9} {'candidate':>10} {'decision':>10}")
    for d in decisions:
        verdict = "ACCEPT*" if d["accepted"] else "reject"
        print(f"{d['agent']:50} {d['baseline_fidelity']:>9} {d['candidate_fidelity']:>10} {verdict:>10}")
    man = skillclaw_share()
    print(f"\nSkillClaw — shared skill offered to {len(man['offered_to'])} agents "
          f"(local, air-gapped): {man['shared_skill']}")
    print(f"\n* ACCEPTED proposals are STAGED under evolvers/skillopt/{WF}/<agent>/staged/.")
    print("  Nothing was adopted. Review decision.json + candidate_skill.md, then adopt manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
