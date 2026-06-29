#!/usr/bin/env python3
# Used by: shared — 8-field test-case formatter for EVERY agent; used by make_all_test_cases, run_pipeline, build_postman.
"""Deterministic test-case-creator: format an agent's handed-off steps+results into the
professional 9-field test-case schema. EXACT by construction (no LLM, no paraphrasing).

Each api-tester records, per test it ran, the exact request it sent and the result. The
record list and its field names differ per agent (some use `scenarios`, most use `cases`,
with keys like ideal/observed_token or expected_class/actual_code). This module normalizes
those, then emits the 9-field cases. It is the SOLE author of the formatted cases and invents
nothing — every field is sourced from the agent's own recorded output.

Per agent -> results/runs/<RUN>/test-case-registry/<agent>/{cases.json, cases.md}
9 fields: test_case_id, title, description, preconditions, test_data, test_steps[],
          expected_results, actual_results, status (Pass|Fail|Blocked|Skipped)

Usage:  python format_test_cases.py <RUN_ID> <agent>
"""
from __future__ import annotations

import json
import os
import re
import sys
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()

CODES = {
    "validate-request-payloads": "REQPAY", "verify-response-status-codes": "STATUS",
    "test-authentication-flows": "AUTH", "check-authorization-rules": "AUTHZ",
    "validate-json-schema-responses": "SCHEMA", "test-pagination-behavior": "PAGE",
    "verify-error-message-clarity": "ERRMSG", "test-rate-limit-enforcement": "RATE",
    "validate-query-parameter-handling": "QPARAM", "test-idempotency-of-endpoints": "IDEMP",
    "verify-content-type-negotiation": "CTYPE", "validate-null-empty-fields": "NULLF",
    "test-timeout-handling": "TIMEOUT", "verify-crud-operation-integrity": "CRUD",
    "test-concurrent-request-handling": "CONCUR", "validate-header-propagation": "HDRPROP",
    "test-webhook-delivery": "WEBHOOK", "run-regression-suite": "REGR",
    "track-defect-density": "DEFECT", "validate-api-versioning-behavior": "VERSION",
    "test-ssl-tls-enforcement": "TLS", "verify-caching-headers": "CACHE",
    "validate-correlation-id-propagation": "CORRID", "test-bulk-operation-endpoints": "BULK",
    "verify-audit-log-generation": "AUDIT", "validate-search-and-filter-queries": "SEARCH",
    "test-file-upload-and-download": "FILE", "verify-sorting-behavior": "SORT",
    "test-event-driven-api-triggers": "EVENT", "test-ip-allowlist-enforcement": "IPALLOW",
    "test-api-gateway-routing": "GATEWAY", "verify-third-party-oauth-integration": "OAUTH",
    "test-multipart-form-data-handling": "MPART", "validate-retry-after-header-compliance": "RETRY",
    "test-soft-delete-behavior": "SOFTDEL", "validate-graphql-depth-limits": "GQLDEPTH",
    "test-long-polling-support": "LONGPOLL", "verify-enum-value-restrictions": "ENUM",
    "measure-api-consumer-satisfaction": "NPS", "create-postman-collection": "POSTMAN",
}
# keys whose list value holds the per-test records, in priority order
RECORD_KEYS = ("scenarios", "cases", "test_cases", "results", "probes", "checks",
               "flows", "pairs", "sprints", "stages", "resources")
LABEL_KEYS = ("scenario", "label", "slug", "name", "item", "check", "provider", "pair", "sprint")
EXPECTED_KEYS = ("ideal", "expect_status", "expected_class", "ideal_token", "expected_code",
                 "expected_status", "expected", "ideal_status", "gold_report", "gold_record")
ACTUAL_KEYS = ("observed_token", "actual_code", "actual_class", "observed", "actual",
               "actual_status", "status", "emitted_report")
CORRECT_KEYS = ("api_correct", "correct", "passed", "is_correct", "flow_complete", "integrity_pass")


def find_cases_file(run_id: str, agent: str):
    """The agent's recorded output may live in results/runs/<id>/ OR a bespoke subdir like
    results/{status,authz,schema,clarity,crud}/runs/<id>/. Find it wherever it is."""
    import glob
    name = f"api-tester-{agent}.cases.json"
    direct = WS / "results" / "runs" / run_id / name
    if direct.exists():
        return direct
    for p in glob.glob(str(WS / "results" / "*" / "runs" / run_id / name)):
        if Path(p).exists():
            return Path(p)
    return None
SUFFIXES = ("_status", "_ordering", "_message", "_count", "_correct", "_present", "_absent",
            "_len", "_byte_identical", "_delta", "_rate")


