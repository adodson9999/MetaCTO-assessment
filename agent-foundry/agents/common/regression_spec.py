"""Canonical structure for the API "Run Regression Suite" task.

ONE definition of the regression comparison + the per-field evaluation, shared by:
  - the deterministic gold reference (data/run-regression-suite/build_gold.py), and
  - the harness (agents/common/regression.py) — which scores whatever regression
    report an agent emitted on exactly the same field scheme.

Pure: no env, no I/O, no LLM, no HTTP. Keeps agent output and the gold report on the
same (build_pair x field) key scheme so the judge can compare them field-for-field.

Why fixtures (Phase-2 fork). DummyJSON exposes no CI build-result-artifact surface
and must not be modified, so the "test result artifacts" for build N-1 and build N
are local, air-gapped fixtures under data/run-regression-suite/builds/<pair>/ in the
three reporter formats the task names: Postman/Newman JUnit XML, pytest JUnit XML,
and Jest --json (plus pytest-json-report). The "deploy build N + GET /health == 200"
step is honored separately by the harness pinging the live local DummyJSON /health
read-only. This mirrors the track-defect-density / validate-search-and-filter
precedent: a report-from-fixtures task with a deterministic gold reference, DummyJSON
left 100% untouched.

The regression contract (the exact algorithm the agent must reproduce):
  PREV_PASSED_IDS = the test IDs whose status in the build N-1 artifact is "passed".
  A REGRESSION    = a test ID in PREV_PASSED_IDS whose status in the build N artifact
                    is exactly "failed". (A prev-passed test that is ABSENT in build N,
                    or skipped, or still passing, is NOT a regression.)
  newly_passing   = test IDs whose status was "failed" in N-1 and "passed" in N.
  Already-failing tests (failed in both N-1 and N) are NOT regressions.

The emitted regression report has EXACTLY these seven fields (task-mandated names):
  build_n_nus_1, build_n, total_tests_in_suite, prev_passed_count,
  regressions (list of {id, failure_message}), newly_passing (list of id),
  overall_status ("fail" iff any regression, else "pass").

Metric — Regression Rate = len(regressions) / prev_passed_count * 100. Pass = exactly
0 (zero regressions blocks nothing); Fail = any value > 0 (a single regression blocks
deployment, no tolerance). The forge judge ranks the four frameworks on
Regression-Report Fidelity (the fraction of build_pair x field cells matching gold)
because the headline Regression Rate is a property of the fixtures, not the framework.
"""
from __future__ import annotations

import json
import xml.etree.ElementTree as ET

# The build-pair catalogue: each is one (build N-1, build N) result-artifact pair in a
# named reporter format. This is the static truth; build_gold.py writes it to
# regression_spec.json (the agents' briefing input) and derives the gold reports.
BUILD_PAIRS = [
    {"pair": "newman_junit", "format": "junit_xml",
     "prev_build_id": "ci-1042", "build_id": "ci-1043",
     "prev_file": "build_prev.xml", "curr_file": "build_curr.xml",
     "note": "Postman/Newman JUnit reporter output."},
    {"pair": "pytest_junit", "format": "junit_xml",
     "prev_build_id": "build-77", "build_id": "build-78",
     "prev_file": "build_prev.xml", "curr_file": "build_curr.xml",
     "note": "pytest --junitxml output (clean build: zero regressions)."},
    {"pair": "jest_json", "format": "jest_json",
     "prev_build_id": "gh-2001", "build_id": "gh-2002",
     "prev_file": "build_prev.json", "curr_file": "build_curr.json",
     "note": "Jest --json reporter output."},
    {"pair": "pytest_json", "format": "pytest_json",
     "prev_build_id": "rel-9", "build_id": "rel-10",
     "prev_file": "build_prev.json", "curr_file": "build_curr.json",
     "note": "pytest-json-report output (a prev-passed test is removed in build N)."},
]

