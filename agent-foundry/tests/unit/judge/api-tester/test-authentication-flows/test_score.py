#!/usr/bin/env python3
"""Unit tests for judge/api-tester/test-authentication-flows/score.py — the Auth-Flow
Fidelity judge metric.

Correctness of this metric is load-bearing: a wrong score silently corrupts the whole
tournament. These tests pin the EXACT numeric score for:
  * a perfect plan (all executed + all not_applicable matched -> 100.0);
  * partial plans (each dropped/wrong case lowers the score by exactly 100/denominator);
  * the None==None asymmetry fix (an unreported case must NOT count as a match);
  * symmetric gold/observed filtering ('none'/'_none_' rows excluded on both sides);
  * malformed / empty / non-JSON / non-object / non-list-cases input -> 0 matches, no crash;
  * path-traversal guards on run-id and raw_output_path (fail closed, never read outside ws);
  * atomic metric write-back and the deterministic leaderboard ordering.

Run: agent-foundry/.venv/bin/python \
     agent-foundry/tests/unit/judge/api-tester/test-authentication-flows/test_score.py
"""
from __future__ import annotations

import contextlib
import importlib.util
import json
import logging
import os
import re
import sys
import tempfile
import time
from pathlib import Path

# ---- import the module under test by path (its dir name is not a python package) ----
_HERE = Path(__file__).resolve()
WS = _HERE.parents[5]  # agent-foundry
_SCORE_PATH = WS / "judge" / "api-tester" / "test-authentication-flows" / "score.py"
_spec = importlib.util.spec_from_file_location("auth_flow_score", _SCORE_PATH)
assert _spec and _spec.loader
score = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(score)


# ---- fixtures --------------------------------------------------------------
# Mirror data/auth_gold.json: 5 executed cases + 5 not_applicable items -> denom 10.
_GOLD = {
    "summary": {
        "not_applicable": [
            {"item": "apiKey"}, {"item": "basic"}, {"item": "oauth2"},
            {"item": "apikey_wrong_location"}, {"item": "dedicated_revoke_endpoint"},
        ]
    },
    "cases": [
        {"scheme": "bearerJWT", "label": "valid", "actual_class": "2xx"},
        {"scheme": "bearerJWT", "label": "missing", "actual_class": "401"},
        {"scheme": "bearerJWT", "label": "malformed", "actual_class": "other_500"},
        {"scheme": "bearerJWT", "label": "expired", "actual_class": "401"},
        {"scheme": "bearerJWT", "label": "revoked", "actual_class": "2xx"},
    ],
}
_NA_ITEMS = ["apiKey", "basic", "oauth2", "apikey_wrong_location", "dedicated_revoke_endpoint"]


def _perfect_cases_doc() -> dict:
    return {
        "cases": [dict(c) for c in _GOLD["cases"]],
        "not_applicable_enumerated": [
            {"item": i, "status": "needs_to_be_built_and_tested"} for i in _NA_ITEMS
        ],
    }


def _exec_truth() -> tuple[dict, set]:
    """gold_truth() computed against an in-memory gold, via a temp workspace."""
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td)
        (ws / "data").mkdir()
        (ws / "data" / "auth_gold.json").write_text(json.dumps(_GOLD))
        return score.gold_truth(ws)


# ---- gold_truth / agent_observed extraction --------------------------------
def test_gold_truth_counts():
    exec_truth, na = _exec_truth()
    assert len(exec_truth) == 5
    assert len(na) == 5
    assert exec_truth[("bearerJWT", "valid")] == "2xx"


def test_gold_truth_missing_file_defaults_empty():
    with tempfile.TemporaryDirectory() as td:
        exec_truth, na = score.gold_truth(Path(td))  # no data/auth_gold.json
        assert exec_truth == {} and na == set()


def test_agent_observed_extracts_keys_and_na():
    obs, na = score.agent_observed(_perfect_cases_doc())
    assert len(obs) == 5 and len(na) == 5
    assert obs[("bearerJWT", "revoked")] == "2xx"


