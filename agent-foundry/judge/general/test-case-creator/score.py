#!/usr/bin/env python3
"""Judge scorer + discriminator for the Test-Case-Creator task ("n600").

The four framework agents each emit a per-step test-case registry (blind to the gold).
This step re-scores every agent's emitted registry **authoritatively** against the
deterministic gold in ``data/test-case-creator/gold.json`` — it never trusts the
number the harness self-reported, which is precisely how the old metric saturated
(a benign-wrong / empty fallback was credited as 100%).

Gates (the authorized anti-saturation metric move; see metric.json):

  G4  anti-saturation oracle  — reference input scores 100; empty {}/[] scores a low
      floor (never 100); single-knob mutations (drop a step, flip one involves_*, blank
      an Assert clause, invent an extra case) each strictly lower the score. Proven by
      ``score.py --oracle`` (exits non-zero if the metric stops discriminating).
  G5  schema validity         — a case counts only if it has EXACTLY the eleven keys,
      correct types, and a unique tc_id. Malformed cases (incl. TC-ERR sentinels) are
      dropped from the scored set, never credited as covered.
  G6  tc_id set equality      — per enabled agent, the emitted valid tc_ids must equal
      the gold tc_ids: no invented extras, no omissions.
  G8  gold determinism        — rebuilding the reference registry twice is byte-identical.
  G9  denominator intact      — gold_tc == sum of numbered steps over enabled agents, and
      every gold tc_id is reproduced or explained by a logged failure sentinel.
  G10 regression floor        — coverage and field-accuracy may not drop below the last
      accepted golden baseline (tradeoff-authorized drops are recorded, not silently
      swallowed).

Ranking: quality_score desc, coverage desc, field-accuracy desc, invented-extras asc,
tokens asc, elapsed asc. ``quality_score`` = coverage x field-accuracy x set-equality, so
it is 100 only for a perfect reproduction and strictly drops for any single-knob defect.

Usage:
    python judge/general/test-case-creator/score.py --workspace . --run-id <id>
    python judge/general/test-case-creator/score.py --workspace . --oracle
    python judge/general/test-case-creator/score.py --workspace . --check-regression --run-id <id>
"""
from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path

TASK = "test-case-creator"
GROUP = "general"


# --------------------------------------------------------------------------- #
# IO helpers
# --------------------------------------------------------------------------- #
def _load(p: Path, default=None):
    try:
        return json.loads(p.read_text())
    except Exception:  # noqa: BLE001
        return default


def _import_spec(ws: Path):
    sys.path.insert(0, str(ws / "agents" / "common"))
    import testcase_spec  # noqa: PLC0415
    return testcase_spec


def _resolve_spec_path(ws: Path, manifest_dir: Path, spec_path: str) -> Path:
    raw = Path(spec_path)
    if raw.is_absolute():
        return raw
    for base in (ws, manifest_dir):
        cand = (base / raw).resolve()
        if cand.exists():
            return cand
    return (ws / raw).resolve()


def _enabled_specs(ws: Path) -> list[dict]:
    """The enabled agent specs from the build manifest: [{name, spec_text}]."""
    manifest_path = ws / "data" / TASK / "manifest.json"
    entries = _load(manifest_path, [])
    out: list[dict] = []
    for e in entries:
        if isinstance(e, dict) and e.get("enabled") is True:
            sf = _resolve_spec_path(ws, manifest_path.parent, e["spec_path"])
            out.append({"name": e["name"], "spec_text": sf.read_text()})
    return out


def _gold_registry(ws: Path) -> list[dict]:
    gold = _load(ws / "data" / TASK / "gold.json", {})
    return gold.get("registry", []) if isinstance(gold, dict) else []


# --------------------------------------------------------------------------- #
# G5 — schema validity
# --------------------------------------------------------------------------- #
def validate_case(case, fields: list[str], bool_fields: set[str]) -> str | None:
    """Return None if the case is schema-valid, else a short reason string."""
    if not isinstance(case, dict):
        return "not_an_object"
    if set(case.keys()) != set(fields):
        return "wrong_key_set"
    for f in fields:
        v = case[f]
        if f in bool_fields:
            if not isinstance(v, bool):
                return f"non_bool:{f}"
        elif not isinstance(v, str):
            return f"non_str:{f}"
    return None


