#!/usr/bin/env python3
"""Golden regression runner for the System-Design code-review agent.

Self-contained and deterministic — needs NO model. It exercises the same scorer the live
harness and judge use (``agents/common/sysdesign_spec.py``), so a green run proves the
output contract and the metric baseline hold:

1. schema_cases — each inline ``output`` is fed through ``sysdesign_spec.schema_ok`` and
   must match its ``expect`` ("pass"/"fail"). These are the deterministic forcing function
   for the {rating, notes} contract.
2. band_cases — the labeled held-out examples. For each, the reference oracle
   (``build_reference_decision``, rating = band midpoint) must score 1.0 (a known-good
   in-band baseline an empty emission cannot reproduce). When ``--outputs <dir>`` is given,
   a recorded live output named ``<case-id>.json``/``.txt`` is also scored against the band.
3. saturation guard — an empty emission must score 0.0 on every band case.

Exit 0 = all runnable cases passed; 1 = a failure.

Usage:
    python run_golden.py                       # schema + oracle + saturation (no model)
    python run_golden.py --outputs ./recorded  # also score recorded live agent outputs
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

HERE = Path(__file__).resolve().parent
# .../agent-foundry/tests/golden/code-review/system-design -> workspace = parents[4]
WS = Path(__import__("os").environ.get("FORGE_WORKSPACE", str(HERE.parents[4]))).resolve()
sys.path.insert(0, str(WS / "agents" / "common"))
import sysdesign_spec as spec  # noqa: E402

GOLDEN = HERE / "golden.json"


def _extract(raw: str):
    """Best-effort: parse a recorded output into a dict ({} if it cannot be parsed)."""
    try:
        obj = json.loads(raw.strip())
        return obj if isinstance(obj, dict) else {}
    except Exception:  # noqa: BLE001
        return {}


def run_schema_cases(golden: dict) -> tuple[int, int, list[str]]:
    passed, failed = 0, []
    cases = golden.get("schema_cases", [])
    for c in cases:
        want_pass = c["expect"] == "pass"
        got = spec.schema_ok(c["output"])
        if got == want_pass:
            passed += 1
        else:
            failed.append(f"schema_case '{c['id']}': expected {c['expect']}, scorer said "
                          f"{'pass' if got else 'fail'}")
    return passed, len(cases), failed


def run_band_cases(golden: dict, outputs_dir: Path | None) -> tuple[int, int, list[str]]:
    passed, failed = 0, []
    cases = golden.get("band_cases", [])
    runnable = 0
    for c in cases:
        band = c["expect_band"]
        case = {"id": c["id"], "input_code": c["input_code"], "gold_band": band}

        # oracle baseline: must score 1.0.
        runnable += 1
        oracle = spec.build_reference_decision(case)
        if spec.score_output(oracle, band)["score"] >= 1.0:
            passed += 1
        else:
            failed.append(f"band_case '{c['id']}': reference oracle did not land in band {band}")

        # saturation guard: empty emission must score 0.0.
        runnable += 1
        if spec.score_output({}, band)["score"] == 0.0:
            passed += 1
        else:
            failed.append(f"band_case '{c['id']}': empty emission scored > 0 (saturation guard breached)")

        # optional recorded live output.
        if outputs_dir is not None:
            raw = None
            for ext in (".json", ".txt", ""):
                p = outputs_dir / f"{c['id']}{ext}"
                if p.is_file():
                    raw = p.read_text(encoding="utf-8")
                    break
            if raw is not None:
                runnable += 1
                if spec.score_output(_extract(raw), band)["score"] >= 1.0:
                    passed += 1
                else:
                    failed.append(f"band_case '{c['id']}': recorded output not a valid in-band {band} emission")
    return passed, runnable, failed


def main(argv: list[str]) -> int:
    ap = argparse.ArgumentParser(description="Golden runner for code-review-system-design.")
    ap.add_argument("--outputs", type=Path, default=None, help="dir of recorded agent outputs")
    args = ap.parse_args(argv[1:])

    golden = json.loads(GOLDEN.read_text())
    s_pass, s_total, s_fail = run_schema_cases(golden)
    b_pass, b_total, b_fail = run_band_cases(golden, args.outputs)

    print(f"schema_cases: {s_pass}/{s_total} passed")
    print(f"band_cases:   {b_pass}/{b_total} passed (oracle + saturation"
          f"{' + recorded' if args.outputs else ''})")

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