def test_agent_observed_filters_none_and_placeholder_rows():
    doc = {"cases": [
        {"scheme": "s", "label": "_none_", "actual_class": "2xx"},   # placeholder label
        {"scheme": "s", "label": "x", "actual_class": "none"},        # non-observed class
        {"scheme": "s", "label": "y", "actual_class": None},          # missing class
        {"scheme": "s", "label": "keep", "actual_class": "401"},      # the only real row
    ]}
    obs, _ = score.agent_observed(doc)
    assert obs == {("s", "keep"): "401"}


# ---- exact scores ----------------------------------------------------------
def test_perfect_plan_scores_100():
    exec_truth, na = _exec_truth()
    fidelity, matches, em, nm = score._score_one(exec_truth, na, _perfect_cases_doc())
    assert (fidelity, matches, em, nm) == (100.0, 10, 5, 5)


def test_each_missing_executed_case_lowers_by_10():
    exec_truth, na = _exec_truth()
    doc = _perfect_cases_doc()
    doc["cases"] = doc["cases"][:-1]  # drop one executed case -> 9/10
    fidelity, matches, em, nm = score._score_one(exec_truth, na, doc)
    assert (fidelity, matches, em, nm) == (90.0, 9, 4, 5)


def test_each_missing_na_item_lowers_by_10():
    exec_truth, na = _exec_truth()
    doc = _perfect_cases_doc()
    doc["not_applicable_enumerated"] = doc["not_applicable_enumerated"][:-2]  # 3/5 na -> 8/10
    fidelity, matches, em, nm = score._score_one(exec_truth, na, doc)
    assert (fidelity, matches, em, nm) == (80.0, 8, 5, 3)


def test_wrong_actual_class_is_not_a_match():
    exec_truth, na = _exec_truth()
    doc = _perfect_cases_doc()
    doc["cases"][0]["actual_class"] = "WRONG"  # valid case now mismatches -> 9/10
    fidelity, matches, em, _ = score._score_one(exec_truth, na, doc)
    assert (fidelity, matches, em) == (90.0, 9, 4)


def test_empty_plan_scores_zero_not_crash():
    exec_truth, na = _exec_truth()
    for doc in ({}, {"cases": []}, {"cases": [], "not_applicable_enumerated": []}):
        fidelity, matches, em, nm = score._score_one(exec_truth, na, doc)
        assert (fidelity, matches, em, nm) == (0.0, 0, 0, 0)


def test_none_actual_class_does_not_false_match():
    # math-correctness fix: an agent that never reports a case (absent key) must NOT
    # match a gold value — the None==None trap. Here obs is empty; gold has 5 exec.
    exec_truth, na = _exec_truth()
    # Agent reported nothing: no exec matches AND (nothing enumerated) no na matches.
    fidelity, matches, em, nm = score._score_one(exec_truth, na, {"cases": []})
    assert (fidelity, matches, em, nm) == (0.0, 0, 0, 0)


def test_na_only_plan_partial_score():
    exec_truth, na = _exec_truth()
    doc = {"not_applicable_enumerated": [
        {"item": i, "status": "needs_to_be_built_and_tested"} for i in _NA_ITEMS
    ]}
    fidelity, matches, em, nm = score._score_one(exec_truth, na, doc)
    assert (fidelity, matches, em, nm) == (50.0, 5, 0, 5)  # 5 na / 10


def test_na_wrong_status_not_counted():
    exec_truth, na = _exec_truth()
    doc = {"not_applicable_enumerated": [
        {"item": i, "status": "done"} for i in _NA_ITEMS  # wrong status
    ]}
    _, matches, _, nm = score._score_one(exec_truth, na, doc)
    assert (matches, nm) == (0, 0)


def test_zero_denominator_scores_zero():
    fidelity, matches, em, nm = score._score_one({}, set(), _perfect_cases_doc())
    assert (fidelity, matches, em, nm) == (0.0, 0, 0, 0)


