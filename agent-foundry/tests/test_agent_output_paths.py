#!/usr/bin/env python3
"""Regression test: api-tester executor output must land in the STANDARD path
results/runs/<RUN_ID>/api-tester-<agent>.cases.json — never a bespoke per-task bucket
(authz/clarity/crud/schema/status). Five contract modules used to hardcode those buckets,
which produced mislabeled top-level folders like results/authz/ instead of the agent name.

Gold: tests/agent_output_paths.gold.json
Run:  agent-foundry/.venv/bin/python agent-foundry/tests/test_agent_output_paths.py
      (or via pytest — the test_* functions are discoverable)
"""
from __future__ import annotations

import json
import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]            # MetaCTO-Assessment
WS = ROOT / "agent-foundry"
COMMON = WS / "agents" / "common"
RESULTS = WS / "results"
GOLD = json.loads((Path(__file__).resolve().parent / "agent_output_paths.gold.json").read_text())
BUCKETS = GOLD["forbidden_bucket_dirs"]


def _bucket_path_re(bucket: str) -> re.Pattern:
    # matches  "results" / "<bucket>" / "runs"   (the forbidden Path expression)
    return re.compile(r'"results"\s*/\s*"' + re.escape(bucket) + r'"\s*/\s*"runs"')


def test_contract_modules_use_standard_path():
    """No *_contract.py may build a results/<bucket>/runs path; each fixed module must use
    the standard results/runs path."""
    problems = []
    for mod in GOLD["agents_that_must_use_standard_path"]:
        src = (COMMON / mod).read_text()
        for b in BUCKETS:
            if _bucket_path_re(b).search(src):
                problems.append(f"{mod} still builds a 'results/{b}/runs' path")
        if 'WORKSPACE / "results" / "runs"' not in src:
            problems.append(f"{mod} does not use the standard 'results/runs' path")
    assert not problems, "FORBIDDEN bucket paths / missing standard path:\n  " + "\n  ".join(problems)


def test_no_common_module_references_a_bucket_path():
    """Belt-and-suspenders: NO module under agents/common may build any bucket path."""
    offenders = []
    for py in sorted(COMMON.glob("*.py")):
        src = py.read_text()
        for b in BUCKETS:
            if _bucket_path_re(b).search(src):
                offenders.append(f"{py.name}: results/{b}/runs")
    assert not offenders, "bucket paths found:\n  " + "\n  ".join(offenders)


def test_no_bucket_directories_under_results():
    """Runtime artifact check: no mislabeled bucket folders exist under results/."""
    if not RESULTS.is_dir():
        return
    present = [b for b in BUCKETS if (RESULTS / b).is_dir()]
    assert not present, f"bespoke bucket dirs present under results/: {present} (should be agent-named, in results/runs/)"


def main() -> int:
    tests = [test_contract_modules_use_standard_path,
             test_no_common_module_references_a_bucket_path,
             test_no_bucket_directories_under_results]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
