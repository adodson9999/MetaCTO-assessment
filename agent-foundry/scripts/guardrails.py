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
    elif empty and unsupported:
        # Producing no cases is EXPECTED when the probed capability is genuinely absent on the
        # target (no RBAC, no enum enforcement, no documented response schema). That is ENV-LIMITED,
        # not a model failure — so it never trips the G21 empty-output hard gate.
        outcome, why = "ENV-LIMITED", f"no output; probed capability absent on target: {', '.join(unsupported)}"
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


def g21_no_silent_empty(rows: list) -> dict:
    """HARD: no agent may ship EMPTY on a capability the target SUPPORTS. An EMPTY outcome here means
    the agent ran but produced no usable output (e.g. its LLM case-gen timed out) while the probed
    feature genuinely exists — the exact silent-miss that let the auth agent skip AUTH-ME-MALFORMED
    and still be marked PASS. Empties whose capability is declared unsupported are already downgraded
    to ENV-LIMITED by classify() and never reach here, so absent-feature 0%s do not trip this gate."""
    empty = [r["agent"] for r in rows if r["outcome"] == "EMPTY"]
    return {"id": "G21", "name": "no-silent-empty", "hard": True,
            "status": "FAIL" if empty else "PASS",
            "detail": (f"agent(s) EMPTY on a SUPPORTED capability (silent coverage miss — map to an "
                       f"unsupported capability if the target truly lacks it, else fix the agent): {empty}"
                       if empty else "no agent shipped empty output on a supported capability.")}


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
_PRESERVE_MARKER = "code-review"   # code-review judge fixtures/leaderboards: a separate subsystem, not run output
_RESULTS_KEEP = {"_global"}        # code-review subsystem's shared dir — tolerated (kept by choice); see G23

# Core-Requirements coverage floors (scenario_ids that MUST appear in each core agent's cases)
_AUTH_REQUIRED = {"AUTH-LOGIN-VALID", "AUTH-LOGIN-WRONGPASS", "AUTH-LOGIN-UNKNOWN",
                  "AUTH-ME-VALID", "AUTH-ME-MISSING", "AUTH-ME-MALFORMED", "AUTH-ME-EXPIRED",
                  "AUTH-REFRESH-VALID", "AUTH-REFRESH-MISSING"}
_CRUD_REQUIRED = {"CRUD-READ-ONE", "CRUD-CREATE", "CRUD-CREATE-NONPERSIST", "CRUD-UPDATE",
                  "CRUD-DELETE", "CRUD-READ-MISSING"}
_SEARCH_REQUIRED = {"SEARCH-KEYWORD", "FILTER-CATEGORY", "PAGE-LIMIT-SKIP", "SELECT-FIELDS", "SORT-ASC"}


_BUGREPORT_ARTIFACT_DIRS = {"screenshots", "recordings", "logs", "db"}
# Index/manifest files are forbidden under BugReport (G22) — the per-bug JSONs are the source of truth.
_FORBIDDEN_BUG_INDEX_RE = re.compile(r".*-index\.json$|^index\.json$")


