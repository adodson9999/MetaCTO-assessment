#!/usr/bin/env python3
"""Phase 4.5 improvement tournament for code-review-adversarial-input (keep-if-improved, 10
rounds). Implements ``references/improvement-loop.md`` for the shared skill doc.

Same discipline as the security tournament, plus OLLAMA-CRASH RESILIENCE (the lesson from
that run, where ollama died under ~35 min of sustained load and rounds scored a spurious 0):

  - before every round, health-check the backend; if down, restart `ollama serve` and wait.
  - after scoring a round, if the result looks like a backend failure (any framework emitted
    a ConnectError / the run is uniformly 0 with gen_errors), restart ollama and RE-RUN that
    round once. A genuine prompt result is never silently corrupted by an outage.

The round (per references/improvement-loop.md):
  round 0  = the debate-gated baseline (advinput_prompt.APPROVED_PROMPT), establishes best.
  rounds 1..N: one bounded candidate edit each. PROPOSE (the candidate doc) -> GATE
  (single-concern edits, by construction) -> DETERMINISM (temperature=0 greedy) -> RUN (all
  four frameworks under FORGE_SKILL_DOC=<candidate>, same held-out/backend/concurrency) ->
  KEEP iff mean rating_band_accuracy strictly improves AND no framework drops below the
  round-0 floor, else DISCARD -> LOG.

Score per candidate = mean over the four frameworks of rating_band_accuracy, recomputed
from each framework's recorded per-case emissions against the gold bands (judge contract).

Artifacts:
  evolvers/skillopt/code-review/adversarial-input/best_skill.md
  evolvers/skillopt/code-review/adversarial-input/trajectory-<TS>.json
  results/code-review/adversarial-input/leaderboard-tournament-<TS>.md

Usage:
    python tournament.py --workspace <ws> --rounds 10 [--recheck] [--ts <stamp>]
"""
from __future__ import annotations

import argparse
import json
import os
import subprocess
import sys
import time
import uuid
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path
from urllib.request import urlopen

HERE = Path(__file__).resolve().parent
CAND_DIR = HERE / "candidates"
FRAMEWORKS = {
    "langgraph": "agents/code-review/adversarial-input/langgraph/run.py",
    "crewai": "agents/code-review/adversarial-input/crewai/run.py",
    "claude_sdk": "agents/code-review/adversarial-input/claude_sdk/run.py",
    "code-review-adversarial-input": "agents/code-review/adversarial-input/subagent/run.py",
}
OLLAMA_TAGS = "http://localhost:11434/api/tags"


def _pyexe(ws: Path) -> str:
    venv = ws / ".venv" / "bin" / "python"
    return str(venv) if venv.exists() else (sys.executable or "python3")


def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


# --------------------------------------------------------------------------- #
# Backend resilience
# --------------------------------------------------------------------------- #
def _ollama_up() -> bool:
    try:
        with urlopen(OLLAMA_TAGS, timeout=4) as r:
            return r.status == 200
    except Exception:  # noqa: BLE001
        return False


