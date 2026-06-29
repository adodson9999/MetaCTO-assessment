#!/usr/bin/env python3
"""Self-evolution loop (SkillOpt + SkillClaw) for the api-tester / track-defect-density
workflow. Staged — never auto-adopts.

The manual `/evolve` trigger and the body the nightly sleep cycle runs for THIS
workflow, wired to the central backend and the judge metric (Defect-Density Report
Accuracy).

  SkillOpt (per-agent, vertical):
    For each agent, propose a bounded edit to its skill document, evaluate the
    candidate on the HELD-OUT sprints (results/track-defect-density/held_out.jsonl)
    using the judge metric, and ACCEPT only on STRICT improvement of held-out
    accuracy. Accept or reject, the proposal + decision is STAGED under
    evolvers/skillopt/track-defect-density/<agent>/staged/. best_skill.md is never
    overwritten here.

  SkillClaw (collective, horizontal):
    The shared pool (evolvers/skillclaw/defectdensity-shared/SKILL.md, local
    filesystem, air-gapped) is offered to all agents. This records the share
    manifest; adoption stays the user's call.

Fully air-gapped on the data side (local fixtures; no Jira/Git/network target).

Usage:
    python evolvers/evolve_defectdensity.py [--agents langgraph,crewai,...] [--dry-run]
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
AGENTS = ["langgraph", "crewai", "claude_sdk", "api-tester-track-defect-density"]
BASE = "agents/api-tester-track-defect-density"
AGENT_DIR = {
    "langgraph": f"{BASE}/langgraph/run.py",
    "crewai": f"{BASE}/crewai/run.py",
    "claude_sdk": f"{BASE}/claude_sdk/run.py",
    "api-tester-track-defect-density": f"{BASE}/subagent/run.py",
}

sys.path.insert(0, str(WS / "agents" / "common"))
import defectdensity_spec as ddspec  # noqa: E402


def _held_out_sprints() -> list[str]:
    out = []
    p = WS / "results" / "track-defect-density" / "held_out.jsonl"
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line)["sprint_name"])
    return out


def _gold_records(sprints: set[str]) -> dict:
    gold = json.loads((WS / "data" / "track-defect-density" / "gold.json").read_text())
    return {s["sprint_name"]: s["record"] for s in gold["sprints"] if s["sprint_name"] in sprints}


def _candidate_skill(base_doc: str) -> str:
    """Bounded add edit distilled from the SkillClaw shared pool: reinforce the four
    most plausible misses — loose priority mapping, dropping a *test.go/*test.py/
    *.spec.ts line incorrectly, the >20 (not >=20) alert boundary, and the trend
    sign/one-decimal format."""
    addition = ("Count P1-P4 by EXACT priority string (Highest/High/Medium/Low only). "
                "Before summing changed lines, exclude every file whose path ends with "
                "test.go, test.py, or .spec.ts, and sum insertions+deletions of the rest. "
                "Round half up to the stated decimals. alert_flag is true ONLY when "
                "deviation_pct is strictly greater than 20 (exactly 20.00 -> false). Format "
                "trend as a sign then the absolute percent with exactly one decimal then '%'. "
                "Emit one parseable JSON object with exactly the ten keys and nothing else.")
    return base_doc.rstrip() + "\n" + addition + "\n"


def _run_agent_on_heldout(agent: str, skill_doc: Path | None, run_id: str,
                          sprints: list[str]) -> Path:
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(WS)
    env["FORGE_SANDBOX_ROOT"] = str(WS)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_ONLY_SPRINTS"] = ",".join(sprints)
    env["PATH"] = str(WS / ".venv" / "bin") + os.pathsep + env.get("PATH", "")
    if skill_doc is not None:
        env["FORGE_SKILL_DOC"] = str(skill_doc)
    else:
        env.pop("FORGE_SKILL_DOC", None)
    subprocess.run([str(WS / ".venv" / "bin" / "python"), AGENT_DIR[agent]],
                   cwd=str(WS), env=env, capture_output=True, text=True)
    return WS / "results" / "runs" / run_id / f"{agent}.cases.json"


def _heldout_accuracy(cases_path: Path, gold: dict) -> float:
    if not cases_path.exists():
        return 0.0
    doc = json.loads(cases_path.read_text())
    denom = len(gold) * len(ddspec.FIELDS)
    if not denom:
        return 0.0
    matches = 0
    for sp in doc.get("sprints", []):
        rec = gold.get(sp["sprint"])
        if not rec:
            continue
        checks = ddspec.evaluate(sp.get("emitted_report", {}), rec)
        matches += sum(1 for ok in checks.values() if ok)
    return round(100.0 * matches / denom, 2)


def skillopt_for_agent(agent: str, sprints: list[str], gold: dict) -> dict:
    base = WS / "evolvers" / "skillopt" / "track-defect-density" / agent / "best_skill.md"
    staged = WS / "evolvers" / "skillopt" / "track-defect-density" / agent / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    cand_path = staged / "candidate_skill.md"
    cand_path.write_text(_candidate_skill(base.read_text()))

    base_cases = _run_agent_on_heldout(agent, None, f"evolve-dd-{agent}-base", sprints)
    base_acc = _heldout_accuracy(base_cases, gold)
    cand_cases = _run_agent_on_heldout(agent, cand_path, f"evolve-dd-{agent}-cand", sprints)
    cand_acc = _heldout_accuracy(cand_cases, gold)

    accepted = cand_acc > base_acc
    decision = {"agent": agent, "ts": datetime.now(timezone.utc).isoformat(),
                "metric": "defect_density_report_accuracy_heldout", "held_out_sprints": sprints,
                "baseline_accuracy": base_acc, "candidate_accuracy": cand_acc,
                "accepted": accepted, "candidate_skill_path": str(cand_path),
                "note": ("STRICT-improvement gate. ACCEPTED candidate is STAGED only — "
                         "best_skill.md is NOT overwritten. Adopt manually after review.")}
    (staged / "decision.json").write_text(json.dumps(decision, indent=2))
    return decision


def skillclaw_share() -> dict:
    pool = WS / "evolvers" / "skillclaw" / "defectdensity-shared" / "SKILL.md"
    manifest = {"shared_skill": str(pool), "ts": datetime.now(timezone.utc).isoformat(),
                "offered_to": AGENTS, "backend": "local_filesystem", "air_gapped": True,
                "note": "Shared skill available to all agents; adoption is the user's call."}
    (WS / "evolvers" / "skillclaw" / "defectdensity_share_manifest.json").write_text(
        json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    sprints = _held_out_sprints()
    gold = _gold_records(set(sprints))

    print(f"Self-evolution (staged) · held-out = {sprints} · {len(gold) * len(ddspec.FIELDS)} gold cells")
    if a.dry_run:
        print("[dry-run] would run SkillOpt held-out gate + SkillClaw share; no agent calls made.")
        skillclaw_share()
        return 0
    print("SkillOpt — per-agent, gated on held-out accuracy (strict improvement):\n")
    decisions = [skillopt_for_agent(ag, sprints, gold) for ag in agents]
    print(f"{'agent':40} {'baseline':>9} {'candidate':>10} {'decision':>10}")
    for d in decisions:
        verdict = "ACCEPT*" if d["accepted"] else "reject"
        print(f"{d['agent']:40} {d['baseline_accuracy']:>9} {d['candidate_accuracy']:>10} {verdict:>10}")
    man = skillclaw_share()
    print(f"\nSkillClaw — shared skill offered to {len(man['offered_to'])} agents "
          f"(local, air-gapped): {man['shared_skill']}")
    print("\n* ACCEPTED proposals are STAGED under evolvers/skillopt/track-defect-density/<agent>/staged/.")
    print("  Nothing was adopted. Review decision.json + candidate_skill.md, then adopt manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