def _check_section(entry: Path) -> list:
    """Validate one TestCases/ or BugReport/ section. TestCases is strict: every <agent>/ holds
    EXACTLY {cases.json,cases.md}. BugReport is the deliverable's bug tree and may also hold
    per-run index files (verified-/unverified-index.json), shared artifact dirs (screenshots/
    recordings/logs/db), and per-agent bug reports in EITHER shape — System-B {cases.json,cases.md}
    OR System-A verified_bugs/ | unverified_bugs/ (plus their own artifacts). Extras are allowed in
    BugReport so a self-contained report (with its screenshots + screen recordings) still passes."""
    bad: list = []
    is_bug = entry.name == "BugReport"
    for child in sorted(entry.iterdir()):
        if child.name in _LAYOUT_IGNORE:
            continue
        if is_bug and child.is_file() and _FORBIDDEN_BUG_INDEX_RE.match(child.name):
            bad.append(f"BugReport/{child.name}: forbidden index file (G22 — bug JSONs are the "
                       f"source of truth)")
            continue
        if is_bug and child.is_dir() and child.name in _BUGREPORT_ARTIFACT_DIRS:
            continue
        if is_bug and child.is_dir() and child.name == "unverified":
            continue  # the single top-level unverified/{category}/ tree (not an agent)
        if not child.is_dir():
            bad.append(f"{entry.name}/{child.name}: loose file (must be <agent>/ dir)")
            continue
        names = {f.name for f in child.iterdir() if f.name not in _LAYOUT_IGNORE}
        if not is_bug:
            if names != _LAYOUT_FILES:
                bad.append(f"{entry.name}/{child.name}: files {sorted(names)} != {sorted(_LAYOUT_FILES)}")
            continue
        # BugReport agent dir: System-B cases pair, OR System-A verified_bugs/ (unverified bugs no
        # longer live per-agent — they are in the top-level BugReport/unverified/ tree).
        system_b = _LAYOUT_FILES.issubset(names)
        system_a = "verified_bugs" in names
        if not (system_b or system_a):
            bad.append(f"BugReport/{child.name}: neither {sorted(_LAYOUT_FILES)} nor "
                       f"verified_bugs/ present (got {sorted(names)})")
    return bad


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
        if (top.name in _LAYOUT_IGNORE or _PRESERVE_MARKER in top.name
                or top.name == "runs" or top.name in _RESULTS_KEEP):
            continue   # transient shared executor dir (runs/) + code-review subsystem are tolerated
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
                bad.extend(_check_section(entry))
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
    want = {"test-authentication-flows", "verify-crud-operation-integrity",
            "validate-search-and-filter-queries"}
    if not want.issubset(folders):
        problems.append(f"missing agent folders {sorted(want - folders)}")
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


_POSTMAN_NAME_RE = re.compile(r"^TC-[A-Z]+-\d{3,} — .+")


def g18_postman_testcase_alignment(out_root: Path = None) -> dict:
    """HARD: every Postman request is named '<test_case_id> — <title>', sits in its agent's folder,
    and maps 1:1 to a row in that agent's TestCases cases.json (same id AND same title). This is what
    makes a request traceable to its test case; it must hold whenever the collection is created."""
    if out_root is None:
        out_root = _latest_run_dir()
    col_path = (out_root / "Postman" / "collection.json") if out_root else None
    if not col_path or not col_path.exists():
        return {"id": "G18", "name": "postman-testcase-alignment", "hard": True, "status": "FAIL",
                "detail": "Postman/collection.json missing."}
    try:
        c = json.loads(col_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"id": "G18", "name": "postman-testcase-alignment", "hard": True, "status": "FAIL",
                "detail": f"collection.json not valid JSON: {e}"}
    problems: list[str] = []
    checked = 0
    for folder in c.get("item", []):
        agent = folder.get("name", "")
        try:
            cases = {cc["test_case_id"]: cc["title_summary"]
                     for cc in json.loads((out_root / "TestCases" / agent / "cases.json").read_text())}
        except (OSError, json.JSONDecodeError):
            problems.append(f"{agent}: folder has no matching TestCases/{agent}/cases.json")
            cases = {}
        for it in folder.get("item", []):
            name = it.get("name", "")
            checked += 1
            if not _POSTMAN_NAME_RE.match(name):
                problems.append(f"{agent}: request not named '<TC-id> — <title>': {name!r}")
                continue
            tc_id, title = name.split(" — ", 1)
            if tc_id not in cases:
                problems.append(f"{agent}: {tc_id} has no matching test case in cases.json")
            elif cases[tc_id] != title:
                problems.append(f"{agent}: {tc_id} title differs between Postman and cases.json")
    return {"id": "G18", "name": "postman-testcase-alignment", "hard": True,
            "status": "FAIL" if problems else "PASS",
            "detail": "; ".join(problems[:6]) or f"all {checked} requests named '<TC-id> — <title>' and aligned 1:1 with TestCases."}


