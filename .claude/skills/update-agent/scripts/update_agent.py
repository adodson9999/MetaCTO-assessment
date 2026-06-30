#!/usr/bin/env python3
"""update-agent — bring one existing agent through the v2 flow + a user change.

    update_agent.py <agent_name> <prompt ...> [--workspace DIR] [--rounds 10]

Brownfield, regression-protected: applies the user's change, re-runs every foundry
gate (debate, determinism, 95 quality, analyze, judge, improve, golden, guardrails),
and refuses to let the agent's judged metric fall below its golden baseline unless
the user's prompt explicitly authorized a tradeoff (references/flow.md).

The harness is deterministic; PROPOSE and the gates are subprocess hooks into the
foundry's own scripts so this loop stays model-free. Absent hooks == no-op pass, so
this runs in a partially scaffolded workspace without crashing.
"""
from __future__ import annotations

import argparse
import glob
import json
import re
import shutil
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

PY = sys.executable
TRADEOFF_RE = re.compile(r"even if it (lowers|reduces|drops)|accept the tradeoff", re.I)

# --- Code-review gate wiring (constitution Article I.10, no bypass) ----------
# The gate ships beside this orchestrator so the skill is self-sufficient. Its
# reviewer set is DYNAMIC: every agent discovered in <foundry>/agents/code-review/
# at run time, however many there are — each must run and score >=85 on every code
# target, no exception, no hardcoded count or list. See references/code-review-gate.md.
GATE = Path(__file__).resolve().parent / "code_review_gate.py"
sys.path.insert(0, str(Path(__file__).resolve().parent))
try:
    import code_review_gate as crg  # discover_perspectives / receipt_matches_folder / is_code_producing
except Exception:  # pragma: no cover — the gate is copied in beside us
    crg = None


def hook(ws: Path, name: str, *args) -> int:
    script = ws / "scripts" / name
    if not script.is_file():
        return 0
    return subprocess.run([PY, str(script), *args], cwd=str(ws)).returncode


def locate(ws: Path, agent_name: str) -> tuple[str, str] | None:
    for group in ("api-tester", "general"):
        for d in glob.glob(str(ws / "agents" / group / "*")):
            name = Path(d).name
            if name == agent_name or name.endswith(agent_name) or agent_name in name:
                return group, name
    return None


def golden_floor(ws: Path, group: str, name: str) -> float:
    g = ws / "tests" / "golden" / group / name / "golden.json"
    if not g.is_file():
        return float("-inf")
    try:
        return float(json.loads(g.read_text())["baseline"]["value"])
    except (KeyError, ValueError, json.JSONDecodeError):
        return float("-inf")


def latest_score(ws: Path, group: str, name: str) -> float:
    best = float("-inf")
    for f in sorted(glob.glob(str(ws / "results" / group / name / "leaderboard-*.json"))):
        try:
            d = json.loads(Path(f).read_text())
            best = max(best, float(d.get("this_run", d.get("score", best))))
        except (ValueError, json.JSONDecodeError):
            continue
    return best


def is_regression(after: float, floor: float, tradeoff: bool) -> bool:
    """The regression gate's predicate, extracted so it is unit-testable (no tautology).

    An update regresses when the post-update score fell below the recorded golden
    baseline and the user did not authorize a tradeoff. Used at TWO points with the
    SAME rule: the early single-agent regression gate (unchanged behavior) and the
    per-affected regression re-check folded into the code-review/completion contract.
    """
    return after < floor and not tradeoff


def affected_agents(primary: str, extra: list[str]) -> list[str]:
    """Every agent this update affects — primary first, de-duplicated, order kept.

    Multi-agent fan-out: the code-review gate and the regression re-check run once
    per entry, and EVERY affected agent must pass — no exception, no skip."""
    out: list[str] = []
    for ag in [primary, *extra]:
        if ag and ag not in out:
            out.append(ag)
    return out


def latest_receipt(ws: Path, agent: str) -> dict | None:
    """The most recent code-review receipt written for this agent, or None."""
    files = sorted(glob.glob(str(ws / "results" / "_global" / "code-review-*.json")))
    for f in reversed(files):
        try:
            d = json.loads(Path(f).read_text())
        except (ValueError, json.JSONDecodeError):
            continue
        if d.get("agent_under_build") == agent:
            return d
    return None


