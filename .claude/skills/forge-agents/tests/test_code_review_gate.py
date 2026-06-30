#!/usr/bin/env python3
"""Unit + golden tests for the code-review gate's deterministic core.

Install target: .claude/skills/forge-agents/tests/test_code_review_gate.py
(keep code_review_gate.py importable, e.g. via scripts/ on sys.path).

Pure Python, no model. Run with: pytest -q
"""
from __future__ import annotations

import json
import sys
from pathlib import Path

import pytest

# Make code_review_gate.py importable whether it sits in scripts/ or beside this file.
HERE = Path(__file__).resolve().parent
for cand in (HERE, HERE.parent / "scripts", HERE.parent):
    if (cand / "code_review_gate.py").is_file():
        sys.path.insert(0, str(cand))
        break

import code_review_gate as g  # noqa: E402

GOLDEN = next(
    (p for p in (HERE / "code-review-gate.golden.json",
                 HERE / "golden" / "code-review-gate.golden.json",
                 HERE.parent / "tests" / "golden" / "code-review-gate.golden.json")
     if p.is_file()),
    None,
)


# ---- trigger detection -------------------------------------------------------

@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "Build a QA automation agent that writes Playwright tests",
    "A software engineer agent that will implement functions",
    "The agent generates a Python script for the user",
    "refactor the module and emit code",
])
def test_code_producing_detected(text: str) -> None:
    assert g.is_code_producing(text) is True


@pytest.mark.unit
@pytest.mark.parametrize("text", [
    "Rate one bug report and emit a JSON verdict",
    "Summarize meeting notes into action items",
])
def test_non_code_producing(text: str) -> None:
    assert g.is_code_producing(text) is False


@pytest.mark.unit
def test_config_override_wins() -> None:
    assert g.is_code_producing("no code here", config_applies=True) is True
    assert g.is_code_producing("write a script", config_applies=False) is False


# ---- rating validation (schema gate) ----------------------------------------

@pytest.mark.unit
def test_valid_rating() -> None:
    assert g.validate_rating({"rating": 90, "notes": "ok"}) == 90
    assert g.validate_rating({"rating": 0, "notes": "x"}) == 0
    assert g.validate_rating({"rating": 100, "notes": "x"}) == 100


@pytest.mark.unit
@pytest.mark.parametrize("bad", [
    {"rating": 101, "notes": "x"},
    {"rating": -1, "notes": "x"},
    {"rating": 90.5, "notes": "x"},
    {"rating": "90", "notes": "x"},
    {"rating": True, "notes": "x"},
    {"rating": 90, "notes": ""},
    {"rating": 90},
    {"rating": 90, "notes": "x", "extra": 1},
    {"_raw": "not json"},
    [90, "x"],
])
def test_invalid_rating_is_none(bad: object) -> None:
    assert g.validate_rating(bad) is None


# ---- evaluate(): the core decision ------------------------------------------

def _all21(target: str, rating: int) -> list[g.Verdict]:
    return [g.Verdict(target, p, rating, "n") for p in g.REQUIRED_PERSPECTIVES]


@pytest.mark.unit
def test_pass_at_threshold_boundary() -> None:
    res = g.evaluate(["a.py"], _all21("a.py", 85), applies=True)
    assert res.status == "pass"
    assert res.min_rating == 85
    assert res.failures == []


@pytest.mark.unit
def test_one_below_threshold_fails() -> None:
    verdicts = _all21("a.py", 90)
    verdicts = [v for v in verdicts if v.perspective != "security"]
    verdicts.append(g.Verdict("a.py", "security", 84, "tighten input handling"))
    res = g.evaluate(["a.py"], verdicts, applies=True)
    assert res.status == "fail"
    assert any(f["perspective"] == "security" and f["rating"] == 84 for f in res.failures)


@pytest.mark.unit
def test_missing_perspective_fails_no_skip() -> None:
    verdicts = [v for v in _all21("a.py", 95) if v.perspective != "chaos-engineering"]
    res = g.evaluate(["a.py"], verdicts, applies=True)
    assert res.status == "fail"
    assert any(f["perspective"] == "chaos-engineering" and f["rating"] is None for f in res.failures)


@pytest.mark.unit
def test_missing_target_fails() -> None:
    res = g.evaluate(["a.py", "b.py"], _all21("a.py", 95), applies=True)
    assert res.status == "fail"
    assert any(f["target"] == "b.py" for f in res.failures)


@pytest.mark.unit
def test_applies_false_never_blocks() -> None:
    assert g.evaluate([], [], applies=False).status == "pass"


@pytest.mark.unit
def test_applies_true_no_targets_fails() -> None:
    assert g.evaluate([], [], applies=True).status == "fail"