def _request_parser():
    """The single source of truth for 'is this test case an API call?' — core_postman._parse_request."""
    sys.path.insert(0, str(WS / "agents" / "common"))
    import core_postman as CP
    return CP._parse_request


def g19_postman_coverage(out_root: Path = None) -> dict:
    """HARD: every test case that is an API call (its steps contain 'Send <METHOD> /path') MUST
    appear as a request in its agent's folder in the collection. This makes ALL recorded API calls
    follow the agent-folder → test_case_id flow; an agent whose cases aren't API calls requires none."""
    if out_root is None:
        out_root = _latest_run_dir()
    col_path = (out_root / "Postman" / "collection.json") if out_root else None
    tc_root = (out_root / "TestCases") if out_root else None
    if not col_path or not col_path.exists():
        return {"id": "G19", "name": "postman-coverage", "hard": True, "status": "FAIL",
                "detail": "Postman/collection.json missing."}
    try:
        c = json.loads(col_path.read_text())
    except (OSError, json.JSONDecodeError) as e:
        return {"id": "G19", "name": "postman-coverage", "hard": True, "status": "FAIL",
                "detail": f"collection.json not valid JSON: {e}"}
    parse = _request_parser()
    in_col: dict[str, set] = {}
    for f in c.get("item", []):
        in_col[f.get("name", "")] = {it["name"].split(" — ", 1)[0]
                                     for it in f.get("item", []) if " — " in it.get("name", "")}
    problems, required_total = [], 0
    for agent_dir in sorted(p for p in (tc_root.iterdir() if tc_root and tc_root.is_dir() else []) if p.is_dir()):
        agent = agent_dir.name
        try:
            cases = json.loads((agent_dir / "cases.json").read_text())
        except (OSError, json.JSONDecodeError):
            continue
        required = {cc["test_case_id"] for cc in cases if parse(cc) is not None}
        required_total += len(required)
        missing = required - in_col.get(agent, set())
        if missing:
            problems.append(f"{agent}: {len(missing)} API-call test case(s) absent from collection "
                            f"e.g. {sorted(missing)[:3]}")
    return {"id": "G19", "name": "postman-coverage", "hard": True,
            "status": "FAIL" if problems else "PASS",
            "detail": "; ".join(problems[:6]) or f"all {required_total} API-call test cases present in the collection."}