def code_review_contract_ok(receipt: dict | None, ws: Path) -> tuple[bool, str]:
    """No-bypass completion check for ONE affected agent's code-review receipt.

    Passes only when: a receipt exists (the gate ran); and when the gate APPLIES,
    status == 'pass' AND the receipt's reviewer set equals the current contents of
    agents/code-review/ (receipt_matches_folder — blocks a stale or short receipt
    that omitted a reviewer). A genuine does-not-apply receipt passes but must still
    exist. There is no path to completion without a matching, passing receipt.
    """
    if receipt is None:
        return False, "no code-review receipt (gate did not run)"
    if not receipt.get("applies"):
        return True, "does-not-apply (receipt present)"
    if receipt.get("status") != "pass":
        return False, (f"status={receipt.get('status')} min_rating={receipt.get('min_rating')} "
                       f"(rewrite to >=85 on every reviewer in agents/code-review/)")
    if crg is not None and not crg.receipt_matches_folder(receipt, ws):
        return False, "receipt reviewer set != agents/code-review/ (stale/short receipt — re-run)"
    return True, "pass"


def agent_is_code_producing(ws: Path, group: str, name: str) -> bool:
    """True when this agent itself writes/generates code (so the self-awareness clause
    applies). config.toml [code_review_gate].applies wins; else task_spec keywords."""
    if crg is None:
        return False
    applies = crg._read_config_applies(ws)
    spec = ""
    for cand in (ws / "data" / name / "task_spec.md",
                 ws / "data" / f"{group}-{name}" / "task_spec.md",
                 ws / "agents" / group / name / "task_spec.md"):
        if cand.is_file():
            spec = cand.read_text(encoding="utf-8", errors="replace")
            break
    return crg.is_code_producing(spec, applies)


def self_aware_ok(ws: Path, group: str, name: str) -> tuple[bool, str]:
    """For a code-producing agent, its system prompt must STATE that all code it
    creates is reviewed by every agent in agents/code-review/ at >=85, no exception,
    looping until it does — pointing to agents/code-review/ and the shared memory.
    Checks the canonical subagent prompt; absent the clause -> the update must add it."""
    sub = ws / "agents" / group / name / "subagent"
    mds = sorted(glob.glob(str(sub / "*.md")))
    if not mds:
        return True, "no subagent prompt to check"
    for md in mds:
        text = Path(md).read_text(encoding="utf-8", errors="replace").lower()
        if "agents/code-review/" in text and "85" in text:
            return True, "self-awareness clause present"
    return False, ("prompt missing the code-review self-awareness clause — must point to "
                   "agents/code-review/ and the >=85-on-every-reviewer rule (the update adds it)")


def run_code_review_gate(ws: Path, agent: str) -> int:
    """Run the dynamic code-review gate for ONE agent against the foundry.

    Discovers every reviewer in agents/code-review/ at run time and scores every
    code target (all four framework run.py + the judge score.py + produced code) at
    >=85. Writes results/_global/code-review-<TS>.json. Absent gate == no-op (the
    contract check still hard-halts on the missing receipt, so this never bypasses)."""
    if not GATE.is_file():
        return 0
    return subprocess.run([PY, str(GATE), "--workspace", str(ws), "--agent", agent],
                          cwd=str(ws)).returncode