def ensure_ollama(wait_s: int = 60) -> bool:
    if _ollama_up():
        return True
    print("       [resilience] ollama down -> restarting `ollama serve`...", flush=True)
    subprocess.Popen(["ollama", "serve"], stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL)
    for _ in range(wait_s // 3):
        time.sleep(3)
        if _ollama_up():
            print("       [resilience] ollama back up", flush=True)
            return True
    print("       [resilience] ollama still down after restart", flush=True)
    return False


def _looks_like_outage(ws: Path, run_id: str) -> bool:
    """True if any framework recorded a connection error (a backend outage, not a result)."""
    run_dir = ws / "results" / "runs" / run_id
    for name in FRAMEWORKS:
        doc = _load(run_dir / f"{name}.cases.json", {})
        for e in doc.get("gen_errors", []):
            if "ConnectError" in str(e.get("error", "")) or "Connection refused" in str(e.get("error", "")):
                return True
    return False


# --------------------------------------------------------------------------- #
# Running / scoring one candidate
# --------------------------------------------------------------------------- #
def _run_one_framework(name: str, rel: str, ws: Path, run_id: str, skill_doc: Path | None) -> None:
    env = dict(os.environ)
    env["FORGE_WORKSPACE"] = str(ws)
    env["FORGE_RUN_ID"] = run_id
    env["FORGE_AGENT"] = name
    env["FORGE_SANDBOX_ROOT"] = str(ws)
    env["FORGE_PROVIDER"] = env.get("FORGE_PROVIDER", "ollama")
    if skill_doc is not None:
        env["FORGE_SKILL_DOC"] = str(skill_doc)
    else:
        env.pop("FORGE_SKILL_DOC", None)
    subprocess.run([_pyexe(ws), rel], cwd=str(ws), env=env, capture_output=True, text=True)


def _score(ws: Path, run_id: str, spec) -> dict:
    cases = spec.load_heldout(ws)
    golds = {c["id"]: c["gold_band"] for c in cases}
    run_dir = ws / "results" / "runs" / run_id
    per_fw: dict[str, float] = {}
    for name in FRAMEWORKS:
        doc = _load(run_dir / f"{name}.cases.json", {})
        total = correct = 0
        for case in doc.get("cases", []):
            gold = golds.get(case.get("case_id"))
            if gold is None:
                continue
            total += 1
            correct += 1 if spec.score_output(case.get("emitted") or {}, gold)["score"] >= 1.0 else 0
        per_fw[name] = round(correct / total, 4) if total else 0.0
    mean = round(sum(per_fw.values()) / len(per_fw), 4) if per_fw else 0.0
    return {"per_framework": per_fw, "mean": mean, "min": min(per_fw.values()) if per_fw else 0.0}


def run_round(ws: Path, label: str, skill_doc: Path | None, spec, retries: int = 1) -> dict:
    """Run all four frameworks once; on a detected backend outage, restart ollama and re-run
    (up to ``retries`` times) so an outage never masquerades as a prompt result."""
    for attempt in range(retries + 1):
        ensure_ollama()
        run_id = f"adv-tourney-{label}-{uuid.uuid4().hex[:6]}"
        with ThreadPoolExecutor(max_workers=4) as ex:
            futs = [ex.submit(_run_one_framework, n, r, ws, run_id, skill_doc)
                    for n, r in FRAMEWORKS.items()]
            for f in as_completed(futs):
                f.result()
        if _looks_like_outage(ws, run_id) and attempt < retries:
            print(f"       [resilience] outage detected in {run_id}; restarting + re-running round",
                  flush=True)
            ensure_ollama()
            continue
        sc = _score(ws, run_id, spec)
        sc["run_id"] = run_id
        return sc
    sc = _score(ws, run_id, spec)
    sc["run_id"] = run_id
    return sc


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--rounds", type=int, default=10)
    ap.add_argument("--ts", default=None)
    ap.add_argument("--recheck", action="store_true")
    a = ap.parse_args(argv[1:])

    ws = Path(a.workspace).resolve()
    ts = a.ts or uuid.uuid4().hex[:10]
    sys.path.insert(0, str(ws / "agents" / "common"))
    import advinput_spec as spec  # noqa: PLC0415

    trajectory: list[dict] = []

    base_doc = CAND_DIR / "round-00-baseline.md"
    print("[round 00] baseline (APPROVED_PROMPT)...", flush=True)
    base = run_round(ws, "r00", base_doc, spec)
    floor = dict(base["per_framework"])
    best = {"label": "round-00-baseline", "doc": base_doc, **base}
    trajectory.append({"round": 0, "edit": "baseline (debate-gated APPROVED_PROMPT)",
                       "per_framework": base["per_framework"], "mean": base["mean"],
                       "kept": True, "gate_ok": True, "determinism": "temp=0 greedy",
                       "run_id": base["run_id"]})
    print(f"           mean={base['mean']} per_fw={base['per_framework']}", flush=True)

    for r in range(1, a.rounds + 1):
        doc = CAND_DIR / f"round-{r:02d}.md"
        if not doc.exists():
            break
        print(f"[round {r:02d}] {doc.name}...", flush=True)
        sc = run_round(ws, f"r{r:02d}", doc, spec)
        improves = sc["mean"] > best["mean"] + 1e-9
        no_regression = all(sc["per_framework"][fw] >= floor[fw] - 1e-9 for fw in floor)
        kept = improves and no_regression
        if kept:
            best = {"label": f"round-{r:02d}", "doc": doc, **sc}
            floor = {fw: max(floor[fw], sc["per_framework"][fw]) for fw in floor}  # ratchet up
        trajectory.append({"round": r, "edit": doc.name,
                           "per_framework": sc["per_framework"], "mean": sc["mean"],
                           "kept": kept, "improves": improves, "no_regression": no_regression,
                           "gate_ok": True, "determinism": "temp=0 greedy", "run_id": sc["run_id"]})
        verdict = "KEPT (new best)" if kept else (
            "discard (no improvement)" if not improves else "discard (regressed a framework)")
        print(f"           mean={sc['mean']} per_fw={sc['per_framework']} -> {verdict}", flush=True)

    determinism_ok = None
    if a.recheck:
        print("[recheck] re-running best twice to confirm temp-0 determinism...", flush=True)
        re1 = run_round(ws, "recheckA", best["doc"], spec)
        re2 = run_round(ws, "recheckB", best["doc"], spec)
        determinism_ok = (re1["per_framework"] == re2["per_framework"]
                          and abs(re1["mean"] - re2["mean"]) < 1e-9)
        print(f"           recheckA={re1['mean']} recheckB={re2['mean']} deterministic={determinism_ok}",
              flush=True)

    (HERE / "best_skill.md").write_text(best["doc"].read_text())
    traj = {"task": "code-review / adversarial-input", "rounds": a.rounds,
            "baseline_mean": base["mean"], "best_label": best["label"], "best_mean": best["mean"],
            "best_per_framework": best["per_framework"],
            "improvement": round(best["mean"] - base["mean"], 4),
            "determinism_recheck": determinism_ok, "trajectory": trajectory}
    (HERE / f"trajectory-{ts}.json").write_text(json.dumps(traj, indent=2))

    lb = ["# Improvement tournament — code-review / adversarial-input", "",
          f"Baseline mean **{base['mean']}** → best mean **{best['mean']}** "
          f"(+{traj['improvement']}), winner **{best['label']}**.",
          f"Determinism recheck: {determinism_ok}.", "",
          "| round | edit | langgraph | crewai | claude_sdk | subagent | mean | kept |",
          "|---|---|---|---|---|---|---|---|"]
    for t in trajectory:
        pf = t["per_framework"]
        lb.append(f"| {t['round']:02d} | {t['edit']} | {pf['langgraph']} | {pf['crewai']} | "
                  f"{pf['claude_sdk']} | {pf['code-review-adversarial-input']} | {t['mean']} | "
                  f"{'✓' if t['kept'] else '·'} |")
    out_md = ws / "results" / "code-review" / "adversarial-input" / f"leaderboard-tournament-{ts}.md"
    out_md.write_text("\n".join(lb) + "\n")

    print("\n=== TOURNAMENT COMPLETE ===")
    print(f"baseline {base['mean']} -> best {best['mean']} (+{traj['improvement']}) winner {best['label']}")
    print(f"trajectory: {HERE / ('trajectory-' + ts + '.json')}")
    print(f"leaderboard: {out_md}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
