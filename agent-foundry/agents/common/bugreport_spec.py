"""Canonical structure for the API "Bug Reporter" task (general position, "n602").

ONE definition of the per-failure bug-report DECISION + the per-field evaluation, shared
by:
  - the deterministic gold reference (data/bug-reporter/build_gold.py), and
  - the harness (agents/common/bugreport.py) — which materialises the file artifacts,
    assembles the bug reports, and scores whatever DECISION an agent emitted on exactly
    the same (failure x field) key scheme.

Pure: no env, no I/O, no LLM, no HTTP, no subprocess. Keeps agent output and the gold
decisions on the same key scheme so the judge can compare them field-for-field.

What the agent actually does (the measurable analytical core). The full "Bug Reporter"
task (read pipeline-summary -> for every non-PASSED agent collect ten artifacts ->
write results/bug-reports/[BUG_ID].json + index.json -> exit 1 on any CRITICAL/HIGH)
splits into two halves:

  * the DETERMINISTIC half — read the pipeline summary, the registry, the Postman
    collection and the config; generate BUG_ID + CREATED_AT; MATERIALISE the four FILE
    artifacts (the replay screenshot, the asciinema recording, the concatenated logs,
    and — only when a [database] is configured — the schema dump); assemble the final
    bug-report JSON; write the consolidated index; and set the process exit code — is
    the harness/CI program's job, and the agent is debate-gated against performing any
    of it (no file writes, no convert/pg_dump/asciinema/Newman subprocess, no HTTP).

  * the ANALYTICAL half — given ONE failed agent's captured artifacts (its status,
    exit_code, spec_path, stderr/stdout, its registry test cases, and the Postman
    lookup), decide the bug report's judgement fields: the title, the severity (by the
    nine ordered rules), the priority, the mapped testing_steps, and the
    postman_references (existing-item refs + constructed v2.1 new_items) — is the
    agent's job. This is what the four frameworks implement and what the judge measures,
    mirroring the run-cicd-pipeline / run-regression-suite precedent (the agent emits
    the report; a separate program acts on it).

DummyJSON is NOT touched and NOT used: n602 is a pure transform over the local
results/* JSON fixtures; it makes no HTTP calls of its own.

The severity contract (the exact ordered rules the agent must reproduce; FIRST match
wins). The task prose has two garbled clauses; the debate gate pins them:
  R1 CRITICAL  spec_path contains "authentication"/"authorization" (case-insensitive)
               — every record reaching the reporter is already a failure, so the
               garbled "AND F.status ." clause is satisfied by definition.
  R2 CRITICAL  stderr contains any of the six exact security substrings.
  R3 CRITICAL  status TIMED_OUT and spec_path contains "pipeline".
  R4 HIGH      status FAILED and stdout is valid JSON with numeric
               false_acceptance_rate > 0.
  R5 HIGH      status FAILED and stderr contains any of 500/503/database/
               connection refused/schema validation/CRUD.
  R6 HIGH      status MALFORMED.
  R7 MEDIUM    status FAILED and stderr contains any of 400/404/pagination/sorting/
               filter/timeout/rate limit/idempotency.
  R8 MEDIUM    status TIMED_OUT and agent_name does not contain "pipeline".
  R9 LOW       any failure matching none of the above.
priority maps CRITICAL->P1, HIGH->P2, MEDIUM->P3, LOW->P4.

Metric — Bug Report Completeness Rate = sum(complete_artifact_count) /
(reports x 10) x 100; pass >= 80%. The forge judge ranks the four frameworks on
Bug-Report Fidelity (the fraction of failure x decision-field cells matching gold)
because the headline completeness rate is a property of the fixtures + the harness's
artifact materialisation, not the framework.
"""
from __future__ import annotations

import json
import re

# --------------------------------------------------------------------------- #
# Canonical extraction constants (Artifact 2, verbatim from the spec)
# --------------------------------------------------------------------------- #
METHOD_PATTERN = r"\b(GET|POST|PUT|DELETE|PATCH|HEAD)\b"
DEFAULT_METHOD = "GET"
PATH_PATTERN = r"(\/[\w\-\.{}\/]+)"
DEFAULT_PATH = "/unknown"
BODY_TRIGGERS = ["with body", "body =", "body:"]
STATUS_PATTERN = r"(?:assert(?:s)?\s+(?:exactly\s+)?|→\s*assert\s+(?:exactly\s*)?)([1-9][0-9]{2})"