def record_memory(ws: Path, ts: str, prompt: str, results: list[dict]) -> None:
    """Write the gate run to the shared EverOS pool (references/memory-everos.md):
    the discovered reviewer set, each affected agent's code-review result + regression
    check, and the update itself — under the shared project_id/app_id with each
    affected agent's agent_id, so any future update can read what it is tested against."""
    reviewers = crg.discover_perspectives(ws) if crg is not None else []
    mem_dir = ws / "memory" / "code-review"
    mem_dir.mkdir(parents=True, exist_ok=True)
    lines = [f"# Code-review gate run — {ts}", "",
             "project_id=agent-foundry  app_id=forge", "",
             "## Update (what was touched, why)", prompt, "",
             f"## Discovered reviewer set ({len(reviewers)})",
             ", ".join(reviewers) or "(none)", "",
             "## Per-affected-agent result (agent_id : code-review / regression)"]
    for r in results:
        lines.append(f"- agent_id={r['agent']}: code_review={r['cr']}  regression={r['reg']}  "
                     f"status={r['status']}  min_rating={r['min_rating']}")
        for fail in r.get("failures", []):
            lines.append(f"    - FAIL {fail.get('target')} :: {fail.get('perspective')} "
                         f"= {fail.get('rating')}  {fail.get('notes')}")
    (mem_dir / f"update-{ts}.md").write_text("\n".join(lines) + "\n")


def back_up(ws: Path, group: str, name: str, ts: str) -> Path:
    dest = ws / "archives" / f"update-{name}-{ts}"
    dest.mkdir(parents=True, exist_ok=True)
    src = ws / "agents" / group / name
    if src.is_dir():
        shutil.copytree(src, dest / "agent", dirs_exist_ok=True)
    judge = ws / "judge" / group / name
    if judge.is_dir():
        shutil.copytree(judge, dest / "judge", dirs_exist_ok=True)
    return dest


def write_spec(ws: Path, name: str, prompt: str, tradeoff: bool) -> None:
    sp = ws / "workspace"
    sp.mkdir(parents=True, exist_ok=True)
    (sp / f"update_spec-{name}.md").write_text(
        f"# Update Spec — {name}\n\n## User prompt\n{prompt}\n\n"
        f"## Tradeoff authorized\n{tradeoff}\n")


def write_report(ws: Path, name: str, info: dict) -> None:
    sp = ws / "workspace"
    sp.mkdir(parents=True, exist_ok=True)
    (sp / f"update-report-{name}.md").write_text(
        f"# Update Report — {name}, {info['ts']}\n\n"
        f"## Change applied\n{info['prompt']}\n(tradeoff: {info['tradeoff']})\n\n"
        f"## Score\nFLOOR: {info['floor']}  ·  after: {info['after']}  ·  "
        f"verdict: {info['verdict']}\n\n## Backup\n{info['backup']}\n")


