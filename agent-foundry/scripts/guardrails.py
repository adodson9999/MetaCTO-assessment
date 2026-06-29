#!/usr/bin/env python3
# Used by: shared — guardrail gates (G1–G13) for all-agent runs: make_all_test_cases, produce_all_testcases, run_pipeline, handoff_all.
"""Post-run guardrail layer for the agent-foundry orchestration.

Turns every known failure class from the RUN-20260628 retrospective into a
deterministic, reported signal. It does two things:

  1. CLASSIFY each agent's REAL outcome from its metric/artifacts/stderr, replacing
     the driver's misleading "artifacts written => PASS". Outcomes:
       ERROR        crashed (traceback in stderr)
       EMPTY        ran but produced no usable output (model failure)
       ENV-LIMITED  low score because the TARGET lacks the probed capability
                    (see data/target-capabilities.json) — excluded from real-fail accounting
       FAIL         real low score on a capability the target DOES support
       PARTIAL      mid-range score
       PASS         metric >= pass threshold
       N/A          general/non-metric agent ran cleanly

  2. RUN guardrail checks G1..G10 and write guardrails-report.json.

This module is AGENT-SIDE only. It never touches the DummyJSON app; the capability
manifest tells it how to interpret results so absent-feature 0%s stop reading as bugs.

Usage:  python guardrails.py <RUN_ID>
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
CAP_PATH = WS / "data" / "target-capabilities.json"
PCT_RE = re.compile(r"=\s*(-?\d+(?:\.\d+)?)\s*%")
TRACEBACK_MARKERS = ("Traceback (most recent call last)", "\nError:", "Exception:")

API_TESTERS = [
    "validate-request-payloads", "verify-response-status-codes", "test-authentication-flows",
    "check-authorization-rules", "validate-json-schema-responses", "test-pagination-behavior",
    "verify-error-message-clarity", "test-rate-limit-enforcement", "validate-query-parameter-handling",
    "test-idempotency-of-endpoints", "verify-content-type-negotiation", "validate-null-empty-fields",
    "test-timeout-handling", "verify-crud-operation-integrity", "test-concurrent-request-handling",
    "validate-header-propagation", "test-webhook-delivery", "run-regression-suite",
    "track-defect-density", "validate-api-versioning-behavior", "test-ssl-tls-enforcement",
    "verify-caching-headers", "validate-correlation-id-propagation", "test-bulk-operation-endpoints",
    "verify-audit-log-generation", "validate-search-and-filter-queries", "test-file-upload-and-download",
    "verify-sorting-behavior", "test-event-driven-api-triggers", "test-ip-allowlist-enforcement",
    "test-api-gateway-routing", "verify-third-party-oauth-integration", "test-multipart-form-data-handling",
    "validate-retry-after-header-compliance", "test-soft-delete-behavior", "validate-graphql-depth-limits",
    "test-long-polling-support", "verify-enum-value-restrictions", "measure-api-consumer-satisfaction",
    "create-postman-collection",
]
GENERALS = ["test-case-creator", "documentation-reviewer", "run-cicd-pipeline", "bug-reporter"]


def load_caps() -> dict:
    try:
        return json.loads(CAP_PATH.read_text())
    except OSError:
        return {"capabilities": {}, "agent_capability_map": {},
                "pass_threshold_pct": 70.0, "partial_threshold_pct": 30.0}


def _read(p: Path) -> str:
    try:
        return p.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def _full_name(name: str) -> str:
    return f"{'api-tester' if name in API_TESTERS else 'general'}-{name}"


def agent_metric(run_dir: Path, name: str) -> tuple[float | None, str]:
    """Primary metric % for an agent: first '=NN%' in its stdout summary line,
    falling back to metric_value / first *_pct key in its result JSON. None if unknown."""
    full = _full_name(name)
    stdout = _read(next(iter((run_dir / "agents" / full).glob("*stdout.txt")), Path("/nonexistent")))
    line = next((ln for ln in stdout.splitlines() if ln.strip().startswith(f"[{full}]")), "")
    m = PCT_RE.search(line)
    if m:
        return float(m.group(1)), line.strip()
    for cand in (run_dir / f"{full}.json", run_dir / f"{full}.cases.json"):
        try:
            d = json.loads(cand.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(d, dict):
            if isinstance(d.get("metric_value"), (int, float)):
                return float(d["metric_value"]), f"(from {cand.name}) metric_value={d['metric_value']}"
            for k, v in d.items():
                if k.endswith("_pct") and isinstance(v, (int, float)):
                    return float(v), f"(from {cand.name}) {k}={v}"
    return None, line.strip()


def is_empty(run_dir: Path, name: str) -> tuple[bool, str]:
    """True if the agent produced no usable output (the model-failure signal)."""
    full = _full_name(name)
    for cand in (run_dir / f"{full}.json", run_dir / f"{full}.cases.json"):
        try:
            d = json.loads(cand.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        if isinstance(d, dict):
            for key in ("present_tc", "responses_validated", "produced_cases", "emitted_tc"):
                if key in d and not d[key]:
                    return True, f"{key}=0 in {cand.name}"
        if isinstance(d, list) and len(d) == 0:
            return True, f"empty array in {cand.name}"
    # no metric AND no cases file at all
    pct, _ = agent_metric(run_dir, name)
    has_cases = any(run_dir.glob(f"{full}*.json"))
    if pct is None and not has_cases:
        return True, "no metric and no result artifact"
    return False, ""


def has_traceback(run_dir: Path, name: str) -> bool:
    full = _full_name(name)
    err = _read(next(iter((run_dir / "agents" / full).glob("*stderr.txt")), Path("/nonexistent")))
    return any(mk in err for mk in TRACEBACK_MARKERS)


def classify(run_dir: Path, name: str, caps: dict) -> dict:
    pass_t = caps.get("pass_threshold_pct", 70.0)
    part_t = caps.get("partial_threshold_pct", 30.0)
    cap_map = caps.get("agent_capability_map", {})
    cap_defs = caps.get("capabilities", {})

    error = has_traceback(run_dir, name)
    empty, empty_reason = is_empty(run_dir, name)
    pct, line = agent_metric(run_dir, name)

    # capability dependency: any mapped cap that is unsupported on the target
    unsupported = [c for c in cap_map.get(name, []) if not cap_defs.get(c, {}).get("supported", True)]

    if error:
        outcome, why = "ERROR", "traceback in stderr"
    elif empty:
        outcome, why = "EMPTY", empty_reason
    elif pct is None:
        outcome, why = "N/A", "ran; no headline metric (general agent)"
    elif pct >= pass_t:
        outcome, why = "PASS", f"metric {pct}% >= {pass_t}%"
    elif unsupported:
        outcome, why = "ENV-LIMITED", f"low metric ({pct}%) attributable to unsupported target capability: {', '.join(unsupported)}"
    elif pct >= part_t:
        outcome, why = "PARTIAL", f"metric {pct}% in [{part_t}%,{pass_t}%)"
    else:
        outcome, why = "FAIL", f"metric {pct}% < {part_t}% on a supported capability"

    return {"agent": name, "outcome": outcome, "metric_pct": pct,
            "unsupported_caps": unsupported, "reason": why, "summary_line": line}


# --------------------------------------------------------------------------- #
# Guardrail checks (G1..G10): each returns {id, name, status, detail}
# status: PASS (clean) | WARN (informational/known-gap) | FAIL (must fix)
# --------------------------------------------------------------------------- #
def g1_fixture_presence() -> dict:
    # A build_gold.py whose gold was never produced (no gold.json AND no *_spec.json)
    # is the "missing fixture" class that crashed validate-retry-after-header-compliance.
    # Dirs that built gold under any name (gold.json or <x>_spec.json) are fine.
    missing = []
    for bg in sorted((WS / "data").glob("*/build_gold.py")):
        agent_dir = bg.parent
        built = (agent_dir / "gold.json").exists() or bool(list(agent_dir.glob("*_spec.json")))
        if not built:
            missing.append(str(agent_dir.relative_to(WS)))
    return {"id": "G1", "name": "fixture-presence",
            "status": "FAIL" if missing else "PASS",
            "detail": f"agent data dirs whose gold/spec was never built: {missing or 'none'}"}


def g2_no_crash_as_pass(rows: list, exec_status: dict) -> dict:
    bad = [r["agent"] for r in rows
           if r["outcome"] == "ERROR" and exec_status.get(r["agent"]) in ("PASS",)]
    return {"id": "G2", "name": "no-crash-as-pass",
            "status": "FAIL" if bad else "PASS",
            "detail": f"agents with stderr traceback but execution_status PASS: {bad or 'none'}"}


def g3_honest_outcome(rows: list, exec_status: dict) -> dict:
    exec_pass = sum(1 for v in exec_status.values() if v == "PASS")
    quality_pass = sum(1 for r in rows if r["outcome"] == "PASS")
    gap = exec_pass - quality_pass
    return {"id": "G3", "name": "honest-pass-semantics",
            "status": "WARN" if gap > 0 else "PASS",
            "detail": f"execution-PASS={exec_pass} vs quality-PASS={quality_pass}; "
                      f"{gap} agents looked PASS but were not (now reclassified)."}


def g4_env_separation(rows: list) -> dict:
    env = [r["agent"] for r in rows if r["outcome"] == "ENV-LIMITED"]
    return {"id": "G4", "name": "env-limited-separation",
            "status": "PASS",
            "detail": f"{len(env)} agents reclassified ENV-LIMITED (target lacks the feature, not a bug): {env}"}


def g5_empty_output(rows: list) -> dict:
    empty = [r["agent"] for r in rows if r["outcome"] == "EMPTY"]
    return {"id": "G5", "name": "empty-output-detection",
            "status": "WARN" if empty else "PASS",
            "detail": f"agents that produced no usable output (model failure): {empty or 'none'}"}


def g6_metric_saturation(run_dir: Path, rows: list) -> dict:
    sat = []
    for r in rows:
        if r["metric_pct"] is not None and r["metric_pct"] >= 100.0:
            empty, _ = is_empty(run_dir, r["agent"])
            if empty:
                sat.append(r["agent"])
    return {"id": "G6", "name": "metric-saturation-oracle",
            "status": "FAIL" if sat else "PASS",
            "detail": f"agents scoring 100% on EMPTY output (saturation): {sat or 'none'}"}


def g7_producer_scope(run_dir: Path) -> dict:
    f = run_dir / "general-test-case-creator.json"
    try:
        gold_tc = json.loads(f.read_text()).get("gold_tc")
    except (OSError, json.JSONDecodeError):
        gold_tc = None
    # Durable scope signal: the 40-agent manifest exists and enables every api-tester.
    full = WS / "data" / "test-case-creator" / "manifest.full.json"
    full_n = 0
    try:
        full_n = sum(1 for e in json.loads(full.read_text()) if e.get("enabled"))
    except (OSError, json.JSONDecodeError):
        full_n = 0
    run_ok = bool(gold_tc) and gold_tc >= len(API_TESTERS)
    infra_ok = full_n >= len(API_TESTERS)
    status = "PASS" if (run_ok or infra_ok) else "WARN"
    return {"id": "G7", "name": "producer-scope",
            "status": status,
            "detail": f"this-run gold_tc={gold_tc}; manifest.full.json enables {full_n}/{len(API_TESTERS)} "
                      f"api-testers. {'40-agent scope wired.' if infra_ok else 'Demo-scoped only.'}"}


def g8_reviewer_inversion(run_dir: Path) -> dict:
    flags = []
    rev_dir = run_dir / "general-documentation-reviewer.reviews"
    for rf in sorted(rev_dir.glob("*.json")) if rev_dir.is_dir() else []:
        try:
            r = json.loads(rf.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        em = r.get("emitted", {})
        reason = (em.get("reason") or "").lower()
        verdict = em.get("verdict")
        # BR-004 class: reasoning says "matches" but verdict is "yes" (differs)
        if verdict == "yes" and "match" in reason and "differ" not in reason:
            flags.append({"case": r.get("case_id"), "issue": "verdict=yes but reason says 'matches' (should be 'no')"})
        # gold disagreement recorded by the harness
        if r.get("verdict_correct") is False:
            flags.append({"case": r.get("case_id"), "issue": "verdict != gold"})
    return {"id": "G8", "name": "reviewer-inversion-guard",
            "status": "WARN" if flags else "PASS",
            "detail": f"documentation-reviewer suspect verdicts: {flags or 'none'}"}


def g9_ledger_presence(run_dir: Path) -> dict:
    led = run_dir / "adjudication-ledger.json"
    rows = 0
    try:
        rows = len(json.loads(led.read_text()).get("rows", []))
    except (OSError, json.JSONDecodeError):
        rows = -1
    return {"id": "G9", "name": "adjudication-ledger",
            "status": "WARN" if rows <= 0 else "PASS",
            "detail": f"adjudication-ledger rows={rows} "
                      f"(scripts/adjudicate.py §3 loop: mismatch -> capability filter -> "
                      f"newest-wins doc verdict -> reviewer-gated bug). 0/absent => not run."}


def g10_coverage(rows: list) -> dict:
    expected = set(API_TESTERS + GENERALS)
    got = {r["agent"] for r in rows}
    missing = sorted(expected - got)
    return {"id": "G10", "name": "coverage-denominator",
            "status": "FAIL" if missing else "PASS",
            "detail": f"agents with no classification: {missing or 'none'}"}


def g11_per_agent_producer(run_dir: Path) -> dict:
    """HARD: the producer MUST be invoked per-agent (right after each api-tester), never as a
    single batch. Every EXECUTED api-tester must have a per-agent producer invocation with
    cases>0 or a logged sentinel. A batch invocation, a missing invocation, or any producer
    timeout marks the run BROKEN."""
    inv = _read_json(run_dir / "producer-invocations.json", {})
    invs = inv.get("invocations", [])
    if not invs:
        return {"id": "G11", "name": "per-agent-producer", "hard": True, "status": "FAIL",
                "detail": "no producer-invocations.json — producer was not run per-agent."}
    # which api-testers actually executed this run (have an agent dir)? create-postman-collection
    # is the general collection builder, not a test-case producer — never expect a producer call.
    testers = [a for a in API_TESTERS if a != "create-postman-collection"]
    executed = {a for a in testers if any((run_dir / "agents" / f"api-tester-{a}").glob("*"))}
    covered = {i["agent"] for i in invs if i.get("mode") == "per-agent"}
    batch = [i for i in invs if i.get("mode") != "per-agent"]
    missing = sorted(a for a in executed if f"api-tester-{a}" not in covered)
    timeouts = [i["agent"] for i in invs if i.get("timed_out")]
    problems = []
    if batch:
        problems.append(f"batch producer invocation(s) detected: {[i['agent'] for i in batch]}")
    if missing:
        problems.append(f"executed api-testers with NO per-agent producer call: {missing}")
    if timeouts:
        problems.append(f"per-agent producer timeout(s) (raise FORGE_TESTCASE_AGENT_TIMEOUT): {timeouts}")
    return {"id": "G11", "name": "per-agent-producer", "hard": True,
            "status": "FAIL" if problems else "PASS",
            "detail": (f"{len(covered)} per-agent producer calls, "
                       f"{inv.get('agents_with_cases', '?')} with cases, "
                       f"{inv.get('sentinels', '?')} sentinels. " + ("; ".join(problems) or "all executed api-testers covered per-agent."))}


def _read_json(p: Path, default):
    try:
        return json.loads(p.read_text())
    except (OSError, json.JSONDecodeError):
        return default


BUCKET_DIRS = ["authz", "clarity", "crud", "schema", "status"]


def g12_agent_output_location(run_dir: Path) -> dict:
    """HARD: every api-tester writes to the STANDARD results/runs/<RUN>/api-tester-<agent>.cases.json.
    Bespoke per-task bucket dirs (results/authz/, results/clarity/, …) are forbidden — they
    produce mislabeled folders instead of the agent name. Fails on a bucket dir under results/
    OR any agents/common module that builds a 'results/<bucket>/runs' path."""
    results = WS / "results"
    present = [b for b in BUCKET_DIRS if (results / b).is_dir()]
    offenders = []
    for py in sorted((WS / "agents" / "common").glob("*.py")):
        try:
            src = py.read_text(errors="replace")
        except OSError:
            continue
        for b in BUCKET_DIRS:
            if re.search(r'"results"\s*/\s*"' + re.escape(b) + r'"\s*/\s*"runs"', src):
                offenders.append(f"{py.name}:results/{b}/runs")
    problems = []
    if present:
        problems.append(f"bucket dirs under results/: {present}")
    if offenders:
        problems.append(f"modules building bucket paths: {offenders}")
    return {"id": "G12", "name": "agent-output-location", "hard": True,
            "status": "FAIL" if problems else "PASS",
            "detail": "; ".join(problems) or "all agent output uses the standard results/runs/<RUN>/ path; no bespoke buckets."}


_DATE_RE = re.compile(r"^\d{4}-\d{2}-\d{2}$")
_TIME_RE = re.compile(r"^\d{2}-\d{2}-\d{2}$")
_AGENT_SECTIONS = ("TestCases", "BugReport")
_POSTMAN_FILES = {"collection.json", "environment.json"}
_LAYOUT_FILES = {"cases.json", "cases.md"}
_LAYOUT_IGNORE = {".DS_Store"}

# Core-Requirements coverage floors (scenario_ids that MUST appear in each core agent's cases)
_AUTH_REQUIRED = {"AUTH-LOGIN-VALID", "AUTH-LOGIN-WRONGPASS", "AUTH-LOGIN-UNKNOWN",
                  "AUTH-ME-VALID", "AUTH-ME-MISSING", "AUTH-ME-MALFORMED", "AUTH-ME-EXPIRED",
                  "AUTH-REFRESH-VALID", "AUTH-REFRESH-MISSING"}
_CRUD_REQUIRED = {"CRUD-READ-ONE", "CRUD-CREATE", "CRUD-CREATE-NONPERSIST", "CRUD-UPDATE",
                  "CRUD-DELETE", "CRUD-READ-MISSING"}
_SEARCH_REQUIRED = {"SEARCH-KEYWORD", "FILTER-CATEGORY", "PAGE-LIMIT-SKIP", "SELECT-FIELDS", "SORT-ASC"}


def g13_results_layout() -> dict:
    """HARD: after a clean run, results/ contains ONLY <YYYY-MM-DD>/<HH-MM-SS>/ trees, each with
    TestCases/<agent>/{cases.json,cases.md} (required), optional BugReport/<agent>/{...}, and an
    optional Postman/{collection.json,environment.json}. No runs/, flat agent folders, or loose files."""
    results = WS / "results"
    bad: list[str] = []
    if not results.is_dir():
        return {"id": "G13", "name": "results-layout", "hard": True, "status": "PASS",
                "detail": "results/ absent (nothing to validate)."}
    for top in sorted(results.iterdir()):
        if top.name in _LAYOUT_IGNORE:
            continue
        if not top.is_dir() or not _DATE_RE.match(top.name):
            bad.append(f"forbidden top-level entry: {top.name} (only YYYY-MM-DD dirs allowed)")
            continue
        for tdir in sorted(top.iterdir()):
            if tdir.name in _LAYOUT_IGNORE:
                continue
            if not tdir.is_dir() or not _TIME_RE.match(tdir.name):
                bad.append(f"{top.name}/{tdir.name}: not a HH-MM-SS time dir")
                continue
            if not (tdir / "TestCases").is_dir():
                bad.append(f"{top.name}/{tdir.name}: missing TestCases/")
            for entry in sorted(tdir.iterdir()):
                if entry.name in _LAYOUT_IGNORE:
                    continue
                if entry.name == "Postman":
                    names = {f.name for f in entry.iterdir() if f.name not in _LAYOUT_IGNORE}
                    if names != _POSTMAN_FILES:
                        bad.append(f"Postman/: files {sorted(names)} != {sorted(_POSTMAN_FILES)}")
                    continue
                if entry.name not in _AGENT_SECTIONS:
                    bad.append(f"{top.name}/{tdir.name}/{entry.name}: not TestCases|BugReport|Postman")
                    continue
                for agent in sorted(entry.iterdir()):
                    if agent.name in _LAYOUT_IGNORE:
                        continue
                    if not agent.is_dir():
                        bad.append(f"{entry.name}/{agent.name}: loose file (must be <agent>/ dir)")
                        continue
                    names = {f.name for f in agent.iterdir() if f.name not in _LAYOUT_IGNORE}
                    if names != _LAYOUT_FILES:
                        bad.append(f"{entry.name}/{agent.name}: files {sorted(names)} != {sorted(_LAYOUT_FILES)}")
    return {"id": "G13", "name": "results-layout", "hard": True,
            "status": "FAIL" if bad else "PASS",
            "detail": ("; ".join(bad) if bad
                       else "results/ holds only <date>/<time>/{TestCases,BugReport,Postman} per the contract.")}


# --------------------------------------------------------------------------- #
# Core-Requirements coverage gates (G14–G17): operate on one run's out_root
# --------------------------------------------------------------------------- #
def _latest_run_dir():
    results = WS / "results"
    dates = [d for d in (results.iterdir() if results.is_dir() else []) if d.is_dir() and _DATE_RE.match(d.name)]
    times = [t for d in dates for t in d.iterdir() if t.is_dir() and _TIME_RE.match(t.name)]
    return max(times, key=lambda p: p.name, default=None) if times else None


def _scenario_ids(out_root: Path, agent: str) -> set:
    cf = out_root / "TestCases" / agent / "cases.json"
    try:
        return {c.get("test_data", {}).get("scenario_id") for c in json.loads(cf.read_text())}
    except (OSError, json.JSONDecodeError):
        return set()


def _coverage_gate(gid: str, name: str, agent: str, required: set, out_root: Path) -> dict:
    if out_root is None:
        out_root = _latest_run_dir()
    present = _scenario_ids(out_root, agent) if out_root else set()
    missing = sorted(required - present)
    return {"id": gid, "name": name, "hard": True, "status": "FAIL" if missing else "PASS",
            "detail": (f"{agent}: missing required scenarios {missing}" if missing
                       else f"{agent}: all {len(required)} required core scenarios present.")}


def g14_auth_lifecycle(out_root: Path = None) -> dict:
    """HARD: the auth agent must cover the JWT lifecycle (login valid/wrong/unknown, /auth/me
    valid/missing/malformed/expired, refresh valid/missing) — not just a happy-path login."""
    return _coverage_gate("G14", "auth-lifecycle", "test-authentication-flows", _AUTH_REQUIRED, out_root)


def g15_crud_products(out_root: Path = None) -> dict:
    """HARD: the CRUD agent must cover products create/read/update/delete + a 404 negative + the
    documented non-persistence proof."""
    return _coverage_gate("G15", "crud-products-depth", "verify-crud-operation-integrity", _CRUD_REQUIRED, out_root)


def g16_search_coverage(out_root: Path = None) -> dict:
    """HARD: the search agent must cover keyword search, category filter, pagination, field select,
    and sort."""
    return _coverage_gate("G16", "search-coverage", "validate-search-and-filter-queries", _SEARCH_REQUIRED, out_root)


def g17_postman(out_root: Path = None) -> dict:
    """HARD: the Postman deliverable exists, is valid v2.1, organised into the four Core-Requirement
    folders, ships {{base_url}}, and every request carries a pm.test() assertion script."""
    if out_root is None:
        out_root = _latest_run_dir()
    col = (out_root / "Postman" / "collection.json") if out_root else None
    if not col or not col.exists():
        return {"id": "G17", "name": "postman-deliverable", "hard": True, "status": "FAIL",
                "detail": "Postman/collection.json missing."}
    try:
        c = json.loads(col.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"id": "G17", "name": "postman-deliverable", "hard": True, "status": "FAIL",
                "detail": f"collection.json not valid JSON: {e}"}
    problems = []
    folders = {f.get("name") for f in c.get("item", [])}
    want = {"Authentication", "CRUD — Products", "Search & Filtering", "Error Handling"}
    if not want.issubset(folders):
        problems.append(f"missing folders {sorted(want - folders)}")
    if "base_url" not in {v.get("key") for v in c.get("variable", [])}:
        problems.append("missing {{base_url}} variable")
    reqs = [it for f in c.get("item", []) for it in f.get("item", [])]
    if not reqs:
        problems.append("no requests")
    no_test = [it["name"] for it in reqs
               if not any(ev.get("listen") == "test" and "pm.test" in "\n".join(ev.get("script", {}).get("exec", []))
                          for ev in it.get("event", []))]
    if no_test:
        problems.append(f"{len(no_test)} request(s) lack a pm.test script")
    return {"id": "G17", "name": "postman-deliverable", "hard": True,
            "status": "FAIL" if problems else "PASS",
            "detail": "; ".join(problems) or f"valid v2.1 collection: {len(folders)} folders, {len(reqs)} requests, all asserted."}


def core_gate(out_root: Path = None) -> list:
    """The deliverable gate set: layout (G13) + the four Core-Requirements coverage gates."""
    return [g13_results_layout(), g14_auth_lifecycle(out_root), g15_crud_products(out_root),
            g16_search_coverage(out_root), g17_postman(out_root)]


def run(run_id: str) -> dict:
    run_dir = WS / "results" / "runs" / run_id
    caps = load_caps()
    state = {}
    try:
        state = json.loads((run_dir / "orchestration-state.json").read_text())
    except (OSError, json.JSONDecodeError):
        pass
    exec_status = {k: v.get("outcome") for k, v in state.get("agents", {}).items()}

    order = [a for a in API_TESTERS + GENERALS
             if a in exec_status or any((run_dir / "agents" / _full_name(a)).glob("*"))]
    if not order:
        order = API_TESTERS + GENERALS
    rows = [classify(run_dir, a, caps) for a in order]

    checks = [
        g1_fixture_presence(),
        g2_no_crash_as_pass(rows, exec_status),
        g3_honest_outcome(rows, exec_status),
        g4_env_separation(rows),
        g5_empty_output(rows),
        g6_metric_saturation(run_dir, rows),
        g7_producer_scope(run_dir),
        g8_reviewer_inversion(run_dir),
        g9_ledger_presence(run_dir),
        g10_coverage(rows),
        g11_per_agent_producer(run_dir),
        g12_agent_output_location(run_dir),
    ]
    from collections import Counter
    dist = dict(Counter(r["outcome"] for r in rows))
    report = {
        "run_id": run_id,
        "outcome_distribution": dist,
        "checks": checks,
        "any_fail": any(c["status"] == "FAIL" for c in checks),
        "any_hard_fail": any(c["status"] == "FAIL" and c.get("hard") for c in checks),
        "agents": rows,
    }
    (run_dir / "guardrails-report.json").write_text(json.dumps(report, indent=2))
    return report


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python guardrails.py <RUN_ID> | layout", file=sys.stderr)
        sys.exit(2)
    if sys.argv[1] == "layout":
        gates = core_gate()
        for c in gates:
            print(f"  {c['id']} {c['name']}: {c['status']} — {c['detail']}")
        sys.exit(1 if any(g["status"] == "FAIL" and g.get("hard") for g in gates) else 0)
    rep = run(sys.argv[1])
    print(f"[guardrails] outcomes={rep['outcome_distribution']}")
    for c in rep["checks"]:
        print(f"  {c['id']} {c['name']}: {c['status']} — {c['detail']}")
    sys.exit(1 if rep["any_fail"] else 0)


if __name__ == "__main__":
    main()