@pytest.mark.unit
def test_raised_threshold_is_honored() -> None:
    res = g.evaluate(["a.py"], _all21("a.py", 90), applies=True, threshold=95)
    assert res.status == "fail"


# ---- dynamic discovery + no bypass ------------------------------------------

def _make_reviewers(root: Path, names: list[str]) -> None:
    for n in names:
        d = root / "agents" / "code-review" / n / "subagent"
        d.mkdir(parents=True)
        (d / f"code-review-{n}.md").write_text(f"---\nname: code-review-{n}\n---\nbody\n")


@pytest.mark.unit
def test_discover_perspectives_is_the_folder(tmp_path: Path) -> None:
    _make_reviewers(tmp_path, ["beta", "alpha", "gamma"])
    # a directory without the canonical prompt is not a reviewer
    (tmp_path / "agents" / "code-review" / "incomplete").mkdir(parents=True)
    assert g.discover_perspectives(tmp_path) == ["alpha", "beta", "gamma"]


@pytest.mark.unit
def test_discover_empty_folder(tmp_path: Path) -> None:
    assert g.discover_perspectives(tmp_path) == []


@pytest.mark.unit
def test_dynamic_set_of_any_size_passes() -> None:
    required = ("alpha", "beta", "gamma")
    verdicts = [g.Verdict("a.py", p, 90, "n") for p in required]
    assert g.evaluate(["a.py"], verdicts, applies=True, required=required).status == "pass"


@pytest.mark.unit
def test_dynamic_missing_one_fails_no_skip() -> None:
    required = ("alpha", "beta", "gamma")
    verdicts = [g.Verdict("a.py", p, 90, "n") for p in ("alpha", "beta")]  # gamma absent
    res = g.evaluate(["a.py"], verdicts, applies=True, required=required)
    assert res.status == "fail"
    assert any(f["perspective"] == "gamma" for f in res.failures)


@pytest.mark.unit
def test_empty_required_cannot_pass() -> None:
    # zero reviewers must never be a pass when the gate applies (no bypass)
    assert g.evaluate(["a.py"], [], applies=True, required=()).status == "fail"


@pytest.mark.unit
def test_added_reviewer_becomes_required() -> None:
    base = ("alpha", "beta", "gamma")
    verdicts = [g.Verdict("a.py", p, 95, "n") for p in base]
    assert g.evaluate(["a.py"], verdicts, applies=True, required=base).status == "pass"
    # add a 4th reviewer with no verdict -> automatically required -> fails
    assert g.evaluate(["a.py"], verdicts, applies=True, required=base + ("delta",)).status == "fail"


@pytest.mark.unit
def test_receipt_must_match_folder(tmp_path: Path) -> None:
    _make_reviewers(tmp_path, ["alpha", "beta"])
    assert g.receipt_matches_folder({"perspectives": ["alpha", "beta"]}, tmp_path) is True
    assert g.receipt_matches_folder({"perspectives": ["alpha"]}, tmp_path) is False            # stale/short
    assert g.receipt_matches_folder({"perspectives": ["alpha", "beta", "x"]}, tmp_path) is False


# ---- golden cases ------------------------------------------------------------

def _expand_matrix(case: dict, required: tuple[str, ...]) -> list[g.Verdict]:
    verdicts: list[g.Verdict] = []
    for target, persp, rating in case["matrix"]:
        if persp in ("all", "all21"):
            for p in required:
                verdicts = [v for v in verdicts if not (v.target == target and v.perspective == p)]
                verdicts.append(g.Verdict(target, p, rating, "n"))
        elif persp == "all-but-chaos":
            for p in required:
                if p != "chaos-engineering":
                    verdicts.append(g.Verdict(target, p, rating, "n"))
        else:
            # later explicit entries override the broad ones for the same pair
            verdicts = [v for v in verdicts if not (v.target == target and v.perspective == persp)]
            verdicts.append(g.Verdict(target, persp, rating, "n"))
    return verdicts


@pytest.mark.skipif(GOLDEN is None, reason="golden file not found")
def test_golden_cases() -> None:
    data = json.loads(GOLDEN.read_text())
    threshold = data.get("threshold", g.DEFAULT_THRESHOLD)
    failures = []
    for case in data["cases"]:
        required = tuple(case.get("perspectives", g.REQUIRED_PERSPECTIVES))
        verdicts = _expand_matrix(case, required)
        res = g.evaluate(case["targets"], verdicts, applies=case["applies"],
                         threshold=threshold, required=required)
        if res.status != case["expect_status"]:
            failures.append(f"{case['id']}: status {res.status} != {case['expect_status']}")
        if "expect_min" in case and res.min_rating != case["expect_min"]:
            failures.append(f"{case['id']}: min {res.min_rating} != {case['expect_min']}")
    assert not failures, "; ".join(failures)