# The exact stderr substrings driving each severity rule (verbatim, order-significant).
SEC_CRITICAL_SUBSTRINGS = [
    "False Acceptance Rate", "SQL injection", "data exposed",
    "allowlist bypass", "TLS handshake", "certificate expired",
]
HIGH_STDERR_SUBSTRINGS = ["500", "503", "database", "connection refused",
                          "schema validation", "CRUD"]
MEDIUM_STDERR_SUBSTRINGS = ["400", "404", "pagination", "sorting", "filter",
                            "timeout", "rate limit", "idempotency"]

TITLE_MAX = 120

# The five decision keys the agent emits, in order. Each is one scored cell per failure.
DECISION_FIELDS = ["title", "severity", "priority", "testing_steps", "postman_references"]

SEVERITY_TO_PRIORITY = {"CRITICAL": "P1", "HIGH": "P2", "MEDIUM": "P3", "LOW": "P4"}

# The ten artifact-completeness keys (Artifact assembly). created_at/title/severity/
# priority are never null; the rest depend on the harness materialisation.
COMPLETENESS_FIELDS = [
    "testing_steps", "postman_references", "screenshot", "recording",
    "logs", "db_dump", "created_at", "title", "severity", "priority",
]


# --------------------------------------------------------------------------- #
# Helpers
# --------------------------------------------------------------------------- #
def first_nonempty_line(text: str) -> str:
    for ln in (text or "").splitlines():
        if ln.strip():
            return ln.strip()
    return ""


def stdout_far(stdout: str):
    """Return the numeric false_acceptance_rate if stdout parses as a JSON object that
    carries one, else None."""
    try:
        doc = json.loads(stdout)
    except Exception:  # noqa
        return None
    if isinstance(doc, dict) and isinstance(doc.get("false_acceptance_rate"), (int, float)):
        return doc["false_acceptance_rate"]
    return None


def _contains_any(text: str, needles: list) -> bool:
    t = text or ""
    return any(n in t for n in needles)


# --------------------------------------------------------------------------- #
# Artifact 8 — Title
# --------------------------------------------------------------------------- #
def build_title(failure: dict) -> str:
    name = failure["agent_name"]
    status = failure["status"]
    if status == "TIMED_OUT":
        return f"[{name}] Agent timed out after 300 seconds — no output produced"
    if status == "MALFORMED":
        return f"[{name}] Agent exited 0 but stdout was not valid JSON"
    # FAILED
    line = first_nonempty_line(failure.get("stderr", ""))
    if line:
        return f"[{name}] " + line[:TITLE_MAX]
    return f"[{name}] Agent exited with code {failure.get('exit_code')} — stderr empty"


# --------------------------------------------------------------------------- #
# Artifact 9 — Severity (nine ordered rules, first match wins)  &  Artifact 10 — Priority
# --------------------------------------------------------------------------- #
def build_severity(failure: dict) -> str:
    spec_path = (failure.get("spec_path") or "").lower()
    status = failure["status"]
    stderr = failure.get("stderr", "")
    name = failure["agent_name"]

    # R1
    if "authentication" in spec_path or "authorization" in spec_path:
        return "CRITICAL"
    # R2
    if _contains_any(stderr, SEC_CRITICAL_SUBSTRINGS):
        return "CRITICAL"
    # R3
    if status == "TIMED_OUT" and "pipeline" in spec_path:
        return "CRITICAL"
    # R4
    if status == "FAILED":
        far = stdout_far(failure.get("stdout", ""))
        if far is not None and far > 0:
            return "HIGH"
    # R5
    if status == "FAILED" and _contains_any(stderr, HIGH_STDERR_SUBSTRINGS):
        return "HIGH"
    # R6
    if status == "MALFORMED":
        return "HIGH"
    # R7
    if status == "FAILED" and _contains_any(stderr, MEDIUM_STDERR_SUBSTRINGS):
        return "MEDIUM"
    # R8
    if status == "TIMED_OUT" and "pipeline" not in name:
        return "MEDIUM"
    # R9
    return "LOW"


def build_priority(severity: str) -> str:
    return SEVERITY_TO_PRIORITY[severity]


# --------------------------------------------------------------------------- #
# Artifact 1 — Testing steps (mapped from the registry, sorted by tc_id)
# --------------------------------------------------------------------------- #
STEP_KEYS = ["tc_id", "step_id", "step_text", "involves_http_call",
             "involves_assertion", "expected_outcome", "fail_condition"]


def agent_tcs(registry: list, agent_name: str) -> list:
    """The registry test cases for one agent, sorted by tc_id ascending."""
    rows = [tc for tc in (registry or []) if tc.get("agent") == agent_name]
    return sorted(rows, key=lambda tc: str(tc.get("tc_id", "")))


