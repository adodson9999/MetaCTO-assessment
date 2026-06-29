#!/usr/bin/env python3
"""Self-evolution loop (SkillOpt + SkillClaw) for the api-tester / test-timeout-handling
workflow. Staged — never auto-adopts.

The manual `/evolve` trigger and the body the nightly sleep cycle runs for THIS
workflow, wired to the central backend and the judge metric (Timeout-Test Fidelity).

  SkillOpt (per-agent, vertical):
    For each agent, propose a bounded edit to its skill document, evaluate the
    candidate on the HELD-OUT services (results/test-timeout-handling/held_out.jsonl)
    using the judge metric, and ACCEPT only on STRICT improvement of held-out fidelity.
    Accept or reject, the proposal + decision is STAGED under
    evolvers/skillopt/test-timeout-handling/<agent>/staged/. best_skill.md is never
    overwritten here.

  SkillClaw (collective, horizontal):
    The shared pool (evolvers/skillclaw/timeout-shared/SKILL.md, local filesystem,
    air-gapped) is offered to all agents. This records the share manifest; adoption
    stays the user's call.

Agents elicit on the Claude Code account via the `claude` CLI; the gateway is the
only network target and is local.

Usage:
    python evolvers/evolve_timeout.py [--agents langgraph,crewai,...] [--dry-run]
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
AGENTS = ["langgraph", "crewai", "claude_sdk", "api-tester-test-timeout-handling"]
BASE = "agents/api-tester-test-timeout-handling"
AGENT_DIR = {
    "langgraph": f"{BASE}/langgraph/run.py",
    "crewai": f"{BASE}/crewai/run.py",
    "claude_sdk": f"{BASE}/claude_sdk/run.py",
    "api-tester-test-timeout-handling": f"{BASE}/subagent/run.py",
}


def _held_out_services() -> list[str]:
    out = []
    p = WS / "results" / "test-timeout-handling" / "held_out.jsonl"
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line)["service"])
    return out


def _gold_truth(services: set[str]) -> dict:
    gold = json.loads((WS / "data" / "test-timeout-handling" / "gold.json").read_text())
    truth = {}
    for svc in gold.get("services", []):
        if svc["service"] in services:
            for s in svc["scenarios"]:
                truth[(svc["service"], s["scenario"])] = s["observed_token"]
    return truth


def _candidate_skill(base_doc: str) -> str:
    """Bounded add edit distilled from the SkillClaw shared pool: reinforce the
    max_wait arithmetic + full both-phase endpoint coverage, addressing the plausible
    failure where a model forgets the buffer, drops the restore phase, or rewrites a
    method/path."""
    addition = ("Always set max_wait_s to exactly upstream_timeout_s plus buffer_s, and always "
                "list every endpoint from the brief once in BOTH the delayed and the restore "
                "array with its method and path copied verbatim (method uppercased) and label "
                '"METHOD path" — never drop the restore phase, never omit or rewrite an endpoint, '
                "and emit one parseable JSON object per service.")
    return base_doc.rstrip() + "\n" + addition + "\n"


def _run_agent_on_heldout(agent: str, skill_doc: Path | None, run_id: str,
                          services: list[str]) -> Path:
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(WS)
    env["FORGE_SANDBOX_ROOT"] = str(WS)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_TARGET_BASE_URL"] = os.environ.get("FORGE_TARGET_BASE_URL", "http://127.0.0.1:8911")
    env["FORGE_ONLY_SERVICES"] = ",".join(services)
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
    for svc in doc.get("services", []):
        for s in svc.get("scenarios", []):
            obs[(svc["service"], s["scenario"])] = s.get("observed_token")
    denom = len(truth)
    if not denom:
        return 0.0
    matches = sum(1 for k, g in truth.items()
                  if obs.get(k) == g and obs.get(k) not in (None, "missing"))
    return round(100.0 * matches / denom, 2)


def skillopt_for_agent(agent: str, services: list[str], truth: dict) -> dict:
    base = WS / "evolvers" / "skillopt" / "test-timeout-handling" / agent / "best_skill.md"
    staged = WS / "evolvers" / "skillopt" / "test-timeout-handling" / agent / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    cand_path = staged / "candidate_skill.md"
    cand_path.write_text(_candidate_skill(base.read_text()))

    base_cases = _run_agent_on_heldout(agent, None, f"evolve-tmo-{agent}-base", services)
    base_fid = _heldout_fidelity(base_cases, truth)
    cand_cases = _run_agent_on_heldout(agent, cand_path, f"evolve-tmo-{agent}-cand", services)
    cand_fid = _heldout_fidelity(cand_cases, truth)

    accepted = cand_fid > base_fid
    decision = {"agent": agent, "ts": datetime.now(timezone.utc).isoformat(),
                "metric": "timeout_test_fidelity_heldout", "held_out_services": services,
                "baseline_fidelity": base_fid, "candidate_fidelity": cand_fid,
                "accepted": accepted, "candidate_skill_path": str(cand_path),
                "note": ("STRICT-improvement gate. ACCEPTED candidate is STAGED only — "
                         "best_skill.md is NOT overwritten. Adopt manually after review.")}
    (staged / "decision.json").write_text(json.dumps(decision, indent=2))
    return decision


def skillclaw_share() -> dict:
    pool = WS / "evolvers" / "skillclaw" / "timeout-shared" / "SKILL.md"
    manifest = {"shared_skill": str(pool), "ts": datetime.now(timezone.utc).isoformat(),
                "offered_to": AGENTS, "backend": "local_filesystem", "air_gapped": True,
                "note": "Shared skill available to all agents; adoption is the user's call."}
    (WS / "evolvers" / "skillclaw" / "timeout_share_manifest.json").write_text(
        json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]
    services = _held_out_services()
    truth = _gold_truth(set(services))

    print(f"Self-evolution (staged) · held-out = {services} · {len(truth)} gold scenarios")
    if a.dry_run:
        print("[dry-run] would run SkillOpt held-out gate + SkillClaw share; no agent calls made.")
        skillclaw_share()
        return 0
    print("SkillOpt — per-agent, gated on held-out fidelity (strict improvement):\n")
    decisions = [skillopt_for_agent(ag, services, truth) for ag in agents]
    print(f"{'agent':40} {'baseline':>9} {'candidate':>10} {'decision':>10}")
    for d in decisions:
        verdict = "ACCEPT*" if d["accepted"] else "reject"
        print(f"{d['agent']:40} {d['baseline_fidelity']:>9} {d['candidate_fidelity']:>10} {verdict:>10}")
    man = skillclaw_share()
    print(f"\nSkillClaw — shared skill offered to {len(man['offered_to'])} agents "
          f"(local, air-gapped): {man['shared_skill']}")
    print("\n* ACCEPTED proposals are STAGED under evolvers/skillopt/test-timeout-handling/<agent>/staged/.")
    print("  Nothing was adopted. Review decision.json + candidate_skill.md, then adopt manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
