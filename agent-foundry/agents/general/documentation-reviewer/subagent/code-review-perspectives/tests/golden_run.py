#!/usr/bin/env python3
"""Golden regression runner for code-review-perspective agents.

Two kinds of golden case (see golden.json):

1. schema_cases -- pure Python, no model. Each carries an inline `output` and an
   `expect` of "pass" or "fail". The runner feeds it through the guardrail
   validator and checks the result matches `expect`. These ALWAYS run and are
   the deterministic forcing function for the output contract.

2. band_cases -- need a model. Each carries `input_code`, an `agent`, and an
   `expect_band` [min, max]. The runner does NOT call a model itself; you supply
   recorded agent outputs via --outputs <dir> (one file named <case-id>.txt /
   .json per case). For each supplied output the runner checks it validates AND
   its rating lands inside expect_band widened by `band_tolerance`. Missing
   outputs are reported as SKIPPED unless --require-bands is set.

Exit code 0 = every runnable case passed; 1 = a failure; 2 = a required band
case had no recorded output.

Usage:
    python golden_run.py                       # schema_cases only
    python golden_run.py --outputs ./recorded  # also check band_cases
    python golden_run.py --outputs ./recorded --require-bands
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
ROOT = HERE.parent
sys.path.insert(0, str(ROOT / "guardrails"))

import validate_output as vo  # noqa: E402

GOLDEN = HERE / "golden.json"


def load_golden() -> dict:
    with open(GOLDEN, "r", encoding="utf-8") as handle:
        return json.load(handle)


def run_schema_cases(golden: dict) -> tuple[int, int, list[str]]:
    passed = 0
    failed: list[str] = []
    cases = golden.get("schema_cases", [])
    for case in cases:
        want_pass = case["expect"] == "pass"
        got = vo.validate(case["output"])
        if got.ok == want_pass:
            passed += 1
        else:
            failed.append(
                f"schema_case '{case['id']}': expected {case['expect']}, "
                f"validator said {'pass' if got.ok else 'fail'}"
                + (f" ({'; '.join(got.errors)})" if got.errors else "")
            )
    return passed, len(cases), failed


def _find_output(outputs_dir: Path, case_id: str) -> str | None:
    for ext in (".txt", ".json", ""):
        candidate = outputs_dir / f"{case_id}{ext}"
        if candidate.is_file():
            return candidate.read_text(encoding="utf-8")
    return None


def run_band_cases(
    golden: dict, outputs_dir: Path | None, require_bands: bool
) -> tuple[int, int, list[str], list[str]]:
    passed = 0
    failed: list[str] = []
    skipped: list[str] = []
    cases = golden.get("band_cases", [])
    band_tol = int(golden.get("band_tolerance", 0))
    runnable = 0
    for case in cases:
        raw = _find_output(outputs_dir, case["id"]) if outputs_dir else None
        if raw is None:
            skipped.append(case["id"])
            continue
        runnable += 1
        res = vo.validate(raw)
        if not res.ok:
            failed.append(f"band_case '{case['id']}': output failed schema ({'; '.join(res.errors)})")
            continue
        rating = res.value["rating"]
        lo, hi = case["expect_band"]
        if (lo - band_tol) <= rating <= (hi + band_tol):
            passed += 1
        else:
            failed.append(
                f"band_case '{case['id']}': rating {rating} outside "
                f"[{lo}-{hi}] +/-{band_tol} for agent {case['agent']}"
            )
    if require_bands and skipped:
        failed.append(f"--require-bands set but no recorded output for: {', '.join(skipped)}")
    return passed, runnable, failed, skipped


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Golden runner for review-perspective agents.")
    ap.add_argument("--outputs", type=Path, default=None, help="dir of recorded agent outputs for band cases")
    ap.add_argument("--require-bands", action="store_true", help="fail if any band case lacks a recorded output")
    args = ap.parse_args(argv[1:])

    golden = load_golden()

    s_pass, s_total, s_fail = run_schema_cases(golden)
    b_pass, b_total, b_fail, b_skip = run_band_cases(golden, args.outputs, args.require_bands)

    print(f"schema_cases: {s_pass}/{s_total} passed")
    print(f"band_cases:   {b_pass}/{b_total} passed ({len(b_skip)} skipped, no recorded output)")

    failures = s_fail + b_fail
    if failures:
        print("\nFAILURES:")
        for f in failures:
            print(f"  - {f}")
        return 1

    print("\nGOLDEN SUITE PASSED")
    return 0


if __name__ == "__main__":
    raise SystemExit(main(sys.argv))
