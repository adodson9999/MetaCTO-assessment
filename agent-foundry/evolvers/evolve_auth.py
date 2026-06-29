#!/usr/bin/env python3
"""Self-evolution loop (SkillOpt + SkillClaw) for the auth-flow task — staged,
never auto-adopts. Mirror of evolve.py wired to the auth metric + harness.

  SkillOpt (per-agent, vertical):
    For each agent, propose a bounded edit to its skill document, evaluate the
    candidate on a DISJOINT HELD-OUT protected endpoint (results/auth_held_out.jsonl
    -> /user/me, same authUser middleware as the ranking endpoint /auth/me) using
    the judge metric (Auth-Flow Fidelity), and ACCEPT the edit only if it STRICTLY
    improves held-out fidelity. Accept or reject, the proposal + decision is STAGED
    under evolvers/skillopt_auth/<agent>/staged/. best_skill.md is never overwritten.

  SkillClaw (collective, horizontal):
    The shared skill pool (evolvers/skillclaw_auth/shared/SKILL.md, local fs,
    air-gapped) is offered to all agents; the share manifest is recorded; adoption
    stays the user's call.

Gate metric = judge/auth_metric.json. Held-out endpoint is disjoint from the
ranking endpoint, so optimization cannot tune the exact target it is graded on.

Usage:
    python evolvers/evolve_auth.py [--agents langgraph,crewai,...] [--dry-run]
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
sys.path.insert(0, str(WS / "agents" / "common"))
AGENTS = ["langgraph", "crewai", "claude_sdk", "api-tester-test-authentication-flows"]
AGENT_ENTRY = {
    "langgraph": "agents/langgraph/auth_run.py",
    "crewai": "agents/crewai/auth_run.py",
    "claude_sdk": "agents/claude_sdk/auth_run.py",
    "api-tester-test-authentication-flows": "agents/api-tester-test-authentication-flows/run.py",
}


def _held_out_path() -> str:
    line = (WS / "results" / "auth_held_out.jsonl").read_text().strip().splitlines()[0]
    return json.loads(line)["protected_path"]


def _build_heldout_gold(held_path: str, base_url: str, secret: str) -> tuple[dict, set]:
    """Probe the held-out endpoint to get its ground-truth classes (it uses the
    same authUser middleware, so this is deterministic), reusing auth_spec."""
    import auth_spec
    env_path = os.environ.get("FORGE_PROTECTED_PATH")
    os.environ["FORGE_PROTECTED_PATH"] = held_path
    # reload so PROTECTED_ENDPOINT picks up the override
    import importlib
    importlib.reload(auth_spec)
    exec_truth = {}
    for sname, label, recipe, _ in auth_spec.SUBTESTS_ITER():
        headers, _note = auth_spec.build_credential(recipe, base_url, secret)
        code, _txt = auth_spec._request(base_url, auth_spec.PROTECTED_ENDPOINT["method"],
                                        auth_spec.PROTECTED_ENDPOINT["path"], headers=headers)
        exec_truth[(sname, label)] = auth_spec.classify(code)
    na_truth = {x["item"] for x in auth_spec.NOT_APPLICABLE}
    if env_path is None:
        os.environ.pop("FORGE_PROTECTED_PATH", None)
    else:
        os.environ["FORGE_PROTECTED_PATH"] = env_path
    return exec_truth, na_truth


def _candidate_skill(base_doc: str) -> str:
    """Bounded add edit distilled from the SkillClaw pool: reinforce that the
    revoked recipe must revoke via POST /auth/logout and still expect 401."""
    addition = ('Reminder: the revoked sub-test must use the recipe '
                '{"kind": "revoked_token", "revoke_via": "POST /auth/logout"} with '
                'expected_class "401"; never change its revoke path or expected class.')
    return base_doc.rstrip() + "\n" + addition + "\n"


def _run_agent_heldout(agent: str, skill_doc: Path | None, run_id: str,
                       held_path: str, base_url: str, secret: str) -> Path:
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(WS)
    env["FORGE_SANDBOX_ROOT"] = str(WS)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_TARGET_BASE_URL"] = base_url
    env["FORGE_PROTECTED_PATH"] = held_path  # evaluate on the held-out endpoint
    env["JWT_SECRET"] = secret
    env["PATH"] = str(WS / ".venv" / "bin") + os.pathsep + env.get("PATH", "")
    if skill_doc is not None:
        env["FORGE_SKILL_DOC"] = str(skill_doc)
    else:
        env.pop("FORGE_SKILL_DOC", None)
    subprocess.run([str(WS / ".venv" / "bin" / "python"), AGENT_ENTRY[agent]],
                   cwd=str(WS), env=env, capture_output=True, text=True)
    return WS / "results" / "runs" / run_id / f"{agent}.cases.json"


def _heldout_fidelity(cases_path: Path, exec_truth: dict, na_truth: set) -> float:
    if not cases_path.exists():
        return 0.0
    doc = json.loads(cases_path.read_text())
    obs = {(c["scheme"], c["label"]): c["actual_class"]
           for c in doc.get("cases", [])
           if c.get("label") not in (None, "_none_") and c.get("actual_class") not in (None, "none")}
    na = {x.get("item") for x in doc.get("not_applicable_enumerated", [])
          if x.get("status") == "needs_to_be_built_and_tested"}
    denom = len(exec_truth) + len(na_truth)
    if not denom:
        return 0.0
    matches = sum(1 for k, g in exec_truth.items() if obs.get(k) == g)
    matches += sum(1 for item in na_truth if item in na)
    return round(100.0 * matches / denom, 2)


def skillopt_for_agent(agent: str, held_path: str, exec_truth: dict, na_truth: set,
                       base_url: str, secret: str) -> dict:
    base_doc = (WS / "evolvers" / "skillopt_auth" / agent / "best_skill.md").read_text()
    staged = WS / "evolvers" / "skillopt_auth" / agent / "staged"
    staged.mkdir(parents=True, exist_ok=True)
    cand_path = staged / "candidate_skill.md"
    cand_path.write_text(_candidate_skill(base_doc))

    base_cases = _run_agent_heldout(agent, None, f"evolve-auth-{agent}-base",
                                    held_path, base_url, secret)
    base_fid = _heldout_fidelity(base_cases, exec_truth, na_truth)
    cand_cases = _run_agent_heldout(agent, cand_path, f"evolve-auth-{agent}-cand",
                                    held_path, base_url, secret)
    cand_fid = _heldout_fidelity(cand_cases, exec_truth, na_truth)

    accepted = cand_fid > base_fid  # STRICT improvement on the held-out endpoint
    decision = {
        "agent": agent, "ts": datetime.now(timezone.utc).isoformat(),
        "metric": "auth_flow_fidelity_heldout", "held_out_endpoint": held_path,
        "baseline_fidelity": base_fid, "candidate_fidelity": cand_fid,
        "accepted": accepted, "candidate_skill_path": str(cand_path),
        "note": ("STRICT-improvement gate. ACCEPTED candidate is STAGED only — "
                 "best_skill.md is NOT overwritten. Adopt manually after review."),
    }
    (staged / "decision.json").write_text(json.dumps(decision, indent=2))
    # clean the held-out probe runs
    for rid in (f"evolve-auth-{agent}-base", f"evolve-auth-{agent}-cand"):
        import shutil
        shutil.rmtree(WS / "results" / "runs" / rid, ignore_errors=True)
    return decision


def skillclaw_share() -> dict:
    pool = WS / "evolvers" / "skillclaw_auth" / "shared" / "SKILL.md"
    if not pool.exists():
        pool.write_text("# Shared auth-flow skill pool (air-gapped, local)\n\n"
                        "Distilled cross-agent reminders for the authentication-flow task.\n"
                        "- Emit the three-key plan; never send requests or log in.\n"
                        "- Use the five fixed credential recipes exactly.\n"
                        "- expected_class is the correct-API rule (2xx valid / 401 invalid).\n"
                        "- Enumerate undocumented schemes as needs_to_be_built_and_tested.\n")
    manifest = {"shared_skill": str(pool), "ts": datetime.now(timezone.utc).isoformat(),
                "offered_to": AGENTS, "backend": "local_filesystem", "air_gapped": True,
                "note": "Shared skill available to all agents; adoption is the user's call."}
    (WS / "evolvers" / "skillclaw_auth" / "share_manifest.json").write_text(
        json.dumps(manifest, indent=2))
    return manifest


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--agents", default=",".join(AGENTS))
    ap.add_argument("--dry-run", action="store_true")
    a = ap.parse_args()
    agents = [x.strip() for x in a.agents.split(",") if x.strip()]

    base_url = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899")
    secret = os.environ.get("JWT_SECRET", "forge_test_secret")
    held_path = _held_out_path()
    exec_truth, na_truth = _build_heldout_gold(held_path, base_url, secret)

    print(f"Self-evolution (staged) · held-out endpoint = {held_path} · "
          f"{len(exec_truth) + len(na_truth)} gold checkpoints")
    print("SkillOpt — per-agent, gated on held-out Auth-Flow Fidelity (strict improvement):\n")
    decisions = [skillopt_for_agent(ag, held_path, exec_truth, na_truth, base_url, secret)
                 for ag in agents]
    print(f"{'agent':40} {'baseline':>9} {'candidate':>10} {'decision':>10}")
    for d in decisions:
        verdict = "ACCEPT*" if d["accepted"] else "reject"
        print(f"{d['agent']:40} {d['baseline_fidelity']:>9} {d['candidate_fidelity']:>10} {verdict:>10}")
    man = skillclaw_share()
    print(f"\nSkillClaw — shared skill offered to {len(man['offered_to'])} agents "
          f"(local, air-gapped): {man['shared_skill']}")
    print("\n* ACCEPTED proposals are STAGED under evolvers/skillopt_auth/<agent>/staged/.")
    print("  Nothing was adopted. Review decision.json + candidate_skill.md, then adopt manually.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