def run_gates(ws: Path, group: str, name: str, rounds: int) -> None:
    agent = f"{group}/{name}"
    hook(ws, "debate_gate.py", "--agent", agent, "--changed-only")
    hook(ws, "determinism_check.py", "--artifact", f"{name}-update",
         "--kind", "agent_prompt", "--samples", "/dev/null")
    hook(ws, "slop_scan.py", str(ws / "agents" / group / name), "--fail-below", "95")
    hook(ws, "analyze.py", "--workspace", str(ws))
    hook(ws, "run_agents.py", "--only", agent)


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("agent_name")
    ap.add_argument("prompt", nargs="+")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--affected", action="append", default=[],
                    help="additional <group>/<name> agents this update affects; the "
                         "code-review gate AND the regression re-check run for each "
                         "(multi-agent fan-out — every affected agent must pass).")
    args = ap.parse_args()
    ws = Path(args.workspace).resolve()
    prompt = " ".join(args.prompt)
    tradeoff = bool(TRADEOFF_RE.search(prompt))
    ts = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%S")

    if hook(ws, "verify_build.py", "--phase", "4", "--workspace", str(ws)) != 0:
        print("update-agent: foundry incomplete (verify_build --phase 4). HARD-HALT.")
        return 1

    found = locate(ws, args.agent_name)
    if not found:
        print(f"update-agent: no existing agent matches '{args.agent_name}'. "
              f"This skill updates existing agents; use forge-agents to create one.")
        return 1
    group, name = found
    floor = golden_floor(ws, group, name)
    backup = back_up(ws, group, name, ts)
    write_spec(ws, name, prompt, tradeoff)
    print(f"update-agent: {group}/{name}  FLOOR={floor}  tradeoff={tradeoff}  backup={backup}")

    run_gates(ws, group, name, args.rounds)
    after = latest_score(ws, group, name)

    if is_regression(after, floor, tradeoff):
        print(f"REGRESSION: {after} < baseline {floor} and no tradeoff authorized. "
              f"HARD-HALT: revise the change, authorize the tradeoff, or restore "
              f"from {backup}.")
        write_report(ws, name, {"ts": ts, "prompt": prompt, "tradeoff": tradeoff,
                                "floor": floor, "after": after, "verdict": "regressed-halt",
                                "backup": str(backup)})
        return 1

    hook(ws, "improve_loop.py", "--agent", f"{group}/{name}", "--rounds", str(args.rounds))
    hook(ws, "golden_run.py", "--derive", "--workspace", str(ws))
    final = latest_score(ws, group, name)
    verdict = "improved" if final >= floor else "tradeoff-accepted"

    # --- Code-review gate + per-affected regression (Article I.10, NO BYPASS) ---
    # After the update is drafted and improved, BEFORE it can complete: run the
    # dynamic code-review gate (every reviewer in agents/code-review/ at >=85,
    # discovered at run time — covering all four framework run.py and the judge
    # score.py) for EVERY affected agent, and re-check each affected agent's
    # regression baseline (hold-or-improve, never drop). The update cannot complete
    # while any reviewer is <85, any receipt is missing/stale, the self-awareness
    # clause is absent on a code-producing agent, or any affected agent regressed.
    # On failure: hard-halt, show the notes, rewrite the code, re-run — loop with no
    # cap until every reviewer is >=85 for every affected agent.
    affected = affected_agents(f"{group}/{name}", args.affected)
    cr_results: list[dict] = []
    cr_failures: list[str] = []
    for ag in affected:
        run_code_review_gate(ws, ag)                 # writes results/_global/code-review-<TS>.json
        receipt = latest_receipt(ws, ag)
        ok, why = code_review_contract_ok(receipt, ws)
        g2, _, n2 = ag.partition("/")
        a_floor = golden_floor(ws, g2, n2)
        a_score = latest_score(ws, g2, n2)
        regressed = is_regression(a_score, a_floor, tradeoff)
        sa_ok, sa_why = True, "n/a"
        if agent_is_code_producing(ws, g2, n2):
            sa_ok, sa_why = self_aware_ok(ws, g2, n2)
        cr_results.append({
            "agent": ag, "cr": "pass" if ok else "FAIL",
            "reg": "ok" if not regressed else "REGRESSED",
            "status": (receipt or {}).get("status"),
            "min_rating": (receipt or {}).get("min_rating"),
            "failures": (receipt or {}).get("failures", []),
        })
        if not ok:
            cr_failures.append(f"{ag}: code-review {why}")
        if regressed:
            cr_failures.append(f"{ag}: regression {a_score} < baseline {a_floor} (no tradeoff)")
        if not sa_ok:
            cr_failures.append(f"{ag}: {sa_why}")
    if crg is not None:
        record_memory(ws, ts, prompt, cr_results)
    if cr_failures:
        print("CODE-REVIEW / REGRESSION GATE FAILED (HARD-HALT). Every affected agent must "
              "score >=85 on every reviewer in agents/code-review/ and hold its baseline:")
        for f in cr_failures:
            print("  - " + f)
        print("Rewrite the offending code, re-run the FULL reviewer set, and loop until every "
              "reviewer is >=85 for every affected agent. The update cannot complete.")
        write_report(ws, name, {"ts": ts, "prompt": prompt, "tradeoff": tradeoff,
                                "floor": floor, "after": final, "verdict": "code-review-halt",
                                "backup": str(backup)})
        return 1

    rc = hook(ws, "verify_build.py", "--phase", "6", "--workspace", str(ws))
    rc = hook(ws, "verify_files.py", "--workspace", str(ws)) or rc
    write_report(ws, name, {"ts": ts, "prompt": prompt, "tradeoff": tradeoff,
                            "floor": floor, "after": final, "verdict": verdict,
                            "backup": str(backup)})
    if rc != 0:
        print("update-agent: post-update output contract FAILED. HARD-HALT.")
        return 1
    print(f"update-agent: {group}/{name} updated. FLOOR={floor} -> {final} ({verdict}).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