def partition_valid(emitted: list, spec) -> tuple[list[dict], list[dict]]:
    """Split an emitted registry into (valid, malformed). Duplicate tc_ids keep the
    first occurrence; later duplicates are malformed. Malformed cases are never scored."""
    valid: list[dict] = []
    malformed: list[dict] = []
    seen: set[str] = set()
    for case in emitted or []:
        reason = validate_case(case, spec.REGISTRY_FIELDS, spec.BOOL_FIELDS)
        if reason is None:
            tc_id = case["tc_id"]
            if tc_id in seen:
                malformed.append({"tc_id": tc_id, "reason": "duplicate_tc_id"})
                continue
            seen.add(tc_id)
            valid.append(case)
        else:
            tc_id = case.get("tc_id") if isinstance(case, dict) else None
            malformed.append({"tc_id": tc_id, "reason": reason})
    return valid, malformed


# --------------------------------------------------------------------------- #
# G6 — per-agent tc_id set equality
# --------------------------------------------------------------------------- #
def set_equality(valid: list[dict], gold_registry: list[dict]) -> dict:
    """Invented extras (emitted valid tc_ids absent from gold) and omissions (gold tc_ids
    not emitted), counted globally; equal=True only when both are empty."""
    gold_ids = {tc["tc_id"] for tc in gold_registry}
    emit_ids = {c["tc_id"] for c in valid}
    extras = sorted(emit_ids - gold_ids)
    omissions = sorted(gold_ids - emit_ids)
    return {"invented_extras": extras, "omissions": omissions,
            "equal": not extras and not omissions}


# --------------------------------------------------------------------------- #
# G9 — denominator integrity
# --------------------------------------------------------------------------- #
def denominator_check(ws: Path, spec, gold_registry: list[dict]) -> dict:
    """gold_tc must equal the sum of numbered steps over the enabled agent specs."""
    total_steps = 0
    for s in _enabled_specs(ws):
        how = spec.extract_how(s["spec_text"]) or ""
        total_steps += len(spec.extract_steps(how))
    gold_tc = len(gold_registry)
    return {"gold_tc": gold_tc, "recomputed_steps": total_steps, "ok": gold_tc == total_steps}


def coverage_explained(gold_registry: list[dict], valid: list[dict],
                       sentinels: list[dict]) -> dict:
    """Every gold tc_id must be reproduced OR explained by a per-agent failure sentinel."""
    gold_ids = {tc["tc_id"]: tc["agent"] for tc in gold_registry}
    emit_ids = {c["tc_id"] for c in valid}
    sentinel_agents = {s.get("agent") for s in sentinels}
    unexplained = sorted(
        tc_id for tc_id, agent in gold_ids.items()
        if tc_id not in emit_ids and agent not in sentinel_agents
    )
    return {"all_explained": not unexplained, "unexplained": unexplained}


# --------------------------------------------------------------------------- #
# Composite quality score (the discriminating headline used for ranking)
# --------------------------------------------------------------------------- #
def quality_score(coverage_pct: float, field_acc_pct: float,
                  invented_extras: int, gold_tc: int) -> float:
    """coverage x field-accuracy x set-equality, in percent.

    100 only when coverage=100, field-accuracy=100, and there are no invented extras.
    Strictly drops if a step is dropped (coverage), a boolean flips or an Assert clause
    is blanked (field-accuracy), or an extra case is invented (set-equality)."""
    set_eq = gold_tc / (gold_tc + invented_extras) if (gold_tc + invented_extras) else 0.0
    return round((coverage_pct / 100.0) * (field_acc_pct / 100.0) * set_eq * 100.0, 2)


# --------------------------------------------------------------------------- #
# Score one agent's emitted registry for a run
# --------------------------------------------------------------------------- #
def score_emitted(emitted: list, gold_registry: list[dict], ws: Path, spec) -> dict:
    """Authoritative re-scoring of one emitted registry. Pure: no run-dir IO."""
    sentinels = [c for c in (emitted or [])
                 if isinstance(c, dict) and str(c.get("tc_id", "")).startswith("TC-ERR-")]
    valid, malformed = partition_valid(emitted, spec)
    scored = spec.score_registry(valid, gold_registry)
    eq = set_equality(valid, gold_registry)
    explained = coverage_explained(gold_registry, valid, sentinels)
    coverage = scored["coverage_rate_pct"]
    field_acc = scored["field_accuracy_pct"]
    qscore = quality_score(coverage, field_acc, len(eq["invented_extras"]), len(gold_registry))
    return {
        "quality_score": qscore,
        "coverage_rate_pct": coverage,
        "field_accuracy_pct": field_acc,
        "gold_tc": scored["gold_tc"],
        "present_tc": scored["present_tc"],
        "schema_valid_count": len(valid),
        "malformed_count": len(malformed),
        "malformed": malformed[:25],
        "sentinel_count": len(sentinels),
        "g5_schema_ok": len(malformed) == 0,
        "g6_set_equality": eq,
        "g9_coverage_explained": explained,
        "missing_tc": scored["missing_tc"][:25],
        "field_mismatches": scored["field_mismatches"][:25],
    }