def g20_deliverable_separation(out_root: Path = None) -> dict:
    """HARD: the per-run deliverable tree keeps TEST CASES and BUG REPORTS in SEPARATE folders and
    ships a Postman collection. Concretely, for results/<date>/<time>/:
      - TestCases/ exists and holds >=1 <agent>/cases.json (test cases ARE a first-class deliverable,
        not merely a by-product hidden under runs/ or mixed into the bug folder);
      - Postman/collection.json exists;
      - every agent that appears under BugReport/ ALSO appears under TestCases/ (a bug can never be the
        only place an agent's cases live — the test case it came from must be in TestCases);
      - no loose cases.json sits directly under the dated root or directly under BugReport/ (files live
        inside <agent>/ dirs).
    This is the gate that encodes 'test cases in their own TestCases/ folder, separate from BugReport/,
    plus a Postman collection' — it must hold after every full-orchestration finalize."""
    if out_root is None:
        out_root = _latest_run_dir()
    if out_root is None:
        return {"id": "G20", "name": "deliverable-separation", "hard": True, "status": "FAIL",
                "detail": "no dated run tree found under results/."}
    tc_root, br_root, pm = out_root / "TestCases", out_root / "BugReport", out_root / "Postman"
    problems: list[str] = []

    def _agents_with_cases(root: Path) -> set:
        if not root.is_dir():
            return set()
        return {p.name for p in root.iterdir()
                if p.is_dir() and p.name not in _LAYOUT_IGNORE and (p / "cases.json").is_file()}

    def _bug_agents(root: Path) -> set:
        """Agents under BugReport/, in either shape: System-B (cases.json) or System-A
        (verified_bugs/). The top-level unverified/ tree, index files, and artifact dirs are not
        agents (unverified bugs are grouped by category, with finding_agent recorded per report)."""
        if not root.is_dir():
            return set()
        out = set()
        for p in root.iterdir():
            if (not p.is_dir() or p.name in _LAYOUT_IGNORE or p.name in _BUGREPORT_ARTIFACT_DIRS
                    or p.name == "unverified"):
                continue
            names = {f.name for f in p.iterdir()}
            if (p / "cases.json").is_file() or "verified_bugs" in names:
                out.add(p.name)
        return out

    tc_agents = _agents_with_cases(tc_root)
    if not tc_root.is_dir():
        problems.append("missing TestCases/ (test cases must be their own deliverable folder)")
    elif not tc_agents:
        problems.append("TestCases/ has no <agent>/cases.json")
    if not (pm / "collection.json").is_file():
        problems.append("missing Postman/collection.json")
    if br_root.is_dir():
        br_agents = _bug_agents(br_root)
        orphan_bugs = sorted(br_agents - tc_agents)
        if orphan_bugs:
            problems.append(f"BugReport agent(s) with no TestCases entry (test cases only in the bug "
                            f"folder): {orphan_bugs}")
        # loose cases.json directly under BugReport/ (not inside an <agent>/ dir)
        if (br_root / "cases.json").is_file():
            problems.append("loose cases.json directly under BugReport/ (must be BugReport/<agent>/)")
    if (tc_root / "cases.json").is_file():
        problems.append("loose cases.json directly under TestCases/ (must be TestCases/<agent>/)")
    if (out_root / "cases.json").is_file():
        problems.append("loose cases.json directly under the dated root")
    return {"id": "G20", "name": "deliverable-separation", "hard": True,
            "status": "FAIL" if problems else "PASS",
            "detail": "; ".join(problems)
                      or (f"TestCases/ ({len(tc_agents)} agents) + Postman/collection.json present and "
                          f"separate from BugReport/.")}


def core_gate(out_root: Path = None) -> list:
    """The deliverable gate set: layout (G13) + the Core-Requirements coverage/Postman gates +
    the TestCases/BugReport/Postman separation gate (G20)."""
    return [g13_results_layout(), g14_auth_lifecycle(out_root), g15_crud_products(out_root),
            g16_search_coverage(out_root), g17_postman(out_root),
            g18_postman_testcase_alignment(out_root), g19_postman_coverage(out_root),
            g20_deliverable_separation(out_root), g22_no_bug_index_files(out_root),
            g24_evidence_authenticity(out_root), g25_unverified_layout(out_root),
            g26_documented_expectation(out_root)]


def g22_no_bug_index_files(out_root: Path = None) -> dict:
    """HARD: no index/manifest file may exist under BugReport/. The per-bug JSONs are the single
    source of truth; verified-index.json / unverified-index.json / index.json must NOT be created.
    Any file under BugReport whose name matches '*-index.json' or 'index.json' fails this gate."""
    if out_root is None:
        out_root = _latest_run_dir()
    if out_root is None:
        return {"id": "G22", "name": "no-bug-index-files", "hard": True, "status": "PASS",
                "detail": "no dated run tree (nothing to validate)."}
    br = out_root / "BugReport"
    offenders = sorted(str(p.relative_to(out_root)) for p in br.rglob("*.json")
                       if _FORBIDDEN_BUG_INDEX_RE.match(p.name)) if br.is_dir() else []
    return {"id": "G22", "name": "no-bug-index-files", "hard": True,
            "status": "FAIL" if offenders else "PASS",
            "detail": (f"forbidden index file(s) under BugReport (delete them; the bug JSONs are the "
                       f"source of truth): {offenders}" if offenders
                       else "no index/manifest files under BugReport.")}


