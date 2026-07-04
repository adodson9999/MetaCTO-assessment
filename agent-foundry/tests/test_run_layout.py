#!/usr/bin/env python3
"""Regression test for the clean per-run output layout (gold: run_layout.gold.json):

  results/<YYYY-MM-DD>/<HH-MM-SS>/
      TestCases/<agent>/{cases.json,cases.md}     (required, >=1 agent)
      BugReport/<agent>/{cases.json,cases.md}     (optional)
  ...and NOTHING else under results/ (no runs/, bug-reports/, flat agent folders, loose files).

Run:  agent-foundry/.venv/bin/python agent-foundry/tests/test_run_layout.py
      (also pytest-discoverable)
"""
from __future__ import annotations

import json
import re
import sys
import tempfile
from pathlib import Path

HERE = Path(__file__).resolve().parent
WS = HERE.parent                       # agent-foundry
RESULTS = WS / "results"
GOLD = json.loads((HERE / "run_layout.gold.json").read_text())
DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
TIME_RE = re.compile(GOLD["time_dir_regex"])
SECTIONS = ("TestCases", "BugReport")
FILES = set(GOLD["agent_dir_files"])
POSTMAN_FILES = set(GOLD.get("postman_files", ["collection.json", "environment.json"]))
IGNORE = set(GOLD["ignored"])
# The unverified-bug feature adds, under BugReport/, two run-level indexes and — per finding
# agent — verified_bugs/ + unverified_bugs/ subtrees (alongside or instead of cases.json/cases.md).
BUG_INDEXES = {"verified-index.json", "unverified-index.json"}
BUG_SUBDIRS = {"verified_bugs", "unverified_bugs"}


def validate(results: Path) -> list[str]:
    """Return a list of layout violations (empty = valid)."""
    bad = []
    if not results.is_dir():
        return ["results/ does not exist"]
    for top in results.iterdir():
        if top.name in IGNORE or "code-review" in top.name or top.name == "runs":  # subsystems / transient runs
            continue
        if not top.is_dir() or not DATE_RE.match(top.name):
            bad.append(f"forbidden top-level entry: {top.name} (only YYYY-MM-DD date dirs allowed)")
            continue
        for tdir in top.iterdir():
            if tdir.name in IGNORE:
                continue
            if not tdir.is_dir() or not TIME_RE.match(tdir.name):
                bad.append(f"{top.name}/{tdir.name}: not a HH-MM-SS time dir")
                continue
            present_sections = [s for s in SECTIONS if (tdir / s).is_dir()]
            if "TestCases" not in present_sections:
                bad.append(f"{top.name}/{tdir.name}: missing TestCases/")
            for entry in tdir.iterdir():
                if entry.name in IGNORE:
                    continue
                if entry.name == "Postman":
                    names = {f.name for f in entry.iterdir() if f.name not in IGNORE}
                    if names != POSTMAN_FILES:
                        bad.append(f"Postman/: files {sorted(names)} != {sorted(POSTMAN_FILES)}")
                    continue
                if entry.name not in SECTIONS:
                    bad.append(f"{top.name}/{tdir.name}/{entry.name}: not TestCases|BugReport|Postman")
                    continue
                for agent in entry.iterdir():
                    if agent.name in IGNORE:
                        continue
                    # the two run-level bug indexes live directly under BugReport/
                    if entry.name == "BugReport" and agent.is_file() and agent.name in BUG_INDEXES:
                        continue
                    if not agent.is_dir():
                        bad.append(f"{entry.name}/{agent.name}: loose file (must be <agent>/ dir)")
                        continue
                    names = {f.name for f in agent.iterdir() if f.name not in IGNORE}
                    if entry.name == "BugReport" and (names & BUG_SUBDIRS):
                        # a finding-agent dir may hold verified_bugs/ + unverified_bugs/ alone or
                        # alongside the cases.json/cases.md pair.
                        core = names - BUG_SUBDIRS
                        if not core.issubset(FILES):
                            bad.append(f"{entry.name}/{agent.name}: files {sorted(core)} "
                                       f"not a subset of {sorted(FILES)} (+ bug subdirs)")
                    elif names != FILES:
                        bad.append(f"{entry.name}/{agent.name}: files {sorted(names)} != {sorted(FILES)}")
    return bad


def test_validator_on_synthetic_layouts():
    """The validator itself: a correct layout passes; forbidden entries fail."""
    with tempfile.TemporaryDirectory() as td:
        r = Path(td) / "results"
        good = r / "2026-06-29" / "12-00-00"
        for sec in ("TestCases", "BugReport"):
            ad = good / sec / "verify-sorting-behavior"
            ad.mkdir(parents=True)
            (ad / "cases.json").write_text("[]")
            (ad / "cases.md").write_text("# x")
        assert validate(r) == [], f"correct layout should pass: {validate(r)}"
        # tolerated infra (must NOT be flagged): a shared runs/ dir and code-review artifacts
        (r / "runs").mkdir()
        (r / "code-review").mkdir()
        # genuinely forbidden: a flat agent folder at top level + an agent dir missing cases.md
        (r / "verify-sorting-behavior").mkdir()
        (good / "TestCases" / "bad-agent").mkdir()
        (good / "TestCases" / "bad-agent" / "cases.json").write_text("[]")  # missing cases.md
        v = validate(r)
        assert not any("runs" in x for x in v) and not any("code-review" in x for x in v), f"infra must be tolerated: {v}"
        assert any("verify-sorting-behavior" in x for x in v) and any("bad-agent" in x for x in v), v


def test_new_bug_tree_is_tolerated():
    """The unverified-bug tree (verified_bugs/ + unverified_bugs/{category}/ + the two indexes
    under BugReport/) must not be flagged as a layout violation."""
    with tempfile.TemporaryDirectory() as td:
        r = Path(td) / "results"
        run = r / "2026-07-01" / "12-00-00"
        # a normal TestCases agent
        tc = run / "TestCases" / "verify-sorting-behavior"
        tc.mkdir(parents=True)
        (tc / "cases.json").write_text("[]")
        (tc / "cases.md").write_text("# x")
        # BugReport with the new tree: a finding agent with both bug subtrees + the run indexes
        br = run / "BugReport"
        vb = br / "test-authentication-flows" / "verified_bugs"
        uv = br / "test-authentication-flows" / "unverified_bugs" / "vulnerability"
        vb.mkdir(parents=True)
        uv.mkdir(parents=True)
        (vb / "BUG-RUN-1-0001.json").write_text("{}")
        (uv / "VULN-RUN-1-0001.json").write_text("{}")
        (br / "verified-index.json").write_text("{}")
        (br / "unverified-index.json").write_text("{}")
        assert validate(r) == [], f"new bug tree should pass: {validate(r)}"

        # a genuinely broken agent dir under BugReport (unexpected loose file) is still flagged
        bad = br / "bad-agent"
        bad.mkdir()
        (bad / "notes.txt").write_text("x")
        assert any("bad-agent" in x for x in validate(r))


def test_current_results_layout():
    """If a run has produced output, results/ must match the clean layout exactly."""
    if not RESULTS.is_dir() or not any(p.is_dir() and DATE_RE.match(p.name) for p in RESULTS.iterdir()):
        print("  (no per-run output yet — skipping live check)")
        return
    bad = validate(RESULTS)
    assert not bad, "results/ layout violations:\n  " + "\n  ".join(bad)


def main() -> int:
    tests = [test_validator_on_synthetic_layouts, test_current_results_layout]
    failed = 0
    for t in tests:
        try:
            t(); print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
