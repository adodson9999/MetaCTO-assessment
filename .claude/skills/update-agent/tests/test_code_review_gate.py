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


# =============================================================================
# update-agent additions: multi-agent fan-out + the no-bypass completion contract
# Appended for the code-review gate wiring; the tests above are unchanged.
# Each test below names, in its docstring, the contract it proves and why it would
# fail if the logic broke (no tautologies).
# =============================================================================

# Import the orchestrator (scripts/update_agent.py) for the contract + regression tests.
import update_agent as u  # noqa: E402  (scripts/ is already on sys.path via the loader above)


# ---- discovery returns EXACTLY the folder set -------------------------------

@pytest.mark.unit
def test_discovery_is_exactly_the_folder_set_ignoring_noise(tmp_path: Path) -> None:
    """Proves the required set == exactly the canonical reviewer dirs, no more/less.
    Fails if discovery counted a non-reviewer dir or a stray file as a reviewer."""
    _make_reviewers(tmp_path, ["delta", "alpha", "charlie"])
    (tmp_path / "agents" / "code-review" / "README.md").write_text("not a reviewer")
    (tmp_path / "agents" / "code-review" / "halfbuilt").mkdir()  # dir, no canonical prompt
    assert g.discover_perspectives(tmp_path) == ["alpha", "charlie", "delta"]


# ---- per-affected-agent: every reviewer >=85 regardless of count ------------

@pytest.mark.unit
@pytest.mark.parametrize("count", [1, 3, 7, 25])
def test_per_affected_every_reviewer_at_85_any_count_passes(count: int) -> None:
    """Two affected agents (a target each), an arbitrary reviewer count: pass needs
    every reviewer >=85 on BOTH. Fails if the gate ignored count or an affected agent."""
    required = tuple(f"r{i}" for i in range(count))
    targets = ["agentA/run.py", "agentB/run.py"]
    verdicts = [g.Verdict(t, p, 85, "n") for t in targets for p in required]
    assert g.evaluate(targets, verdicts, applies=True, required=required).status == "pass"


@pytest.mark.unit
@pytest.mark.parametrize("count", [3, 7, 25])
def test_per_affected_one_reviewer_below_on_one_agent_fails(count: int) -> None:
    """One reviewer at 84 on ONE of two affected agents fails the update, any count.
    Fails if the gate let a sub-85 score through or only checked one agent."""
    required = tuple(f"r{i}" for i in range(count))
    targets = ["agentA/run.py", "agentB/run.py"]
    verdicts = [g.Verdict(t, p, 90, "n") for t in targets for p in required]
    verdicts = [v for v in verdicts if not (v.target == "agentB/run.py" and v.perspective == "r1")]
    verdicts.append(g.Verdict("agentB/run.py", "r1", 84, "fix it"))
    res = g.evaluate(targets, verdicts, applies=True, required=required)
    assert res.status == "fail"
    assert any(f["target"] == "agentB/run.py" and f["perspective"] == "r1" for f in res.failures)


@pytest.mark.unit
def test_multi_agent_missing_verdict_for_one_agent_fails() -> None:
    """An affected agent that received no verdicts is a failure, not a skip.
    Fails if a target with zero verdicts were silently treated as passing."""
    required = ("alpha", "beta")
    res = g.evaluate(["agentA/run.py", "agentB/run.py"],
                     [g.Verdict("agentA/run.py", p, 95, "n") for p in required],
                     applies=True, required=required)
    assert res.status == "fail"
    assert any(f["target"] == "agentB/run.py" and f["rating"] is None for f in res.failures)


@pytest.mark.unit
def test_multi_agent_empty_reviewer_set_cannot_pass() -> None:
    """Even with code targets for multiple agents, an empty reviewer folder cannot pass.
    Fails if a zero-reviewer run were ever allowed to report pass (the core bypass)."""
    assert g.evaluate(["agentA/run.py", "agentB/run.py"], [], applies=True, required=()).status == "fail"


# ---- no-bypass completion contract (update_agent.code_review_contract_ok) ----