# The seven exact output fields, in order. Each is one scored cell per build-pair.
REPORT_FIELDS = [
    "build_n_nus_1",
    "build_n",
    "total_tests_in_suite",
    "prev_passed_count",
    "regressions",
    "newly_passing",
    "overall_status",
]

# Status normalization across the three reporter vocabularies.
_PASSED = {"passed", "pass", "success", "successful", "ok"}
_FAILED = {"failed", "failure", "error", "broken"}
_SKIPPED = {"skipped", "pending", "todo", "disabled", "ignored", "xfailed"}


def normalize_status(raw: str) -> str:
    """Map a reporter's status token to one of: passed | failed | skipped | other."""
    t = (raw or "").strip().lower()
    if t in _PASSED:
        return "passed"
    if t in _FAILED:
        return "failed"
    if t in _SKIPPED:
        return "skipped"
    return "other"


# --------------------------------------------------------------------------- #
# Parsers — text artifact -> {test_id: {"status": <norm>, "message": str|None}}
# --------------------------------------------------------------------------- #
def _strip_xml_comments(text: str) -> str:
    """Remove <!-- ... --> comments. Real reporter output occasionally embeds an
    illegal '--' inside a comment (e.g. 'pytest --junitxml'), which strict XML
    rejects; dropping comments lets the testcases still parse."""
    import re
    return re.sub(r"<!--.*?-->", "", text, flags=re.DOTALL)


def _parse_junit_xml(text: str) -> dict:
    out: dict[str, dict] = {}
    try:
        root = ET.fromstring(text)
    except ET.ParseError:
        root = ET.fromstring(_strip_xml_comments(text))
    # testcases may sit under one or many testsuites, or directly.
    cases = root.iter("testcase")
    for tc in cases:
        name = tc.get("name") or tc.get("classname") or ""
        if not name:
            continue
        failure = tc.find("failure")
        error = tc.find("error")
        skipped = tc.find("skipped")
        if failure is not None or error is not None:
            node = failure if failure is not None else error
            msg = node.get("message") or (node.text or "").strip() or None
            status = "failed"
        elif skipped is not None:
            msg = None
            status = "skipped"
        else:
            msg = None
            status = "passed"
        out[name] = {"status": status, "message": msg}
    return out


def _parse_jest_json(text: str) -> dict:
    doc = json.loads(text)
    out: dict[str, dict] = {}
    for suite in doc.get("testResults", []):
        for a in suite.get("assertionResults", []):
            tid = a.get("fullName") or a.get("title") or ""
            if not tid:
                continue
            status = normalize_status(a.get("status", ""))
            msgs = a.get("failureMessages") or []
            msg = (msgs[0].strip() if msgs and isinstance(msgs[0], str) else None) \
                if status == "failed" else None
            out[tid] = {"status": status, "message": msg}
    return out


def _parse_pytest_json(text: str) -> dict:
    doc = json.loads(text)
    out: dict[str, dict] = {}
    for t in doc.get("tests", []):
        tid = t.get("nodeid") or ""
        if not tid:
            continue
        status = normalize_status(t.get("outcome", ""))
        msg = None
        if status == "failed":
            call = t.get("call") or {}
            crash = call.get("crash") or {}
            msg = (crash.get("message") or call.get("longrepr") or "")
            msg = msg.strip() if isinstance(msg, str) and msg.strip() else None
        out[tid] = {"status": status, "message": msg}
    return out


_PARSERS = {
    "junit_xml": _parse_junit_xml,
    "jest_json": _parse_jest_json,
    "pytest_json": _parse_pytest_json,
}


def parse_artifact(text: str, fmt: str) -> dict:
    """Parse one result artifact to {test_id: {status, message}}. Unknown/malformed
    input yields {} so a missing parse simply scores as a mismatch vs gold."""
    parser = _PARSERS.get(fmt)
    if parser is None:
        return {}
    try:
        return parser(text)
    except Exception:  # noqa - malformed artifact: empty parse, never crash the run
        return {}