def build_testing_steps(tcs: list):
    if not tcs:
        return None
    return [{k: tc.get(k) for k in STEP_KEYS} for tc in tcs]


# --------------------------------------------------------------------------- #
# Artifact 2 — Postman references (existing-item ref OR constructed v2.1 new_item)
# --------------------------------------------------------------------------- #
def extract_method(text: str) -> str:
    m = re.search(METHOD_PATTERN, text or "")
    return m.group(1) if m else DEFAULT_METHOD


def extract_path(text: str) -> str:
    m = re.search(PATH_PATTERN, text or "")
    return m.group(1) if m else DEFAULT_PATH


def extract_status(text: str) -> int:
    m = re.search(STATUS_PATTERN, text or "")
    if m:
        try:
            return int(m.group(1))
        except (ValueError, IndexError):
            return 0
    return 0


def _path_array(url_path: str) -> list:
    return [seg for seg in (url_path or "").split("/") if seg]


def _new_item_headers(text: str, body_mode: str) -> list:
    headers = [{"key": "Authorization", "value": "{{auth_token}}"}]
    if "X-Correlation-ID" in (text or ""):
        headers.append({"key": "X-Correlation-ID", "value": "{{corr_id}}"})
    if body_mode == "raw":
        headers.append({"key": "Content-Type", "value": "application/json"})
    return headers


def _test_script(expected_status: int) -> list:
    return [
        (f'pm.test("Status code is {expected_status}", function() {{ '
         f'pm.response.to.have.status({expected_status}); }});'),
        ('pm.test("Response time < 5000ms", function() { '
         'pm.expect(pm.response.responseTime).to.be.below(5000); });'),
    ]


def build_new_item(tc: dict) -> dict:
    """Construct a Postman v2.1 request item for an HTTP test case absent from the
    collection (Artifact 2, verbatim from the spec)."""
    tc_id = tc.get("tc_id", "")
    text = tc.get("step_text", "")
    method = extract_method(text)
    url_path = extract_path(text)
    body_mode = "raw" if _contains_any(text, BODY_TRIGGERS) else "none"
    if body_mode == "raw":
        body = {"mode": "raw", "raw": "{}", "options": {"raw": {"language": "json"}}}
    else:
        body = {"mode": "none"}
    headers = _new_item_headers(text, body_mode)
    expected_status = extract_status(text)
    return {
        "name": tc_id,
        "request": {
            "method": method,
            "header": headers,
            "url": {
                "raw": "{{base_url}}" + url_path,
                "host": ["{{base_url}}"],
                "path": _path_array(url_path),
            },
            "body": body,
        },
        "event": [{
            "listen": "test",
            "script": {"type": "text/javascript", "exec": _test_script(expected_status)},
        }],
    }


def build_postman_references(failure: dict, tcs: list, postman_items: dict) -> list:
    """One ref per HTTP test case of this agent, in testing-steps (tc_id) order.

    postman_items: {tc_id -> {"folder": str, "item_name": str}} built from the collection.
    """
    refs = []
    for tc in tcs:
        if tc.get("involves_http_call") is not True:
            continue
        tc_id = tc.get("tc_id")
        if tc_id in (postman_items or {}):
            refs.append({
                "exists_in_collection": True,
                "folder": postman_items[tc_id].get("folder"),
                "item_name": tc_id,
                "new_item": None,
            })
        else:
            refs.append({
                "exists_in_collection": False,
                "folder": failure["agent_name"],
                "item_name": tc_id,
                "new_item": build_new_item(tc),
            })
    return refs


# --------------------------------------------------------------------------- #
# The full per-failure decision (gold reference / what the agent must emit)
# --------------------------------------------------------------------------- #
def build_reference_decision(failure: dict, registry: list, postman_items: dict) -> dict:
    """The canonical CORRECT five-key decision for one failure, derived deterministically.
    An agent that emits this decision reproduces the gold report's judgement fields."""
    tcs = agent_tcs(registry, failure["agent_name"])
    severity = build_severity(failure)
    return {
        "title": build_title(failure),
        "severity": severity,
        "priority": build_priority(severity),
        "testing_steps": build_testing_steps(tcs),
        "postman_references": build_postman_references(failure, tcs, postman_items),
    }