@pytest.mark.unit
def test_contract_missing_receipt_fails(tmp_path: Path) -> None:
    """The update cannot complete without a receipt (the gate must have run).
    Fails if a None receipt were accepted as ok."""
    ok, why = u.code_review_contract_ok(None, tmp_path)
    assert ok is False and "no code-review receipt" in why


@pytest.mark.unit
def test_contract_status_not_pass_fails(tmp_path: Path) -> None:
    """A receipt with status != pass blocks completion. Fails if status were ignored."""
    _make_reviewers(tmp_path, ["alpha", "beta"])
    receipt = {"applies": True, "status": "fail", "min_rating": 80, "perspectives": ["alpha", "beta"]}
    ok, _ = u.code_review_contract_ok(receipt, tmp_path)
    assert ok is False


@pytest.mark.unit
def test_contract_receipt_neq_folder_fails(tmp_path: Path) -> None:
    """A passing receipt whose reviewer set != the folder is rejected (stale/short).
    Fails if the no-bypass cross-check were skipped — the central bypass guard."""
    _make_reviewers(tmp_path, ["alpha", "beta", "gamma"])
    short = {"applies": True, "status": "pass", "perspectives": ["alpha", "beta"]}  # gamma omitted
    ok, why = u.code_review_contract_ok(short, tmp_path)
    assert ok is False and "!= agents/code-review/" in why


@pytest.mark.unit
def test_contract_pass_when_receipt_matches_and_passes(tmp_path: Path) -> None:
    """The contract passes only with status==pass AND reviewer set == folder.
    Fails if a correct receipt were wrongly rejected (would block valid updates)."""
    _make_reviewers(tmp_path, ["alpha", "beta"])
    good = {"applies": True, "status": "pass", "perspectives": ["alpha", "beta"]}
    ok, _ = u.code_review_contract_ok(good, tmp_path)
    assert ok is True


@pytest.mark.unit
def test_contract_does_not_apply_still_needs_receipt(tmp_path: Path) -> None:
    """A does-not-apply receipt passes but must still exist (receipt always required)."""
    assert u.code_review_contract_ok({"applies": False}, tmp_path)[0] is True
    assert u.code_review_contract_ok(None, tmp_path)[0] is False


# ---- the EXISTING regression gate still runs (additive, not replaced) --------

@pytest.mark.unit
def test_existing_regression_gate_still_runs() -> None:
    """The regression predicate is intact: below-baseline with no tradeoff regresses;
    at/above baseline, or an authorized tradeoff, does not. Fails if the regression
    gate were dropped or inverted when the code-review gate was added."""
    assert u.is_regression(0.80, 0.85, False) is True       # dropped, not authorized -> regression
    assert u.is_regression(0.80, 0.85, True) is False       # authorized tradeoff -> allowed
    assert u.is_regression(0.90, 0.85, False) is False      # improved -> no regression
    assert u.is_regression(0.85, 0.85, False) is False      # held the line -> no regression


@pytest.mark.unit
def test_affected_agents_fanout_dedup_primary_first() -> None:
    """Multi-agent fan-out enumerates every affected agent once, primary first.
    Fails if a duplicate ran twice or an affected agent were dropped."""
    assert u.affected_agents("g/primary", ["g/other", "g/primary", ""]) == ["g/primary", "g/other"]


# ---- self-awareness clause on a code-producing agent's prompt ----------------

@pytest.mark.unit
def test_self_aware_clause_required_for_code_producing_prompt(tmp_path: Path) -> None:
    """A code-producing agent's prompt must reference agents/code-review/ and the >=85
    rule. Fails if a prompt lacking the clause were accepted (self-awareness bypass)."""
    sub = tmp_path / "agents" / "g" / "n" / "subagent"
    sub.mkdir(parents=True)
    md = sub / "n.md"
    md.write_text("You are an agent. Emit code.\n")
    assert u.self_aware_ok(tmp_path, "g", "n")[0] is False
    md.write_text("You are an agent. ALL code you create is reviewed by every agent in "
                  "agents/code-review/ and must score >=85 on each, looping until it does.\n")
    assert u.self_aware_ok(tmp_path, "g", "n")[0] is True