# ---- adversarial / malformed input -----------------------------------------
def test_non_dict_document_scores_zero():
    exec_truth, na = _exec_truth()
    for bad in ("not a dict", 123, None, [1, 2, 3]):
        fidelity, matches, _, _ = score._score_one(exec_truth, na, bad)
        assert (fidelity, matches) == (0.0, 0)


def test_cases_as_string_does_not_crash():
    # {"cases": "not a list"} would iterate chars in the old code and crash.
    exec_truth, na = _exec_truth()
    fidelity, matches, _, _ = score._score_one(exec_truth, na, {"cases": "xxxx"})
    assert (fidelity, matches) == (0.0, 0)


def test_non_dict_case_rows_are_dropped():
    exec_truth, na = _exec_truth()
    doc = {"cases": [123, "str", None, {"scheme": "bearerJWT", "label": "valid", "actual_class": "2xx"}]}
    fidelity, matches, em, _ = score._score_one(exec_truth, na, doc)
    assert (em, matches) == (1, 1)


def test_load_non_json_returns_default():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "bad.json"
        p.write_text("{not valid json,,,")
        assert score._load(p, {"cases": []}) == {"cases": []}


def test_load_missing_file_returns_default():
    with tempfile.TemporaryDirectory() as td:
        assert score._load(Path(td) / "nope.json", "DEFAULT") == "DEFAULT"


def test_load_oversize_file_refused():
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "big.json"
        p.write_text("{}")
        orig = score._MAX_JSON_BYTES
        score._MAX_JSON_BYTES = 1  # force the size cap to trip
        try:
            assert score._load(p, "CAPPED") == "CAPPED"
        finally:
            score._MAX_JSON_BYTES = orig


# ---- path-traversal / security guards --------------------------------------
def test_validate_run_id_rejects_traversal():
    for bad in ("..", ".", "../../etc", "a/b", "a/../b", "", "x\x00y", "/abs"):
        try:
            score._validate_run_id(bad)
            assert False, f"expected ValueError for {bad!r}"
        except ValueError:
            pass


def test_validate_run_id_accepts_plain_segment():
    for ok in ("ac-claude-1782786985", "adv-tourney-r00-cb1a4f", "run_1.2"):
        assert score._validate_run_id(ok) == ok


def test_confined_path_refuses_outside_workspace():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        assert score._confined_cases_path("/etc/passwd", ws) is None
        assert score._confined_cases_path(str(ws / ".." / "escape.json"), ws) is None
        assert score._confined_cases_path("", ws) is None
        assert score._confined_cases_path(None, ws) is None


def test_confined_path_accepts_inside_workspace():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        inside = ws / "results" / "x.cases.json"
        assert score._confined_cases_path(str(inside), ws) == inside


# ---- write-back + main() end to end ----------------------------------------
def _make_run(ws: Path, run_id: str, doc: dict) -> Path:
    (ws / "data").mkdir(parents=True, exist_ok=True)
    (ws / "data" / "auth_gold.json").write_text(json.dumps(_GOLD))
    run_dir = ws / "results" / "runs" / run_id
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / "agentA.cases.json"
    cases_path.write_text(json.dumps(doc))
    meta = {"agent": "agentA", "raw_output_path": str(cases_path)}
    meta_path = run_dir / "agentA.json"
    meta_path.write_text(json.dumps(meta))
    return meta_path


def test_main_writes_metric_atomically():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        meta_path = _make_run(ws, "run1", _perfect_cases_doc())
        sys.argv = ["score.py", "--workspace", str(ws), "--run-id", "run1"]
        assert score.main() == 0
        written = json.loads(meta_path.read_text())
        assert written["metric_name"] == "auth_flow_fidelity"
        assert written["metric_value"] == 100.0
        assert written["fidelity_denominator"] == 10
        assert written["fidelity_matches"] == 10
        assert written["agent"] == "agentA"  # original field preserved