def _emitted_for(meta: dict, run_dir: Path) -> list | None:
    """Load the authoritative emitted registry for an agent's emit JSON, or None if this
    is not a test-case-creator run."""
    raw = _load(Path(meta.get("raw_output_path", "")), {})
    if not (isinstance(raw, dict) and "test_case_coverage_rate_pct" in raw):
        return None
    agent = meta.get("agent", "")
    reg_path = run_dir / f"{agent}.emitted-registry.json"
    emitted = _load(reg_path, None)
    return emitted if isinstance(emitted, list) else []


# --------------------------------------------------------------------------- #
# Leaderboard
# --------------------------------------------------------------------------- #
def _write_leaderboard(ws: Path, out_prefix: str, run_id: str, rows: list,
                       gates: dict) -> None:
    lb_path = ws / f"{out_prefix}.json"
    lb_path.parent.mkdir(parents=True, exist_ok=True)
    lb = _load(lb_path, {"task": TASK, "runs": []})
    lb["task"] = TASK
    lb["rank_key"] = ("quality_score desc, coverage desc, field_accuracy desc, "
                      "invented_extras asc, tokens asc, elapsed asc")
    lb["runs"].append({"run_id": run_id, "ts": datetime.now(timezone.utc).isoformat(),
                       "gates": gates, "ranking": rows})
    lb_path.write_text(json.dumps(lb, indent=2))

    md = [f"# Leaderboard — {TASK} (n600)",
          "Rank key: **quality_score ↓ → coverage ↓ → field-accuracy ↓ → "
          "invented-extras ↑ → tokens ↑ → elapsed ↑**",
          f"quality_score = coverage x field-accuracy x set-equality (100 only for a "
          f"perfect reproduction)  ·  Updated: {datetime.now(timezone.utc).isoformat()}  "
          f"·  run: {run_id}",
          f"Gates — G8 gold-determinism: {gates.get('g8_gold_deterministic')}  ·  "
          f"G9 denominator: {gates.get('g9_denominator_ok')}",
          "",
          "| Rank | Agent | Quality | Coverage% | FieldAcc% | Valid | Malformed | "
          "Extras | Omissions | G9 |",
          "|------|-------|---------|-----------|-----------|-------|-----------|"
          "--------|-----------|----|"]
    for i, r in enumerate(rows, 1):
        md.append(
            f"| {i} | {r['agent']} | {r['quality_score']:g} | {r['coverage_rate_pct']:g} | "
            f"{r['field_accuracy_pct']:g} | {r['schema_valid_count']} | "
            f"{r['malformed_count']} | {len(r['g6_set_equality']['invented_extras'])} | "
            f"{len(r['g6_set_equality']['omissions'])} | "
            f"{'ok' if r['g9_coverage_explained']['all_explained'] else 'GAP'} |")
    (ws / f"{out_prefix}.md").write_text("\n".join(md) + "\n")
    print("\n".join(md))