# --------------------------------------------------------------------------- #
# The deterministic regression comparison
# --------------------------------------------------------------------------- #
def build_reference_report(prev_parsed: dict, curr_parsed: dict,
                           prev_build_id: str, build_id: str) -> dict:
    """The canonical CORRECT regression report for one build-pair, derived
    deterministically from the two parsed artifacts. This is the gold; the agents
    must reproduce the same seven fields from their brief."""
    prev_passed_ids = sorted(tid for tid, r in prev_parsed.items()
                             if r["status"] == "passed")
    prev_failed_ids = {tid for tid, r in prev_parsed.items() if r["status"] == "failed"}

    regressions = []
    for tid in prev_passed_ids:
        curr = curr_parsed.get(tid)
        if curr is not None and curr["status"] == "failed":
            regressions.append({"id": tid, "failure_message": curr.get("message") or ""})
    regressions.sort(key=lambda r: r["id"])

    newly_passing = sorted(
        tid for tid in prev_failed_ids
        if (curr := curr_parsed.get(tid)) is not None and curr["status"] == "passed"
    )

    return {
        "build_n_nus_1": prev_build_id,
        "build_n": build_id,
        "total_tests_in_suite": len(curr_parsed),
        "prev_passed_count": len(prev_passed_ids),
        "regressions": regressions,
        "newly_passing": newly_passing,
        "overall_status": "fail" if regressions else "pass",
    }


def regression_rate(report: dict) -> float:
    """Regression Rate (%) = regressions / prev_passed_count * 100, 2dp.
    Zero prev-passed tests => 0.0 (nothing could regress)."""
    denom = report.get("prev_passed_count") or 0
    if not denom:
        return 0.0
    n = len(report.get("regressions") or [])
    return round(100.0 * n / denom, 2)


# --------------------------------------------------------------------------- #
# Per-field scoring (agent report vs gold report) — the fidelity cells
# --------------------------------------------------------------------------- #
def _reg_id_set(report: dict) -> set:
    out = set()
    for r in report.get("regressions") or []:
        if isinstance(r, dict) and r.get("id") is not None:
            out.add(str(r["id"]))
        elif isinstance(r, str):
            out.add(r)
    return out


def _norm(s) -> str:
    return " ".join(str(s).split()).lower()


def score_report(agent_report: dict, gold_report: dict) -> dict:
    """Return {field: bool} for each of the seven REPORT_FIELDS — whether the agent's
    value matches gold. The regressions cell scores on the REGRESSION-ID SET (the
    load-bearing detection result); message reproduction is reported separately as a
    diagnostic, not as part of the cell."""
    a = agent_report if isinstance(agent_report, dict) else {}
    cells: dict[str, bool] = {}
    cells["build_n_nus_1"] = str(a.get("build_n_nus_1")) == str(gold_report["build_n_nus_1"])
    cells["build_n"] = str(a.get("build_n")) == str(gold_report["build_n"])
    cells["total_tests_in_suite"] = _as_int(a.get("total_tests_in_suite")) == gold_report["total_tests_in_suite"]
    cells["prev_passed_count"] = _as_int(a.get("prev_passed_count")) == gold_report["prev_passed_count"]
    cells["regressions"] = _reg_id_set(a) == _reg_id_set(gold_report)
    cells["newly_passing"] = {str(x) for x in (a.get("newly_passing") or [])} == \
        {str(x) for x in gold_report["newly_passing"]}
    cells["overall_status"] = _norm(a.get("overall_status")) == _norm(gold_report["overall_status"])
    return cells