def test_main_partial_plan_exact_metric():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        doc = _perfect_cases_doc()
        doc["cases"] = doc["cases"][:3]  # 3 exec + 5 na = 8/10
        meta_path = _make_run(ws, "run2", doc)
        sys.argv = ["score.py", "--workspace", str(ws), "--run-id", "run2"]
        assert score.main() == 0
        assert json.loads(meta_path.read_text())["metric_value"] == 80.0


def test_main_no_results_returns_1():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        (ws / "data").mkdir()
        (ws / "data" / "auth_gold.json").write_text(json.dumps(_GOLD))
        (ws / "results" / "runs" / "empty").mkdir(parents=True)
        sys.argv = ["score.py", "--workspace", str(ws), "--run-id", "empty"]
        assert score.main() == 1


def test_main_rejects_bad_run_id():
    with tempfile.TemporaryDirectory() as td:
        sys.argv = ["score.py", "--workspace", td, "--run-id", "../../etc"]
        assert score.main() == 2  # fail closed, no filesystem escape


def test_main_ignores_cases_json_files():
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        _make_run(ws, "run3", _perfect_cases_doc())
        sys.argv = ["score.py", "--workspace", str(ws), "--run-id", "run3"]
        # only agentA.json is a result; agentA.cases.json must be skipped -> exactly 1 row, rc 0
        assert score.main() == 0


def test_result_files_excludes_cases_and_sorts():
    with tempfile.TemporaryDirectory() as td:
        run_dir = Path(td)
        for n in ("b.json", "a.json", "a.cases.json", "notes.txt"):
            (run_dir / n).write_text("{}")
        got = [p.name for p in score._result_files(run_dir)]
        assert got == ["a.json", "b.json"]  # sorted, no .cases.json, no .txt


# ---- round-2 hardening: adversarial recursion, determinism, locking, resilience ----
def test_load_deeply_nested_json_does_not_crash():
    # adversarial-input: json.loads raises RecursionError on ~thousands of nested braces.
    # _load must swallow it and return the default, not let it bubble up and kill the judge.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "nested.json"
        depth = 20000
        p.write_text("[" * depth + "]" * depth)  # legal JSON, but far past the recursion limit
        assert score._load(p, {"cases": []}) == {"cases": []}


def test_score_one_survives_deeply_nested_cases_doc():
    # End-to-end: even if a nested structure somehow reaches _score_one, it degrades to 0.
    exec_truth, na = _exec_truth()
    deep: object = "leaf"
    for _ in range(2000):
        deep = {"n": deep}
    fidelity, matches, _, _ = score._score_one(exec_truth, na, deep)
    assert (fidelity, matches) == (0.0, 0)


def test_confined_path_relative_anchored_to_workspace_not_cwd():
    # data-integrity/determinism: a RELATIVE raw_output_path must resolve against the
    # workspace, identically regardless of the process CWD.
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        (ws / "results").mkdir()
        target = ws / "results" / "x.cases.json"
        rel = "results/x.cases.json"
        expected = target.resolve()
        cwd = os.getcwd()
        try:
            os.chdir("/")               # a CWD unrelated to the workspace
            got_root = score._confined_cases_path(rel, ws)
            os.chdir(td)                # a different CWD
            got_td = score._confined_cases_path(rel, ws)
        finally:
            os.chdir(cwd)
        assert got_root == expected and got_td == expected  # CWD does not change the result


def test_confined_path_relative_traversal_still_refused():
    # The relative-anchor change must not weaken the traversal guard.
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        assert score._confined_cases_path("../../../etc/passwd", ws) is None