# --------------------------------------------------------------------------- #
# Default mode — score a run
# --------------------------------------------------------------------------- #
def run_scoring(ws: Path, run_id: str, out_prefix: str) -> int:
    spec = _import_spec(ws)
    gold_registry = _gold_registry(ws)
    if not gold_registry:
        print("[error] no gold registry — run data/test-case-creator/build_gold.py first.")
        return 1

    gates = {
        "g8_gold_deterministic": gold_determinism(ws, spec),
        "g9_denominator_ok": denominator_check(ws, spec, gold_registry)["ok"],
    }
    run_dir = ws / "results" / "runs" / run_id
    rows = []
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith((".cases.json", ".emitted-registry.json")):
            continue
        meta = _load(jf, {})
        if not isinstance(meta, dict):
            continue  # sidecar arrays / non-emit files
        emitted = _emitted_for(meta, run_dir)
        if emitted is None:
            continue  # not a test-case-creator run
        s = score_emitted(emitted, gold_registry, ws, spec)
        tokens = int((meta.get("tokens") or {}).get("total_tokens", 0)
                     or meta.get("tokens_total", 0) or 0)
        elapsed = float(meta.get("elapsed_seconds", 0.0) or 0.0)
        meta.update({
            "metric_name": "test_case_coverage_rate_pct",
            "metric_value": s["coverage_rate_pct"],
            "quality_score": s["quality_score"],
            "test_case_field_accuracy_pct": s["field_accuracy_pct"],
            "schema_valid_count": s["schema_valid_count"],
            "malformed_count": s["malformed_count"],
            "invented_extras": s["g6_set_equality"]["invented_extras"],
            "omissions": s["g6_set_equality"]["omissions"],
            "g6_set_equality_ok": s["g6_set_equality"]["equal"],
            "g9_coverage_explained": s["g9_coverage_explained"]["all_explained"],
            "tokens_total": tokens, "elapsed_seconds": elapsed,
        })
        jf.write_text(json.dumps(meta, indent=2))
        s.update({"agent": meta.get("agent", jf.stem), "tokens": tokens, "elapsed": elapsed})
        rows.append(s)

    if not rows:
        print("[warn] no test-case-creator agent results found for this run.")
        return 1

    def keyf(r):
        tok = r["tokens"] if r["tokens"] > 0 else float("inf")
        return (-r["quality_score"], -r["coverage_rate_pct"], -r["field_accuracy_pct"],
                len(r["g6_set_equality"]["invented_extras"]), tok, r["elapsed"])
    rows.sort(key=keyf)

    _write_leaderboard(ws, out_prefix, run_id, rows, gates)
    return 0


# --------------------------------------------------------------------------- #
# G8 — gold determinism
# --------------------------------------------------------------------------- #
def gold_determinism(ws: Path, spec) -> bool:
    """Rebuilding the reference registry twice from the manifest is byte-identical."""
    specs = _enabled_specs(ws)
    a = json.dumps(spec.build_reference_registry([dict(x) for x in specs]), sort_keys=True)
    b = json.dumps(spec.build_reference_registry([dict(x) for x in specs]), sort_keys=True)
    return a == b


# --------------------------------------------------------------------------- #
# G4 + G8 — the oracle suite (acceptance gate)
# --------------------------------------------------------------------------- #
def _mutate_drop_step(reg: list[dict]) -> list[dict]:
    return [dict(c) for c in reg[1:]]  # drop the first case


def _mutate_flip_bool(reg: list[dict], spec) -> list[dict]:
    out = [dict(c) for c in reg]
    bf = sorted(spec.BOOL_FIELDS)[0]
    out[0] = dict(out[0]); out[0][bf] = not out[0][bf]
    return out


def _mutate_blank_assert(reg: list[dict]) -> list[dict]:
    out = [dict(c) for c in reg]
    for i, c in enumerate(out):
        if c.get("expected_outcome", "").startswith("Assert "):
            out[i] = dict(c); out[i]["expected_outcome"] = ""
            return out
    out[0] = dict(out[0]); out[0]["expected_outcome"] = ""  # fallback
    return out


def _mutate_invent_extra(reg: list[dict]) -> list[dict]:
    out = [dict(c) for c in reg]
    bogus = dict(out[0]); bogus["tc_id"] = "bogus-invented-step-99"; bogus["step_id"] = "99"
    out.append(bogus)
    return out


def _q(emitted: list, gold: list[dict], ws: Path, spec) -> float:
    return score_emitted(emitted, gold, ws, spec)["quality_score"]


