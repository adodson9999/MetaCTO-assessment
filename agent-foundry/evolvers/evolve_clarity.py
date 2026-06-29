#!/usr/bin/env python3
"""Self-evolution loop (SkillOpt + SkillClaw) for the verify-error-message-clarity
workflow. Staged — never auto-adopts.

The manual `/evolve` trigger and the body the nightly sleep cycle runs for THIS
workflow, wired to the central backend and the judge metric (Error-Clarity Test
Fidelity). The agents run on the Ollama backend (config.toml default); override
with FORGE_PROVIDER if needed.

  SkillOpt (per-agent, vertical):
    For each agent, propose a bounded edit to its skill document, evaluate the
    candidate on the HELD-OUT operations (results/clarity/held_out.jsonl) using the
    judge metric, and ACCEPT only on STRICT improvement of held-out fidelity.
    Accept or reject, the proposal + decision is STAGED under
    evolvers/skillopt/clarity/<agent>/staged/. best_skill.md is never overwritten here.

  SkillClaw (collective, horizontal):
    The shared pool (evolvers/skillclaw/clarity-shared/SKILL.md, local filesystem,
    air-gapped) is offered to all agents. This records the share manifest; adoption
    stays the user's call.

Usage:
    python evolvers/evolve_clarity.py [--agents ...] [--dry-run]   # backend = ollama (config default)
"""
from __future__ import annotations
import argparse
import json
import os
import subprocess
from datetime import datetime, timezone
from pathlib import Path

WS = Path(__file__).resolve().parents[1]
AGENTS = ["langgraph", "crewai", "claude_sdk", "api-tester-verify-error-message-clarity"]
AGENT_DIR = {a: f"agents/clarity/{a}/run.py" for a in AGENTS}


def _verdict_tuple(v):
    if not isinstance(v, dict):
        return None
    return (bool(v.get("message_present")), bool(v.get("code_present")),
            bool(v.get("sensitive_found")))


def _held_out_slugs() -> list[str]:
    out = []
    p = WS / "results" / "clarity" / "held_out.jsonl"
    for line in p.read_text().splitlines():
        line = line.strip()
        if line:
            out.append(json.loads(line)["slug"])
    return out


def _gold_truth(slugs: set[str]) -> dict:
    """(slug, code) -> (gold actual_code, gold verdict tuple) — same key the judge uses."""
    gold = json.loads((WS / "data" / "clarity" / "gold.json").read_text())
    truth = {}
    for ep in gold["endpoints"]:
        if ep["slug"] in slugs:
            for c in ep["cases"]:
                truth[(ep["slug"], c["documented_code"])] = (
                    c["actual_code"], _verdict_tuple(c.get("verdict")))
    return truth


def _candidate_skill(base_doc: str) -> str:
    """Bounded add edit distilled from the SkillClaw shared pool: reinforce that
    every documented error code must still get a descriptor (coverage), addressing
    the plausible failure where a model drops a code whose body it cannot predict."""
    addition = ('Always emit a descriptor for every documented error code, including codes '
                'whose response body you cannot predict; never omit a documented error code '
                'from the "requests" array, so the harness can observe and grade every '
                'documented error body.')
    return base_doc.rstrip() + "\n" + addition + "\n"


def _run_agent_on_heldout(agent: str, skill_doc: Path | None, run_id: str,
                          slugs: list[str]) -> Path:
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(WS)
    env["FORGE_SANDBOX_ROOT"] = str(WS)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_TARGET_BASE_URL"] = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899")
    env["FORGE_ONLY_SLUGS"] = ",".join(slugs)
    # Backend defaults to Ollama (config.toml); override with FORGE_PROVIDER if set.
    env.setdefault("FORGE_PROVIDER", "ollama")
    env["PATH"] = str(WS / ".venv" / "bin") + os.pathsep + env.get("PATH", "")
    if skill_doc is not None:
        env["FORGE_SKILL_DOC"] = str(skill_doc)
    else:
        env.pop("FORGE_SKILL_DOC", None)
    subprocess.run([str(WS / ".venv" / "bin" / "python"), AGENT_DIR[agent]],
                   cwd=str(WS), env=env, capture_output=True, text=True)
    return WS / "results" / "clarity" / "runs" / run_id / f"{agent}.cases.json"