def test_result_lock_is_reentrant_across_sequential_calls():
    # Sequential locks on the same file must each acquire and release cleanly (no deadlock,
    # no leaked lock file). The O_EXCL lock is cross-platform, so each acquire is genuine.
    with tempfile.TemporaryDirectory() as td:
        jf = Path(td) / "a.json"
        jf.write_text("{}")
        lock_path = jf.with_name(f"{jf.name}.lock")
        for _ in range(3):
            with score._result_lock(jf) as held:
                assert held is True                    # uncontended -> genuinely acquired
            assert not lock_path.exists()              # released + removed each time
        assert score._atomic_write_json(jf, {"k": 1}) is True


def test_process_file_drops_row_when_write_fails(monkeypatch=None):
    # error-handling-resilience: if the metric cannot be persisted, the row is dropped so
    # the leaderboard never reports a score that was not written to disk.
    exec_truth, na = _exec_truth()
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        run_dir = ws / "results" / "runs" / "r"
        run_dir.mkdir(parents=True)
        cases = run_dir / "agentA.cases.json"
        cases.write_text(json.dumps(_perfect_cases_doc()))
        jf = run_dir / "agentA.json"
        jf.write_text(json.dumps({"agent": "agentA", "raw_output_path": str(cases)}))
        orig = score._atomic_write_json
        score._atomic_write_json = lambda *a, **k: False  # simulate a write failure
        try:
            row = score._process_file(jf, exec_truth, na, ws)
        finally:
            score._atomic_write_json = orig
        assert row is None  # dropped, not reported


def test_atomic_write_failure_returns_false_no_crash():
    # A write to a path whose parent does not exist must fail closed (False), never raise.
    with tempfile.TemporaryDirectory() as td:
        bad = Path(td) / "missing_dir" / "x.json"
        assert score._atomic_write_json(bad, {"k": 1}) is False


def test_result_files_missing_dir_returns_empty():
    # device-stack: a non-existent run dir yields [] (logged), never a crash.
    with tempfile.TemporaryDirectory() as td:
        assert score._result_files(Path(td) / "nope") == []


def test_gold_missing_scores_all_zero_no_crash():
    # observability path: absent gold -> denom 0 -> every agent 0%, but the run still
    # completes (rc 0 with a result present) rather than crashing.
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        run_dir = ws / "results" / "runs" / "r"
        run_dir.mkdir(parents=True)
        cases = run_dir / "agentA.cases.json"
        cases.write_text(json.dumps(_perfect_cases_doc()))
        jf = run_dir / "agentA.json"
        jf.write_text(json.dumps({"agent": "agentA", "raw_output_path": str(cases)}))
        # NO data/auth_gold.json written
        sys.argv = ["score.py", "--workspace", str(ws), "--run-id", "r"]
        assert score.main() == 0
        written = json.loads(jf.read_text())
        assert written["metric_value"] == 0.0 and written["fidelity_denominator"] == 0


def test_observed_cases_shared_filter_dry():
    # maintainability: gold_truth and agent_observed must produce identical exec maps for
    # the same rows (they share _observed_cases). Prove the single filter is the one used.
    doc = {"cases": [
        {"scheme": "bearerJWT", "label": "valid", "actual_class": "2xx"},
        {"scheme": "bearerJWT", "label": "revoked", "actual_class": "none"},  # filtered
    ]}
    from_helper = score._observed_cases(doc)
    from_agent, _ = score.agent_observed(doc)
    assert from_helper == from_agent == {("bearerJWT", "valid"): "2xx"}


def test_main_determinism_from_two_cwds():
    # data-integrity: full main() run must produce the identical metric regardless of CWD,
    # using a RELATIVE raw_output_path so the anchor-to-workspace fix is exercised end-to-end.
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        (ws / "data").mkdir()
        (ws / "data" / "auth_gold.json").write_text(json.dumps(_GOLD))
        run_dir = ws / "results" / "runs" / "r"
        run_dir.mkdir(parents=True)
        cases = run_dir / "agentA.cases.json"
        cases.write_text(json.dumps(_perfect_cases_doc()))
        jf = run_dir / "agentA.json"
        # relative path, resolved against the workspace not the CWD:
        jf.write_text(json.dumps({"agent": "agentA",
                                  "raw_output_path": "results/runs/r/agentA.cases.json"}))
        cwd = os.getcwd()
        results = []
        try:
            for at in ("/", td):
                os.chdir(at)
                sys.argv = ["score.py", "--workspace", str(ws), "--run-id", "r"]
                assert score.main() == 0
                results.append(json.loads(jf.read_text())["metric_value"])
        finally:
            os.chdir(cwd)
        assert results == [100.0, 100.0]  # identical, deterministic across CWDs


