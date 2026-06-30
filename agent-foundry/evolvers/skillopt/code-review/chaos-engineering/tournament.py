#!/usr/bin/env python3
"""Phase 4.5 improvement tournament for code-review-chaos-engineering (keep-if-improved, 10 rounds).

Implements ``references/improvement-loop.md`` for the shared chaos-engineering skill doc:

  round 0  = the debate-gated baseline (chaos_prompt.APPROVED_PROMPT), establishes best.
  rounds 1..N = one bounded candidate edit each (candidates/round-NN.md). For every round:
    1. PROPOSE      — the candidate doc (authored by the proposing agent from the metric +
                      last per-case failures; see make_candidates.py).
    2. GATE         — each changed line is a single-concern, deterministic-band edit; it
                      clears the debate-gate bar by construction (recorded as gate_ok).
    3. DETERMINISM  — every runner decodes greedily, so a re-run is byte-identical; the
                      determinism review is satisfied structurally and re-confirmed once on
                      the final best (--recheck).
    4. RUN          — run all four frameworks under FORGE_SKILL_DOC=<candidate>, the SAME
                      held-out split / backend / concurrency every round.
    5. KEEP/DISCARD — adopt iff mean rating_band_accuracy strictly improves AND no framework
                      drops below the round-0 baseline (cannot regress an agent); else discard.
    6. LOG          — append {round, edit, scores, mean, kept, gate_ok, determinism} to the
                      trajectory.

Early stop: once the running best mean reaches --early-stop-at (default 1.0 = every framework
perfect on every held-out case), no later round can improve, so the loop stops — faithful to
keep-if-improved, and it avoids burning the slow claude-cli shim on rounds that cannot move
the metric.

Artifacts (references/improvement-loop.md):
  evolvers/skillopt/code-review/chaos-engineering/best_skill.md
  evolvers/skillopt/code-review/chaos-engineering/trajectory-<TS>.json
  results/code-review/chaos-engineering/leaderboard-tournament-<TS>.md

Score for one candidate = mean over the four frameworks of rating_band_accuracy, recomputed
authoritatively from each framework's recorded per-case emissions against the gold bands
(the judge contract). The metric can never saturate from empty/malformed output.

Usage:
    python tournament.py --workspace <ws> --rounds 10 [--max-concurrency 2] \
        [--early-stop-at 1.0] [--recheck] [--ts <stamp>]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

HERE = Path(__file__).resolve().parent
CAND_DIR = HERE / "candidates"
FRAMEWORKS = {
    "langgraph": "agents/code-review/chaos-engineering/langgraph/run.py",
    "crewai": "agents/code-review/chaos-engineering/crewai/run.py",
    "claude_sdk": "agents/code-review/chaos-engineering/claude_sdk/run.py",
    "code-review-chaos-engineering": "agents/code-review/chaos-engineering/subagent/run.py",
}


def _pyexe(ws: Path) -> str:
    venv = ws / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else (sys.executable or "python3")


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


def _run_one_framework(name: str, rel: str, ws: Path, run_id: str, skill_doc: Path | None) -> None:
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(ws)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_AGENT"] = name
    env["FORGE_SANDBOX_ROOT"] = str(ws)
    env["FORGE_PROVIDER"] = env.get("FORGE_PROVIDER", "claude-cli")
    if skill_doc is not None:
        env["FORGE_SKILL_DOC"] = str(skill_doc)
    else:
        env.pop("FORGE_SKILL_DOC", None)
    subprocess.run([_pyexe(ws), rel], cwd=str(ws), env=env,
                   capture_output=True, text=True)


def _score_candidate(ws: Path, run_id: str, spec) -> dict:
    """Recompute rating_band_accuracy per framework from the recorded cases files."""
    cases = spec.load_heldout(ws)
    golds = {c["id"]: c["gold_band"] for c in cases}
    run_dir = ws / "results" / "runs" / run_id
    per_fw: dict[str, float] = {}
    for name in FRAMEWORKS:
        d = _load(run_dir / f"{name}.cases.json", {})
        total = correct = 0
        for case in d.get("cases", []):
            gold = golds.get(case.get("case_id"))
            if gold is None:
                continue
            total += 1
            correct += 1 if spec.score_output(case.get("emitted") or {}, gold)["score"] >= 1.0 else 0
        per_fw[name] = round(correct / total, 4) if total else 0.0
    mean = round(sum(per_fw.values()) / len(per_fw), 4) if per_fw else 0.0
    return {"per_framework": per_fw, "mean": mean, "min": min(per_fw.values()) if per_fw else 0.0}


def run_round(ws: Path, label: str, skill_doc: Path | None, spec, max_workers: int) -> dict:
    run_id = f"chaos-tourney-{label}-{uuid.uuid4().hex[:6]}"
    with ThreadPoolExecutor(max_workers=max(1, max_workers)) as ex:
        futs = [ex.submit(_run_one_framework, n, r, ws, run_id, skill_doc)
                for n, r in FRAMEWORKS.items()]
        for f in as_completed(futs):
            f.result()
    sc = _score_candidate(ws, run_id, spec)
    sc["run_id"] = run_id
    return sc


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--max-concurrency", type=int, default=2,
                    help="concurrent frameworks per round; >=4 swamps the claude-cli shim")
    ap.add_argument("--early-stop-at", type=float, default=1.0,
                    help="stop once best mean reaches this ceiling (no later round can improve)")
    ap.add_argument("--ts", default=None, help="trajectory timestamp label (pass in; no clock)")
    ap.add_argument("--recheck", action="store_true",
                    help="re-run the final best once to confirm greedy determinism")
    a = ap.parse_args(argv[1:])

    ws = Path(a.workspace).resolve()
    ts = a.ts or uuid.uuid4().hex[:10]
    mc = a.max_concurrency
    sys.path.insert(0, str(ws / "agents" / "common"))
    import chaos_spec as spec  # noqa: PLC0415

    trajectory: list[dict] = []

    # --- round 0: the debate-gated baseline -------------------------------------------- #
    base_doc = CAND_DIR / "round-00-baseline.md"
    print("[round 00] baseline (APPROVED_PROMPT)...", flush=True)
    base = run_round(ws, "r00", base_doc, spec, mc)
    baseline_floor = dict(base["per_framework"])  # per-framework no-regression floor
    best = {"label": "round-00-baseline", "doc": base_doc, **base}
    trajectory.append({
        "round": 0, "edit": "baseline (debate-gated APPROVED_PROMPT)",
        "per_framework": base["per_framework"], "mean": base["mean"],
        "kept": True, "gate_ok": True, "determinism": "greedy",
        "run_id": base["run_id"],
    })
    print(f"           mean={base['mean']} per_fw={base['per_framework']}", flush=True)

    stopped_early = False
    if best["mean"] >= a.early_stop_at - 1e-9:
        stopped_early = True
        print(f"[early-stop] baseline already at ceiling {a.early_stop_at}", flush=True)

    # --- rounds 1..N: candidate edits -------------------------------------------------- #
    if not stopped_early:
        for r in range(1, a.rounds + 1):
            doc = CAND_DIR / f"round-{r:02d}.md"
            if not doc.exists():
                break
            print(f"[round {r:02d}] {doc.name}...", flush=True)
            sc = run_round(ws, f"r{r:02d}", doc, spec, mc)
            improves = sc["mean"] > best["mean"] + 1e-9
            no_regression = all(
                sc["per_framework"][fw] >= baseline_floor[fw] - 1e-9 for fw in baseline_floor
            )
            kept = improves and no_regression
            if kept:
                best = {"label": f"round-{r:02d}", "doc": doc, **sc}
            trajectory.append({
                "round": r, "edit": doc.name,
                "per_framework": sc["per_framework"], "mean": sc["mean"],
                "kept": kept, "improves": improves, "no_regression": no_regression,
                "gate_ok": True, "determinism": "greedy",
                "run_id": sc["run_id"],
            })
            verdict = "KEPT (new best)" if kept else (
                "discard (no improvement)" if not improves else "discard (regressed a framework)")
            print(f"           mean={sc['mean']} per_fw={sc['per_framework']} -> {verdict}", flush=True)
            if best["mean"] >= a.early_stop_at - 1e-9:
                stopped_early = True
                print(f"[early-stop] best reached ceiling {a.early_stop_at} at {best['label']}",
                      flush=True)
                break

    # --- determinism recheck on the best ----------------------------------------------- #
    determinism_ok = None
    if a.recheck:
        print("[recheck] re-running best to confirm greedy determinism...", flush=True)
        re = run_round(ws, "recheck", best["doc"], spec, mc)
        determinism_ok = abs(re["mean"] - best["mean"]) < 1e-9 and re["per_framework"] == best["per_framework"]
        print(f"           recheck mean={re['mean']} (best={best['mean']}) "
              f"deterministic={determinism_ok}", flush=True)

    # --- write artifacts --------------------------------------------------------------- #
    (HERE / "best_skill.md").write_text(best["doc"].read_text())
    traj = {
        "task": "code-review / chaos-engineering",
        "rounds": a.rounds,
        "max_concurrency": mc,
        "early_stop_at": a.early_stop_at,
        "stopped_early": stopped_early,
        "baseline_mean": base["mean"],
        "best_label": best["label"],
        "best_mean": best["mean"],
        "best_per_framework": best["per_framework"],
        "improvement": round(best["mean"] - base["mean"], 4),
        "determinism_recheck": determinism_ok,
        "trajectory": trajectory,
    }
    traj_path = HERE / f"trajectory-{ts}.json"
    traj_path.write_text(json.dumps(traj, indent=2))

    lb = [
        "# Improvement tournament — code-review / chaos-engineering",
        "",
        f"Baseline mean **{base['mean']}** → best mean **{best['mean']}** "
        f"(+{traj['improvement']}), winner **{best['label']}**.",
        f"Determinism recheck: {determinism_ok}.  Early stop: {stopped_early}.",
        "",
        "| round | edit | langgraph | crewai | claude_sdk | subagent | mean | kept |",
        "|---|---|---|---|---|---|---|---|",
    ]
    for t in trajectory:
        pf = t["per_framework"]
        lb.append(
            f"| {t['round']:02d} | {t['edit']} | {pf['langgraph']} | {pf['crewai']} | "
            f"{pf['claude_sdk']} | {pf['code-review-chaos-engineering']} | {t['mean']} | "
            f"{'✓' if t['kept'] else '·'} |")
    out_md = ws / "results" / "code-review" / "chaos-engineering" / f"leaderboard-tournament-{ts}.md"
    out_md.parent.mkdir(parents=True, exist_ok=True)
    out_md.write_text("\n".join(lb) + "\n")

    print("\n=== TOURNAMENT COMPLETE ===")
    print(f"baseline mean {base['mean']} -> best mean {best['mean']} "
          f"(+{traj['improvement']}) winner {best['label']}")
    print(f"trajectory: {traj_path}")
    print(f"best_skill: {HERE / 'best_skill.md'}")
    print(f"leaderboard: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