def _heldout_fidelity(cases_path: Path, truth: dict) -> float:
    if not cases_path.exists():
        return 0.0
    doc = json.loads(cases_path.read_text())
    obs = {(c["slug"], c["documented_code"]): (c.get("actual_code"), _verdict_tuple(c.get("verdict")))
           for c in doc.get("cases", []) if c.get("covered")}
    denom = len(truth)
    if not denom:
        return 0.0
    matches = sum(1 for k, g in truth.items() if obs.get(k) == g)
    return round(100.0 * matches / denom, 2)


def skillopt_for_agent(agent: str, slugs: list[str], truth: dict) -> dict:
    base = WS / "evolvers" / "skillopt" / "clarity" / agent / "best_skill.md"
    staged = WS / "evolvers" / "skillopt" / "clarity" / agent / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    cand_path = staged / "candidate_skill.md"
    cand_path.write_text(_candidate_skill(base.read_text()))

    base_cases = _run_agent_on_heldout(agent, None, f"evolve-clarity-{agent}-base", slugs)
    base_fid = _heldout_fidelity(base_cases, truth)
    cand_cases = _run_agent_on_heldout(agent, cand_path, f"evolve-clarity-{agent}-cand", slugs)
    cand_fid = _heldout_fidelity(cand_cases, truth)

    accepted = cand_fid > base_fid
    decision = {"agent": agent, "ts": datetime.now(timezone.utc).isoformat(),
                "metric": "error_clarity_test_fidelity_heldout", "held_out_endpoints": slugs,
                "baseline_fidelity": base_fid, "candidate_fidelity": cand_fid,
                "accepted": accepted, "candidate_skill_path": str(cand_path),
                "note": ("STRICT-improvement gate. ACCEPTED candidate is STAGED only — "
                         "best_skill.md is NOT overwritten. Adopt manually after review.")}
    (staged / "decision.json").write_text(json.dumps(decision, indent=2))
    return decision


def skillclaw_share() -> dict:
    pool = WS / "evolvers" / "skillclaw" / "clarity-shared" / "SKILL.md"
    manifest = {"shared_skill": str(pool), "ts": datetime.now(timezone.utc).isoformat(),
                "offered_to": AGENTS, "backend": "local_filesystem", "air_gapped": True,
                "note": "Shared skill available to all agents; adoption is the user's call."}
    (WS / "evolvers" / "skillclaw" / "clarity_share_manifest.json").write_text(
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

    print(f"Self-evolution (staged) · held-out = {slugs} · {len(truth)} gold cases")
    if a.dry_run:
        print("[dry-run] skipping held-out agent runs.")
        skillclaw_share()
        return 0
    print("SkillOpt — per-agent, gated on held-out fidelity (strict improvement):\n")
    decisions = [skillopt_for_agent(ag, slugs, truth) for ag in agents]
    print(f"{'agent':45} {'baseline':>9} {'candidate':>10} {'decision':>10}")
    for d in decisions:
        verdict = "ACCEPT*" if d["accepted"] else "reject"
        print(f"{d['agent']:45} {d['baseline_fidelity']:>9} {d['candidate_fidelity']:>10} {verdict:>10}")
    man = skillclaw_share()
    print(f"\nSkillClaw — shared skill offered to {len(man['offered_to'])} agents "
          f"(local, air-gapped): {man['shared_skill']}")
    print("\n* ACCEPTED proposals are STAGED under evolvers/skillopt/clarity/<agent>/staged/.")
    print("  Nothing was adopted. Review decision.json + candidate_skill.md, then adopt manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