# ---- round-3: named row, bounded lock, empty-cases observability -----------
class _CaptureHandler(logging.Handler):
    """Collect emitted records so a test can assert a specific log was produced."""
    def __init__(self) -> None:
        super().__init__()
        self.records: list[logging.LogRecord] = []

    def emit(self, record: logging.LogRecord) -> None:
        self.records.append(record)


def _capture_logs():
    handler = _CaptureHandler()
    score.log.addHandler(handler)
    prev = score.log.level
    score.log.setLevel(logging.DEBUG)
    return handler, prev


def _restore_logs(handler, prev) -> None:
    score.log.removeHandler(handler)
    score.log.setLevel(prev)


def test_row_is_named_and_report_orders_by_named_fields():
    # maintainability: _process_file returns a _Row read by name; the report sorts by
    # fidelity desc then agent. Build rows directly and confirm both.
    rows = [
        score._Row("z-agent", 50.0, 0, 5, 5, 5, None, None),
        score._Row("a-agent", 100.0, 5, 5, 5, 5, 60.0, 0.0),
        score._Row("m-agent", 100.0, 5, 5, 5, 5, None, None),
    ]
    ordered = sorted(rows, key=lambda r: (-r.fidelity, r.agent))
    assert [r.agent for r in ordered] == ["a-agent", "m-agent", "z-agent"]
    assert ordered[0].fidelity == 100.0 and ordered[0].pass_rate == 60.0
    # NamedTuple stays a tuple (backward-compatible positional access):
    assert tuple(ordered[0])[:2] == ("a-agent", 100.0)


def test_process_file_returns_named_row():
    exec_truth, na = _exec_truth()
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        run_dir = ws / "results" / "runs" / "r"
        run_dir.mkdir(parents=True)
        cases = run_dir / "agentA.cases.json"
        cases.write_text(json.dumps(_perfect_cases_doc()))
        jf = run_dir / "agentA.json"
        jf.write_text(json.dumps({"agent": "agentA", "raw_output_path": str(cases)}))
        row = score._process_file(jf, exec_truth, na, ws)
        assert isinstance(row, score._Row)
        assert row.agent == "agentA" and row.fidelity == 100.0
        assert row.exec_matches == 5 and row.na_total == 5


def test_lock_bounded_wait_does_not_hang_when_held():
    # device-stack: if the lock file already exists (holder backgrounded/stopped), a waiter
    # must NOT block forever — the bounded O_EXCL poll returns False within the budget.
    with tempfile.TemporaryDirectory() as td:
        jf = Path(td) / "a.json"
        jf.write_text("{}")
        lock_path = jf.with_name(f"{jf.name}.lock")
        holder = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)  # simulate a stuck holder
        orig_wait = score._LOCK_WAIT_S
        score._LOCK_WAIT_S = 0.2  # shrink the budget so the test is fast
        try:
            start = time.monotonic()
            with score._result_lock(jf) as held:
                elapsed = time.monotonic() - start
                assert held is False          # could not acquire (lock file present)
                assert elapsed < 5.0          # returned promptly, did not hang
        finally:
            score._LOCK_WAIT_S = orig_wait
            os.close(holder)
            with contextlib.suppress(OSError):
                lock_path.unlink()