def report_conformance(raw_report: dict, gold_report: dict) -> dict:
    """DETERMINISTIC structural exactness of the agent's RAW report vs the canonical
    gold report, scored BEFORE the tolerant score_report() normalisation. This is the
    discriminator that separates frameworks when fidelity ties at 100%: a report that
    only scores full fidelity because score_report() is lenient (ints-as-strings, bare
    string regressions, extra keys, mangled messages) loses conformance points here.

    Returns {"earned": int, "total": int, "issues": [str]}. Higher earned/total = a
    more precisely-constructed report.
    """
    issues: list[str] = []
    earned = 0
    total = 0
    a = raw_report if isinstance(raw_report, dict) else {}

    def pt(ok: bool, msg: str):
        nonlocal earned, total
        total += 1
        if ok:
            earned += 1
        else:
            issues.append(msg)

    # Exactly the seven keys, no more, no fewer.
    keys = set(a.keys())
    want = set(REPORT_FIELDS)
    pt(keys == want, f"keys differ: extra={sorted(keys - want)} missing={sorted(want - keys)}")

    # Build identifiers copied unchanged (exact type/value).
    pt(a.get("build_n_nus_1") == gold_report["build_n_nus_1"], "build_n_nus_1 not exact")
    pt(a.get("build_n") == gold_report["build_n"], "build_n not exact")

    # Counts are native ints (not stringified) and exact.
    pt(isinstance(a.get("total_tests_in_suite"), int)
       and a["total_tests_in_suite"] == gold_report["total_tests_in_suite"],
       "total_tests_in_suite not an exact int")
    pt(isinstance(a.get("prev_passed_count"), int)
       and a["prev_passed_count"] == gold_report["prev_passed_count"],
       "prev_passed_count not an exact int")

    # regressions: a list of objects each with EXACTLY {id, failure_message}.
    regs = a.get("regressions")
    well_formed = isinstance(regs, list) and all(
        isinstance(r, dict) and set(r.keys()) == {"id", "failure_message"} for r in regs)
    pt(well_formed, "regressions not a list of exactly {id, failure_message} objects")

    # regression id set exact.
    pt(_reg_id_set(a) == _reg_id_set(gold_report), "regression id set not exact")

    # each regression failure_message verbatim-equals gold's.
    gold_msg = {r["id"]: r.get("failure_message", "") for r in gold_report.get("regressions") or []}
    a_msg = {r["id"]: r.get("failure_message", "")
             for r in (regs or []) if isinstance(r, dict) and "id" in r}
    msgs_exact = bool(gold_msg) and all(a_msg.get(k) == v for k, v in gold_msg.items())
    if not gold_msg:
        # no regressions in gold -> award the point iff agent also emitted none
        msgs_exact = not a_msg
    pt(msgs_exact, "failure_message(s) not verbatim")

    # newly_passing: a list of strings, set exact.
    npass = a.get("newly_passing")
    npass_ok = isinstance(npass, list) and all(isinstance(x, str) for x in npass) and \
        {str(x) for x in npass} == {str(x) for x in gold_report["newly_passing"]}
    pt(npass_ok, "newly_passing not an exact string list")

    # overall_status exactly the canonical lowercase value.
    pt(a.get("overall_status") == gold_report["overall_status"],
       "overall_status not exactly the canonical pass/fail string")

    return {"earned": earned, "total": total, "issues": issues}


def message_fidelity(agent_report: dict, gold_report: dict) -> float | None:
    """Diagnostic: of the gold regressions whose IDs the agent also flagged, the
    fraction whose failure_message the agent reproduced (normalized substring, either
    direction). None when gold has no regressions."""
    gold_msgs = {r["id"]: r.get("failure_message", "") for r in gold_report.get("regressions") or []}
    if not gold_msgs:
        return None
    a_msgs = {}
    for r in (agent_report or {}).get("regressions") or []:
        if isinstance(r, dict) and r.get("id") is not None:
            a_msgs[str(r["id"])] = r.get("failure_message", "")
    hit = 0
    for tid, gmsg in gold_msgs.items():
        am = a_msgs.get(str(tid))
        if am is None:
            continue
        gn, an = _norm(gmsg), _norm(am)
        if gn and (gn in an or an in gn):
            hit += 1
    return round(100.0 * hit / len(gold_msgs), 2)


def _as_int(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None