def g23_results_clean() -> dict:
    """HARD: after a completed run's tidy, results/ holds ONLY dated deliverable dirs (YYYY-MM-DD)
    and the tolerated _global/ (code-review) — no runs/, no legacy bug-reports/, no loose
    test-case-registry*.json. These are deleted as soon as the deliverable is built."""
    results = WS / "results"
    if not results.is_dir():
        return {"id": "G23", "name": "results-clean", "hard": True, "status": "PASS",
                "detail": "results/ absent (nothing to validate)."}
    strays = sorted(e.name for e in results.iterdir()
                    if e.name not in _RESULTS_KEEP and e.name != ".DS_Store"
                    and "code-review" not in e.name
                    and not (e.is_dir() and _DATE_RE.match(e.name)))
    return {"id": "G23", "name": "results-clean", "hard": True,
            "status": "FAIL" if strays else "PASS",
            "detail": (f"non-deliverable entries left under results/ (should be deleted post-run): "
                       f"{strays}" if strays else "results/ holds only <date>/ deliverables + _global.")}


_PNG_MAGIC = b"\x89PNG\r\n\x1a\n"
# server-log origin markers — a captured log must contain the target's OWN request-logger output,
# not the agent's test-runner stdout/stderr.
_SERVER_LOG_MARKERS = ("HTTP Request", "response_time_ms", "SERVER LOG (origin:")


def _is_real_video(path: Path) -> bool:
    """True when the file is a real, multi-frame video (a watchable screen recording): an MP4
    (ISO Base Media 'ftyp' box) or an animated GIF (>1 frame). Single-image files fail."""
    try:
        head = path.read_bytes()[:32]
    except OSError:
        return False
    if head[4:8] == b"ftyp":                      # MP4/MOV
        return path.stat().st_size > 1024
    if head[:6] in (b"GIF87a", b"GIF89a"):        # GIF — require animation (multiple frames)
        try:
            from PIL import Image
            with Image.open(path) as im:
                return getattr(im, "n_frames", 1) > 1
        except Exception:  # noqa: BLE001
            return False
    return False


def _cast_shows_steps(path: Path) -> bool:
    """True when an asciinema .cast is a real recording of the reproduction: a v2 header plus
    output events that include an executed command ('$ ' / 'curl') AND a response line
    (an HTTP status or a curl error) — i.e. not a single static frame. (Text fallback used only
    when ffmpeg is unavailable to encode an MP4.)"""
    try:
        lines = path.read_text().splitlines()
        header = json.loads(lines[0])
    except (OSError, ValueError, IndexError):
        return False
    if header.get("version") != 2:
        return False
    body = "".join(json.loads(ln)[2] for ln in lines[1:]
                   if ln.strip().startswith("[")) if len(lines) > 1 else ""
    has_cmd = ("curl" in body) or ("$ " in body)
    has_resp = ("HTTP" in body) or ("curl:" in body)
    return has_cmd and has_resp and len(lines) - 1 >= 5


def _is_real_recording(path: Path) -> bool:
    """A valid reproduction recording: a real watchable video (MP4/animated GIF) or, only as a
    fallback, a stepped asciinema .cast."""
    if path.suffix.lower() in (".mp4", ".mov", ".gif"):
        return _is_real_video(path)
    if path.suffix.lower() == ".cast":
        return _cast_shows_steps(path)
    return False