def test_lock_acquires_when_free():
    with tempfile.TemporaryDirectory() as td:
        jf = Path(td) / "a.json"
        jf.write_text("{}")
        with score._result_lock(jf) as held:
            assert held is True  # uncontended -> genuinely acquired
        assert not jf.with_name(f"{jf.name}.lock").exists()  # released + removed


def test_lock_timeout_logs_lost_write_warning():
    # observability: when the bounded wait elapses, a distinct lock-timeout event naming the
    # risk (a concurrent write may be lost) must be emitted — not silent best-effort.
    with tempfile.TemporaryDirectory() as td:
        jf = Path(td) / "a.json"
        jf.write_text("{}")
        lock_path = jf.with_name(f"{jf.name}.lock")
        holder = os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        orig_wait = score._LOCK_WAIT_S
        score._LOCK_WAIT_S = 0.1
        handler, prev = _capture_logs()
        try:
            with score._result_lock(jf) as held:
                assert held is False
        finally:
            _restore_logs(handler, prev)
            score._LOCK_WAIT_S = orig_wait
            os.close(holder)
            with contextlib.suppress(OSError):
                lock_path.unlink()
        msgs = [r.getMessage() for r in handler.records]
        assert any("lock-timeout" in m and "may be lost" in m for m in msgs), msgs


def test_lock_serialises_read_modify_write_cross_platform():
    # data-integrity (the stuck lens): the lock must actually serialise. While one holder
    # is inside the lock, a second _result_lock on the SAME file must NOT also acquire —
    # this is the mutual exclusion that prevents the lost update, on every platform.
    with tempfile.TemporaryDirectory() as td:
        jf = Path(td) / "a.json"
        jf.write_text("{}")
        orig_wait = score._LOCK_WAIT_S
        score._LOCK_WAIT_S = 0.1
        try:
            with score._result_lock(jf) as first_held:
                assert first_held is True
                with score._result_lock(jf) as second_held:
                    assert second_held is False   # blocked while the first holds it
            # once released, a fresh acquire succeeds again
            with score._result_lock(jf) as third_held:
                assert third_held is True
        finally:
            score._LOCK_WAIT_S = orig_wait


def test_missing_raw_output_path_is_logged():
    # observability: when _confined_cases_path returns None, the empty-cases fallback
    # must be logged (WARNING) naming the agent, not silently score 0%.
    exec_truth, na = _exec_truth()
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        run_dir = ws / "results" / "runs" / "r"
        run_dir.mkdir(parents=True)
        jf = run_dir / "agentA.json"
        jf.write_text(json.dumps({"agent": "agentA", "raw_output_path": "/etc/escape.json"}))
        handler, prev = _capture_logs()
        try:
            row = score._process_file(jf, exec_truth, na, ws)
        finally:
            _restore_logs(handler, prev)
        msgs = [r.getMessage() for r in handler.records]
        assert any("no usable raw_output_path" in m and "agentA" in m for m in msgs), msgs
        assert row is not None and row.exec_matches == 0  # scored against empty cases


# ---- round-4: OOM resilience in _load, and the returning-list helper ---------
def test_load_degrades_on_memoryerror_reading():
    # device-stack: read_text() can hit MemoryError on a constrained host even under the
    # byte cap. _load must degrade to the default, never propagate MemoryError.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ok.json"
        p.write_text("{}")
        orig = Path.read_text
        Path.read_text = lambda self, *a, **k: (_ for _ in ()).throw(MemoryError("oom"))
        try:
            assert score._load(p, {"cases": []}) == {"cases": []}
        finally:
            Path.read_text = orig


def test_load_degrades_on_memoryerror_parsing():
    # device-stack: json.loads() can hit MemoryError building the object tree for a
    # large-but-under-cap document. _load must degrade, not crash.
    with tempfile.TemporaryDirectory() as td:
        p = Path(td) / "ok.json"
        p.write_text('{"cases": []}')
        orig = score.json.loads
        score.json.loads = lambda *a, **k: (_ for _ in ()).throw(MemoryError("oom"))
        try:
            assert score._load(p, "DEFAULT") == "DEFAULT"
        finally:
            score.json.loads = orig