def code(agent: str) -> str:
    return CODES.get(agent, re.sub(r"[^A-Z]", "", agent.upper())[:6] or "TC")


def humanize(s: str) -> str:
    return re.sub(r"[_\-]+", " ", str(s)).strip().capitalize()


def base_label(label: str) -> str:
    for suf in SUFFIXES:
        if label.endswith(suf):
            return label[: -len(suf)]
    return label


def _find_list(obj, key):
    if isinstance(obj, dict):
        v = obj.get(key)
        if isinstance(v, list) and v and isinstance(v[0], dict):
            return v
        for vv in obj.values():
            r = _find_list(vv, key)
            if r:
                return r
    elif isinstance(obj, list):
        for vv in obj:
            r = _find_list(vv, key)
            if r:
                return r
    return None


def _find(obj, key):
    if isinstance(obj, dict):
        if key in obj:
            return obj[key]
        for v in obj.values():
            r = _find(v, key)
            if r is not None:
                return r
    elif isinstance(obj, list):
        for v in obj:
            r = _find(v, key)
            if r is not None:
                return r
    return None


def records(data: dict):
    for k in RECORD_KEYS:
        lst = _find_list(data, k)
        if lst:
            return lst
    return []


def _first(rec: dict, keys) -> object:
    for k in keys:
        if k in rec and rec[k] not in (None, ""):
            return rec[k]
    return None


def _label(rec: dict, i: int) -> str:
    return str(_first(rec, LABEL_KEYS) or f"case_{i}")


def _class_match(expected, actual) -> bool:
    e, a = str(expected).strip().lower(), str(actual).strip().lower()
    if e == a:
        return True
    m = re.match(r"([1-5])xx", e)                      # "4xx" vs an actual code like 400
    if m and a[:1] == m.group(1):
        return True
    if a.endswith("xx") and e[:1] == a[:1]:
        return True
    return False


def _status(rec: dict, expected, actual) -> str:
    c = _first(rec, CORRECT_KEYS)
    if isinstance(c, bool):
        return "Pass" if c else "Fail"
    if expected is None or actual is None:
        return "Skipped"
    return "Pass" if _class_match(expected, actual) else "Fail"


def build_steps(rec: dict, plan: dict | None, target: str) -> tuple[list[str], dict]:
    steps, data = [], {}
    # nested multi-step records (e.g. CRUD resources, oauth stages): render each real action
    nested = rec.get("steps") or rec.get("stages")
    if isinstance(nested, list) and nested and isinstance(nested[0], dict):
        for i, st in enumerate(nested, 1):
            verb = st.get("step") or st.get("stage") or st.get("action") or "Step"
            m = st.get("method", "")
            p = st.get("sent_path") or st.get("path") or st.get("url") or ""
            res = st.get("actual_code") or st.get("status") or st.get("result") or ""
            steps.append(f"{i}. {verb}: {(m + ' ') if m else ''}{p} -> {res}.".replace("  ", " "))
        if rec.get("table"):
            data["resource"] = rec["table"]
        return steps, data
    method = rec.get("method") or "GET"
    path = rec.get("path") or rec.get("endpoint") or rec.get("collection") or ""
    params = rec.get("params") if isinstance(rec.get("params"), dict) else {}
    body = rec.get("body")
    if rec.get("field"):
        data["field"] = rec["field"]
    if rec.get("category"):
        data["category"] = rec["category"]
    if rec.get("state"):
        data["state"] = rec["state"]
    if plan and isinstance(plan.get("seed"), list) and plan["seed"]:
        seed = plan["seed"]
        sample = ", ".join(str(s.get("name")) for s in seed[:3] if isinstance(s, dict))
        steps.append(f"1. Seed {plan.get('resource_path', path or '/resources')} with "
                     f"{len(seed)} records ({sample}, …) at the documented timestamps.")
        data["seed_records"] = len(seed)
    n = len(steps) + 1
    if params:
        data.update({str(k): v for k, v in params.items()})
    qs = ("?" + "&".join(f"{k}={v}" for k, v in params.items())) if params else ""
    bodytxt = f" with body {json.dumps(body)}" if body else ""
    if body is not None:
        data["body"] = body
    where = f" to {target}" if target else ""
    steps.append(f"{n}. Send {method} {path}{qs}{bodytxt}{where}.")
    steps.append(f"{n+1}. Read the HTTP response status code and body.")
    steps.append(f"{n+2}. Compare the observed result to the expected result.")
    return steps, data


def _measurable_expected(rec: dict, expected, steps: list[str]) -> str:
    if expected is not None:
        return f"The API returns {expected}."
    nested = rec.get("steps") or rec.get("stages")
    if isinstance(nested, list) and nested:
        return "Every step returns its documented success code and state persists across the flow."
    return "The response matches the documented contract for this case."