def g24_evidence_authenticity(out_root: Path = None) -> dict:
    """HARD: every bug's captured evidence is REAL, not a placeholder.
      - screenshot: an actual PNG of the reproduction (PNG magic bytes) — never a '*-replay.txt'.
      - recording: a real, watchable screen recording of the reproduction — an MP4 (or animated
        GIF); a stepped asciinema .cast is accepted only as a fallback when ffmpeg is unavailable.
        A single static image / non-animated file fails.
      - log: BEST-EFFORT (like db_dump) — when a report references a log it must contain the
        target server's OWN request-logger output, not the test runner's stdout. A report with no
        log is allowed (the server may not have been capturable), but a referenced log that is
        empty or non-server-origin fails.
    A single placeholder screenshot (a .txt), a static cast, or a non-server log fails the gate."""
    if out_root is None:
        out_root = _latest_run_dir()
    if out_root is None:
        return {"id": "G24", "name": "evidence-authenticity", "hard": True, "status": "PASS",
                "detail": "no dated run tree (nothing to validate)."}
    tree = out_root / "BugReport"
    if not tree.is_dir():
        return {"id": "G24", "name": "evidence-authenticity", "hard": True, "status": "PASS",
                "detail": "no BugReport tree (nothing to validate)."}
    # any leftover text-replay placeholder screenshot is an immediate fail
    replays = [str(p.relative_to(out_root)) for p in tree.rglob("*-replay.txt")]
    bugs = [p for p in tree.rglob("*.json")
            if ("/verified_bugs/" in str(p) or "/unverified/" in str(p))
            and p.stem[:1] in "BVSb"]  # BUG-/VULN-/BIZ-/SW-
    bad_shot, bad_cast, bad_log, n = [], [], [], 0
    for bf in bugs:
        try:
            d = json.loads(bf.read_text())
        except (OSError, ValueError):
            continue
        n += 1
        atts = d.get("attachments") or {}
        arts = d.get("artifacts") or {}
        bid = d.get("id") or d.get("bug_id")
        shot = atts.get("screenshot") or arts.get("screenshot_path")
        cast = atts.get("recording") or arts.get("recording_path")
        log = atts.get("log") or arts.get("log_path")
        sp = (out_root / shot) if shot else None
        if not sp or not sp.is_file() or sp.read_bytes()[:8] != _PNG_MAGIC:
            bad_shot.append(bid)
        cp = (out_root / cast) if cast else None
        if not cp or not cp.is_file() or not _is_real_recording(cp):
            bad_cast.append(bid)
        if log:  # referenced => must be real server output (best-effort means it may be absent)
            lp = out_root / log
            txt = lp.read_text(errors="replace") if lp.is_file() else ""
            if not any(m in txt for m in _SERVER_LOG_MARKERS):
                bad_log.append(bid)
    problems = []
    if replays:
        problems.append(f"{len(replays)} placeholder '*-replay.txt' screenshot(s) present")
    if bad_shot:
        problems.append(f"{len(bad_shot)} bug(s) without a real PNG screenshot: {bad_shot[:5]}")
    if bad_cast:
        problems.append(f"{len(bad_cast)} bug(s) without a real video recording: {bad_cast[:5]}")
    if bad_log:
        problems.append(f"{len(bad_log)} referenced log(s) not server-origin: {bad_log[:5]}")
    return {"id": "G24", "name": "evidence-authenticity", "hard": True,
            "status": "FAIL" if problems else "PASS",
            "detail": ("; ".join(problems) if problems else
                       f"all {n} bug(s): real PNG screenshot + watchable video recording + "
                       f"server-origin logs where captured.")}


# canonical id-prefix -> category folder (kept local so guardrails has no cross-package import)
_UNVERIFIED_PREFIX_TO_CATEGORY = {"VULN": "vulnerability", "BIZ": "business-workflow",
                                  "SW": "computer-software"}
_UNVERIFIED_ID_RE = re.compile(r"^(VULN|BIZ|SW)-")