def test_dict_rows_returns_list_not_iterator():
    # maintainability: the helper is named for what it returns — a concrete list of dict
    # rows — and drops non-dict rows. Old _iter_ name must be gone.
    assert not hasattr(score, "_iter_cases")
    rows = score._dict_rows({"cases": [{"a": 1}, 7, "x", None, {"b": 2}]}, "cases")
    assert isinstance(rows, list)              # a materialised list, not a generator
    assert rows == [{"a": 1}, {"b": 2}]        # non-dict rows dropped
    assert score._dict_rows("not-a-dict", "cases") == []
    assert score._dict_rows({"cases": "str"}, "cases") == []


# ---- round-5: correlation id threaded into every log, cross-platform lock -----
def test_explicit_correlation_id_stamped_on_every_log():
    # observability: --correlation-id must appear on EVERY log line of the run so all
    # agents/judges in one tournament run are greppable together.
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        (ws / "data").mkdir()
        (ws / "data" / "auth_gold.json").write_text(json.dumps(_GOLD))
        run_dir = ws / "results" / "runs" / "r"
        run_dir.mkdir(parents=True)
        cases = run_dir / "agentA.cases.json"
        cases.write_text(json.dumps(_perfect_cases_doc()))
        jf = run_dir / "agentA.json"
        jf.write_text(json.dumps({"agent": "agentA", "raw_output_path": str(cases)}))
        handler, prev = _capture_logs()
        try:
            sys.argv = ["score.py", "--workspace", str(ws), "--run-id", "r",
                        "--correlation-id", "corr-XYZ-123"]
            assert score.main() == 0
        finally:
            _restore_logs(handler, prev)
        msgs = [r.getMessage() for r in handler.records]
        assert msgs, "expected log output"
        assert all(m.startswith("[cid=corr-XYZ-123]") for m in msgs), msgs
        # the entry log ties the run together:
        assert any("auth-flow judge starting" in m for m in msgs)


def test_default_correlation_id_is_uuid4():
    # observability: with no --correlation-id, a fresh UUIDv4 is generated and stamped.
    with tempfile.TemporaryDirectory() as td:
        ws = Path(td).resolve()
        (ws / "data").mkdir()
        (ws / "data" / "auth_gold.json").write_text(json.dumps(_GOLD))
        (ws / "results" / "runs" / "r").mkdir(parents=True)  # no result files -> rc 1
        handler, prev = _capture_logs()
        try:
            sys.argv = ["score.py", "--workspace", str(ws), "--run-id", "r"]
            assert score.main() == 1
        finally:
            _restore_logs(handler, prev)
        cids = {m[len("[cid="):m.index("]")] for m in (r.getMessage() for r in handler.records)
                if m.startswith("[cid=")}
        assert len(cids) == 1, cids  # one id for the whole run
        cid = cids.pop()
        assert cid != "-"
        uuid4_re = re.compile(r"^[0-9a-f]{8}-[0-9a-f]{4}-4[0-9a-f]{3}-[89ab][0-9a-f]{3}-[0-9a-f]{12}$")
        assert uuid4_re.match(cid), cid  # a real UUIDv4


def test_correlation_filter_does_not_break_message_args():
    # The filter must PREPEND only — a log call with %-args must still format correctly
    # (regression guard: naive re-formatting would consume the message's own placeholders).
    handler, prev = _capture_logs()
    score._CORRELATION_ID.set("cid-1")
    try:
        score.log.info("scored agent=%s fidelity=%.2f", "agentX", 87.5)
    finally:
        _restore_logs(handler, prev)
    msgs = [r.getMessage() for r in handler.records]
    assert msgs == ["[cid=cid-1] scored agent=agentX fidelity=87.50"], msgs


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001 - report any unexpected error as a failure
            failed += 1
            print(f"ERROR {t.__name__}: {e.__class__.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