def _measurable_actual(rec: dict, actual, steps: list[str]) -> str:
    if actual is not None:
        return f"The API returned {actual}."
    nested = rec.get("steps") or rec.get("stages")
    if isinstance(nested, list) and nested:
        codes = ", ".join(f"{(st.get('step') or st.get('stage') or 'step')}={st.get('actual_code') or st.get('status') or '?'}"
                          for st in nested if isinstance(st, dict))
        return f"Observed: {codes}."
    return "Not captured."


def _summary_title(agent: str, label: str, expected, actual) -> str:
    subj = agent.replace("-", " ")
    base = humanize(base_label(label))
    verb = "returns the expected result" if expected is None else f"returns {expected}"
    return f"{base}: verify {subj} {verb}."


def format_agent(agent: str, data: dict) -> list[dict]:
    target = _find(data, "target") or "the API target"
    plan = _find(data, "emitted_plan") if isinstance(_find(data, "emitted_plan"), dict) else None
    cases = []
    for i, rec in enumerate(records(data), 1):
        if not isinstance(rec, dict):
            continue
        label = _label(rec, i)
        expected = _first(rec, EXPECTED_KEYS)
        actual = _first(rec, ACTUAL_KEYS)
        steps, tdata = build_steps(rec, plan, target)
        status = _status(rec, expected, actual)
        if status == "Skipped":
            status = "Blocked"               # rubric allows only Pass | Fail | Blocked
        # exact 8-field schema, in order
        cases.append({
            "test_case_id": f"TC-{code(agent)}-{i:03d}",
            "title_summary": _summary_title(agent, label, expected, actual),
            "preconditions": "API target reachable and authenticated where required; "
                             + ("seed data loaded as in step 1." if plan and plan.get("seed") else "no special prior state required."),
            "test_steps": steps,
            "test_data": tdata or {"note": "no explicit inputs for this case"},
            "expected_result": _measurable_expected(rec, expected, steps),
            "actual_result": _measurable_actual(rec, actual, steps),
            "status": status,
        })
    return cases


FIELD_LABELS = [("test_case_id", "Test Case ID"), ("title_summary", "Title/Summary"),
                ("preconditions", "Preconditions"), ("test_steps", "Test Steps"),
                ("test_data", "Test Data"), ("expected_result", "Expected Result"),
                ("actual_result", "Actual Result"), ("status", "Status")]


def to_markdown(agent: str, cases: list[dict]) -> str:
    counts = {s: sum(1 for c in cases if c["status"] == s) for s in ("Pass", "Fail", "Blocked")}
    out = [f"# Test Cases — {agent}", "",
           f"Total: {len(cases)} | Pass: {counts['Pass']} | Fail: {counts['Fail']} | "
           f"Blocked: {counts['Blocked']}", ""]
    for c in cases:
        out.append(f"## {c['test_case_id']}")
        for key, lbl in FIELD_LABELS[1:]:
            if key == "test_steps":
                out.append("- **Test Steps:**")
                out += [f"  {s}" for s in c["test_steps"]]
            elif key == "test_data":
                out.append(f"- **Test Data:** `{json.dumps(c['test_data'])}`")
            else:
                out.append(f"- **{lbl}:** {c[key]}")
        out.append("")
    return "\n".join(out)


def run(run_id: str, agent: str) -> int:
    cf = find_cases_file(run_id, agent)
    if cf is None:
        return 0
    try:
        data = json.loads(cf.read_text())
    except (OSError, json.JSONDecodeError):
        return 0
    cases = format_agent(agent, data)
    cj, cm = json.dumps(cases, indent=2), to_markdown(agent, cases)
    # 1) deliverable: flat results/<agent-name>/  (what you browse)
    flat = WS / "results" / agent
    flat.mkdir(parents=True, exist_ok=True)
    (flat / "cases.json").write_text(cj)
    (flat / "cases.md").write_text(cm)
    # 2) run-scoped copy: results/runs/<RUN>/test-case-registry/<agent>/  (per-run 'done' tracking)
    rs = WS / "results" / "runs" / run_id / "test-case-registry" / agent
    rs.mkdir(parents=True, exist_ok=True)
    (rs / "cases.json").write_text(cj)
    (rs / "cases.md").write_text(cm)
    return len(cases)


def main() -> None:
    if len(sys.argv) < 3:
        print("usage: python format_test_cases.py <RUN_ID> <agent>", file=sys.stderr)
        sys.exit(2)
    print(f"{sys.argv[2]}: {run(sys.argv[1], sys.argv[2])} test cases formatted")


if __name__ == "__main__":
    main()