def g25_unverified_layout(out_root: Path = None) -> dict:
    """HARD: every UNVERIFIED bug lives in the single top-level tree
    BugReport/unverified/{category}/{PREFIX}-*.json, with its screenshot/recording/logs co-located
    under BugReport/unverified/{category}/{screenshots,recordings,logs}/. Concretely:
      - the legacy per-agent layout BugReport/<agent>/unverified_bugs/ is FORBIDDEN (none may exist);
      - no unverified report (id VULN-/BIZ-/SW-) may sit under a verified_bugs/ dir or any per-agent
        dir — only under BugReport/unverified/{category}/;
      - the {category} path segment equals the report's `category` field AND the id prefix
        (VULN→vulnerability, BIZ→business-workflow, SW→computer-software);
      - finding_agent is non-empty (the owning agent, since it is no longer in the path);
      - every referenced artifact (screenshot/recording/log) is co-located under
        BugReport/unverified/{category}/.
    A run with no unverified bugs passes trivially."""
    if out_root is None:
        out_root = _latest_run_dir()
    if out_root is None:
        return {"id": "G25", "name": "unverified-layout", "hard": True, "status": "PASS",
                "detail": "no dated run tree (nothing to validate)."}
    tree = out_root / "BugReport"
    if not tree.is_dir():
        return {"id": "G25", "name": "unverified-layout", "hard": True, "status": "PASS",
                "detail": "no BugReport tree (nothing to validate)."}
    problems: list = []
    # 1. legacy per-agent unverified layout must not exist
    legacy = [str(p.relative_to(out_root)) for p in tree.rglob("unverified_bugs") if p.is_dir()]
    if legacy:
        problems.append(f"legacy per-agent unverified_bugs/ dir(s) present (move to "
                        f"BugReport/unverified/): {legacy[:5]}")
    # 2. no unverified-id report outside BugReport/unverified/
    stray = [str(p.relative_to(out_root)) for p in tree.rglob("*.json")
             if _UNVERIFIED_ID_RE.match(p.stem) and "/unverified/" not in str(p)]
    if stray:
        problems.append(f"unverified report(s) not under BugReport/unverified/: {stray[:5]}")
    # 3. validate each report under unverified/{category}/
    uv_root = tree / "unverified"
    n = 0
    if uv_root.is_dir():
        for cat_dir in sorted(p for p in uv_root.iterdir() if p.is_dir()):
            cat = cat_dir.name
            for rp in sorted(cat_dir.glob("*.json")):
                n += 1
                try:
                    d = json.loads(rp.read_text())
                except (OSError, ValueError):
                    problems.append(f"unreadable unverified report {rp.name}")
                    continue
                bid = d.get("bug_id") or ""
                pref = bid.split("-", 1)[0]
                want_cat = _UNVERIFIED_PREFIX_TO_CATEGORY.get(pref)
                if want_cat != cat or d.get("category") != cat:
                    problems.append(f"{rp.name}: category mismatch (folder={cat}, "
                                    f"field={d.get('category')}, id-prefix→{want_cat})")
                if not d.get("finding_agent"):
                    problems.append(f"{rp.name}: empty finding_agent")
                arts = d.get("artifacts") or {}
                atts = d.get("attachments") or {}
                for got in (arts.get("screenshot_path") or atts.get("screenshot"),
                            arts.get("recording_path") or atts.get("recording"),
                            arts.get("log_path") or atts.get("log")):
                    if got and not got.startswith(f"BugReport/unverified/{cat}/"):
                        problems.append(f"{rp.name}: artifact not co-located under "
                                        f"unverified/{cat}/ ({got})")
    return {"id": "G25", "name": "unverified-layout", "hard": True,
            "status": "FAIL" if problems else "PASS",
            "detail": ("; ".join(problems[:8]) if problems else
                       f"all {n} unverified bug(s) under BugReport/unverified/<category>/ with "
                       f"category-consistent ids and co-located artifacts.")}


# Vague placeholder phrases a documentation-cited expected_result must NEVER contain — it must
# state the documented behavior, not defer to it.
_VAGUE_EXPECTED_PHRASES = (
    "pass against the documented behaviour",
    "pass against the documented behavior",
    "the documented behaviour for this scenario",
    "the documented behavior for this scenario",
    "an incorrect result",
    "meets its pass threshold",
)
_EXPECTED_STOPWORDS = {
    "the", "a", "an", "and", "or", "of", "to", "in", "on", "for", "with", "is", "are", "be",
    "must", "should", "will", "can", "this", "that", "these", "those", "per", "documentation",
    "documented", "behaviour", "behavior", "every", "scenario", "check", "checks", "conform",
    "all", "get", "use", "used", "you", "your", "it", "its", "as", "by", "from", "at", "each",
}