def run_oracle(ws: Path) -> int:
    """Prove the metric discriminates. Exits non-zero on any failure (acceptance gate)."""
    spec = _import_spec(ws)
    gold = _gold_registry(ws)
    checks: list[tuple[str, bool, str]] = []

    if not gold:
        print("[oracle] FAIL: no gold registry."); return 1

    ref = _q(gold, gold, ws, spec)
    checks.append(("G4 reference scores 100", ref == 100.0, f"quality={ref}"))

    empty_arr = _q([], gold, ws, spec)
    checks.append(("G4 empty [] scores 0 (not 100)", empty_arr == 0.0, f"quality={empty_arr}"))

    empty_obj = _q([{}], gold, ws, spec)  # a single malformed object
    checks.append(("G4 empty/malformed {} scores 0", empty_obj == 0.0, f"quality={empty_obj}"))

    sentinels = [{"tc_id": f"TC-ERR-{a}", "agent": a, "outcome": "ERROR",
                  "reason": "extraction_failure", "fail": True}
                 for a in {tc["agent"] for tc in gold}]
    sent_q = _q(sentinels, gold, ws, spec)
    checks.append(("G4 all-sentinel (the 0/13 collapse) scores 0", sent_q == 0.0,
                   f"quality={sent_q}"))

    drop_q = _q(_mutate_drop_step(gold), gold, ws, spec)
    checks.append(("G4 drop-a-step lowers score", drop_q < 100.0, f"quality={drop_q}"))

    flip_q = _q(_mutate_flip_bool(gold, spec), gold, ws, spec)
    checks.append(("G4 flip-one-involves_* lowers score", flip_q < 100.0, f"quality={flip_q}"))

    blank_q = _q(_mutate_blank_assert(gold), gold, ws, spec)
    checks.append(("G4 blank-an-Assert lowers score", blank_q < 100.0, f"quality={blank_q}"))

    extra_q = _q(_mutate_invent_extra(gold), gold, ws, spec)
    checks.append(("G4 invent-an-extra lowers score", extra_q < 100.0, f"quality={extra_q}"))

    checks.append(("G8 gold registry is deterministic", gold_determinism(ws, spec), ""))

    den = denominator_check(ws, spec, gold)
    checks.append(("G9 gold_tc == sum of steps per enabled agent", den["ok"],
                   f"gold_tc={den['gold_tc']} steps={den['recomputed_steps']}"))

    ok = all(passed for _, passed, _ in checks)
    print(f"# Oracle suite — {TASK} (G4 anti-saturation + G8 + G9)\n")
    for name, passed, detail in checks:
        print(f"  [{'PASS' if passed else 'FAIL'}] {name}" + (f"  ({detail})" if detail else ""))
    print(f"\n{'ORACLE PASS — metric discriminates' if ok else 'ORACLE FAIL'}")
    return 0 if ok else 1


# --------------------------------------------------------------------------- #
# G10 — regression floor vs golden baseline
# --------------------------------------------------------------------------- #
def check_regression(ws: Path, run_id: str) -> int:
    spec = _import_spec(ws)
    gold = _gold_registry(ws)
    golden = _load(ws / "tests" / "golden" / GROUP / TASK / "golden.json", {})
    base = (golden.get("baseline") or {})
    floor_cov = float(base.get("coverage_pct", 0.0) or 0.0)
    floor_field = float(base.get("field_accuracy_pct", 0.0) or 0.0)
    tol = float(base.get("tolerance", 0.0) or 0.0)

    run_dir = ws / "results" / "runs" / run_id
    worst_cov, worst_field, best_agent = None, None, None
    for jf in sorted(run_dir.glob("*.json")):
        if jf.name.endswith((".cases.json", ".emitted-registry.json")):
            continue
        meta = _load(jf, {})
        if not isinstance(meta, dict):
            continue
        emitted = _emitted_for(meta, run_dir)
        if emitted is None:
            continue
        s = score_emitted(emitted, gold, ws, spec)
        if best_agent is None or s["coverage_rate_pct"] > worst_cov:
            worst_cov, worst_field = s["coverage_rate_pct"], s["field_accuracy_pct"]
            best_agent = meta.get("agent")
    if best_agent is None:
        print("[regression] no test-case-creator results in run."); return 1

    cov_ok = worst_cov >= floor_cov - tol
    field_ok = worst_field >= floor_field - tol
    print(f"# G10 regression — best agent {best_agent}")
    print(f"  coverage:       {worst_cov} vs floor {floor_cov} (tol {tol}) -> "
          f"{'OK' if cov_ok else 'REGRESSION'}")
    print(f"  field-accuracy: {worst_field} vs floor {floor_field} (tol {tol}) -> "
          f"{'OK' if field_ok else 'REGRESSION'}")
    return 0 if (cov_ok and field_ok) else 2


# --------------------------------------------------------------------------- #
# Entry point
# --------------------------------------------------------------------------- #
def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id")
    ap.add_argument("--out-prefix", default=f"results/leaderboard-{TASK}")
    ap.add_argument("--oracle", action="store_true",
                    help="run the G4/G8/G9 discrimination proof and exit")
    ap.add_argument("--check-regression", action="store_true",
                    help="check this run against the golden baseline (G10)")
    a = ap.parse_args()
    ws = Path(a.workspace).resolve()

    if a.oracle:
        return run_oracle(ws)
    if a.check_regression:
        if not a.run_id:
            ap.error("--check-regression requires --run-id")
        return check_regression(ws, a.run_id)
    if not a.run_id:
        ap.error("--run-id is required (or pass --oracle)")
    return run_scoring(ws, a.run_id, a.out_prefix)


if __name__ == "__main__":
    raise SystemExit(main())