def build_postman_items(collection: dict) -> dict:
    """Walk a Postman v2.1 collection -> {item_name -> {folder, item_name}}.

    The folder is the name of the parent folder object one level up (the object whose
    'item' array holds this request node)."""
    out: dict = {}

    def walk(node, parent_folder):
        if isinstance(node, dict):
            folder = node.get("name") if "item" in node and "request" not in node else parent_folder
            if "request" in node and node.get("name") is not None:
                out[node["name"]] = {"folder": parent_folder, "item_name": node["name"]}
            for k, v in node.items():
                walk(v, folder if k == "item" else parent_folder)
        elif isinstance(node, list):
            for v in node:
                walk(v, parent_folder)

    walk(collection or {}, None)
    return out


# --------------------------------------------------------------------------- #
# Per-field scoring (agent decision vs gold decision) — the fidelity cells
# --------------------------------------------------------------------------- #
def _steps_key(steps):
    """Comparable shape for a testing_steps value (None or list of dicts)."""
    if steps is None:
        return None
    if not isinstance(steps, list):
        return "INVALID"
    return [tuple((str(s.get(k)) if isinstance(s, dict) else None) for k in STEP_KEYS)
            for s in steps]


def _refs_key(refs):
    """Comparable shape for postman_references: the ordered (item_name, exists, method,
    path, status-line) tuples — the load-bearing facts, ignoring incidental key order."""
    if not isinstance(refs, list):
        return "INVALID"
    out = []
    for r in refs:
        if not isinstance(r, dict):
            out.append(("BAD",))
            continue
        ni = r.get("new_item") or {}
        req = ni.get("request") or {} if isinstance(ni, dict) else {}
        url = req.get("url") or {}
        ev = ni.get("event") or [] if isinstance(ni, dict) else []
        exec_lines = tuple(((ev[0] or {}).get("script") or {}).get("exec", [])) if ev else ()
        out.append((
            str(r.get("item_name")),
            bool(r.get("exists_in_collection")),
            str(r.get("folder")),
            str(req.get("method")) if req else None,
            str(url.get("raw")) if url else None,
            exec_lines,
        ))
    return out


def score_decision(agent_decision: dict, gold_decision: dict) -> dict:
    """Return {field: bool} for each of the five DECISION_FIELDS — whether the agent's
    value matches gold."""
    a = agent_decision if isinstance(agent_decision, dict) else {}
    cells: dict = {}
    cells["title"] = str(a.get("title")) == str(gold_decision["title"])
    cells["severity"] = str(a.get("severity")) == str(gold_decision["severity"])
    cells["priority"] = str(a.get("priority")) == str(gold_decision["priority"])
    cells["testing_steps"] = _steps_key(a.get("testing_steps")) == _steps_key(gold_decision["testing_steps"])
    cells["postman_references"] = _refs_key(a.get("postman_references")) == _refs_key(gold_decision["postman_references"])
    return cells


# --------------------------------------------------------------------------- #
# Task metrics (computed over the assembled reports)
# --------------------------------------------------------------------------- #
def completeness_count(completeness: dict) -> int:
    return sum(1 for v in completeness.values() if v is True)


def bug_report_completeness_rate(reports: list) -> float:
    """sum(complete_artifact_count) / (reports x 10) x 100. Pass >= 80."""
    if not reports:
        return 0.0
    total = sum(r.get("complete_artifact_count", 0) for r in reports)
    return round(100.0 * total / (len(reports) * 10), 2)


def mandatory_field_rate(reports: list) -> float:
    """% of reports where created_at, title, severity, priority are all non-null. Pass 100."""
    if not reports:
        return 0.0
    ok = 0
    for r in reports:
        if all(r.get(f) not in (None, "") for f in ("created_at", "title", "severity", "priority")):
            ok += 1
    return round(100.0 * ok / len(reports), 2)


def testing_steps_coverage_rate(reports: list) -> float:
    """% of reports whose testing_steps is a non-empty array. Pass >= 95."""
    if not reports:
        return 0.0
    ok = 0
    for r in reports:
        ts = (r.get("artifacts") or {}).get("testing_steps")
        if isinstance(ts, list) and ts:
            ok += 1
    return round(100.0 * ok / len(reports), 2)


def postman_reference_rate(reports: list) -> float:
    """% of HTTP test cases across all reports where exists_in_collection is true. Pass >= 90."""
    total = exists = 0
    for r in reports:
        for ref in (r.get("artifacts") or {}).get("postman_references") or []:
            total += 1
            if ref.get("exists_in_collection") is True:
                exists += 1
    return round(100.0 * exists / total, 2) if total else 100.0


def has_critical_or_high(reports: list) -> bool:
    return any(r.get("severity") in ("CRITICAL", "HIGH") for r in reports)