def _sig_words(text: str) -> set:
    """Significant content words (lowercased, len>=3, non-stopword) for grounding comparison."""
    toks = re.findall(r"[A-Za-z0-9_]+", (text or "").lower())
    return {t for t in toks if len(t) >= 3 and t not in _EXPECTED_STOPWORDS}


def g26_documented_expectation(out_root: Path = None) -> dict:
    """HARD: every VERIFIED (documentation-cited) bug's expected_result must state the documented
    behavior in its own words, not defer to it vaguely. For each bug whose documentation.cited is
    true:
      - expected_result must be non-empty and must NOT contain a vague placeholder phrase
        (e.g. 'All N checks pass against the documented behaviour');
      - it must be GROUNDED in the cited documentation — it shares enough significant content words
        with documentation.text to be a reworded version of it (not generic boilerplate).
    Unverified/uncited bugs are out of scope (their expectation is the universal contract, not a
    doc citation). A run with no verified bugs passes trivially."""
    if out_root is None:
        out_root = _latest_run_dir()
    if out_root is None:
        return {"id": "G26", "name": "documented-expectation", "hard": True, "status": "PASS",
                "detail": "no dated run tree (nothing to validate)."}
    tree = out_root / "BugReport"
    if not tree.is_dir():
        return {"id": "G26", "name": "documented-expectation", "hard": True, "status": "PASS",
                "detail": "no BugReport tree (nothing to validate)."}
    vague, ungrounded, n = [], [], 0
    for rp in sorted(tree.rglob("verified_bugs/*.json")):
        try:
            d = json.loads(rp.read_text())
        except (OSError, ValueError):
            continue
        doc = d.get("documentation") or {}
        if not doc.get("cited"):
            continue
        n += 1
        bid = d.get("id") or d.get("bug_id")
        exp = (d.get("expected_result") or "").strip()
        low = exp.lower()
        if not exp or any(p in low for p in _VAGUE_EXPECTED_PHRASES):
            vague.append(bid)
            continue
        # grounding: the expected must share enough content words with the cited doc text to be a
        # reworded version of it (verbatim embed → full overlap; a genuine rewording → partial).
        doc_words = _sig_words(doc.get("text", ""))
        exp_words = _sig_words(exp)
        shared = doc_words & exp_words
        # Grounding floor: at least one shared content word, scaling to ~a quarter of the doc's
        # content words for longer citations. Loose enough that a genuine synonym-rewording passes,
        # strict enough that generic boilerplate sharing nothing with the doc fails.
        need = max(1, len(doc_words) // 4)
        if doc_words and len(shared) < min(need, len(doc_words)):
            ungrounded.append(bid)
    problems = []
    if vague:
        problems.append(f"{len(vague)} verified bug(s) with a vague/placeholder expected_result: {vague[:5]}")
    if ungrounded:
        problems.append(f"{len(ungrounded)} verified bug(s) whose expected_result is not grounded in "
                        f"the cited documentation: {ungrounded[:5]}")
    return {"id": "G26", "name": "documented-expectation", "hard": True,
            "status": "FAIL" if problems else "PASS",
            "detail": ("; ".join(problems) if problems else
                       f"all {n} verified bug(s) state the documented behavior (reworded from the "
                       f"cited docs), no vague placeholders.")}


def deliverable_gate(out_root: Path) -> list:
    """The per-run HARD subset used by the full-orchestration finalize to decide BROKEN. Excludes the
    global G13 (which polices the WHOLE results/ dir for legacy strays — a separate cleanliness concern);
    every gate here is scoped to THIS run's out_root, so a clean full run can always satisfy it."""
    return [g14_auth_lifecycle(out_root), g15_crud_products(out_root), g16_search_coverage(out_root),
            g17_postman(out_root), g18_postman_testcase_alignment(out_root),
            g19_postman_coverage(out_root), g20_deliverable_separation(out_root),
            g22_no_bug_index_files(out_root), g24_evidence_authenticity(out_root),
            g25_unverified_layout(out_root), g26_documented_expectation(out_root)]


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
        g21_no_silent_empty(rows),
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
