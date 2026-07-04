#!/usr/bin/env python3
# Used by: orchestrate_full.py Phase 3e — materialize the clean per-run deliverable tree + run the
# deliverable gate. Closes the gap where the full-orchestration driver left only a BugReport in the
# dated tree and never ran G13-G20 (see the RUN-20260702 retrospective: a documented AUTH-ME-MALFORMED
# 500 bug was missed because the deterministic Core-Requirements contract never ran in the full path).
"""Deliverable finalizer for the full-orchestration run.

After orchestrate_full has executed every agent and written its rich forensics under
results/runs/<RUN_ID>/, this builds the CLEAN, gate-compliant deliverable tree the harness
contract requires:

    results/<YYYY-MM-DD>/<HH-MM-SS>/
        TestCases/<agent>/{cases.json,cases.md}     (every tested agent's 8-field cases)
        Postman/{collection.json,environment.json}  (one collection, agent-foldered, asserted)
        BugReport/<agent>/{cases.json,cases.md}      (ONLY doc-reviewer-confirmed bugs)

It reuses the exact run_pipeline builders (the single source of truth for this layout) so the
full-orchestration output matches run_pipeline byte-for-byte in shape. It additionally runs the
deterministic Core-Requirements contract (Auth / CRUD-products / Search & Filtering / Error
handling) against the live target, which is what actually exercises AUTH-ME-MALFORMED and the
other lifecycle scenarios the shallow per-agent LLM producer misses.

Any pre-existing System-A adjudication BugReport (verified_bugs/unverified_bugs + index files,
written by adjudicate/bug_paths) is MOVED (never deleted) to
results/runs/<RUN_ID>/adjudication-BugReport/ so it survives as forensics while the dated
BugReport/ becomes the clean System-B deliverable.

The run's raw forensics under results/runs/<RUN_ID>/ are LEFT IN PLACE (unlike run_pipeline,
which prunes them) — the full-orchestration run keeps them for the adjudication ledger, guardrails
report, and per-agent stdout/stderr.
"""
from __future__ import annotations

import json
import os
import shutil
import sys
import tempfile
from pathlib import Path

WS = Path(os.environ.get("FORGE_WORKSPACE", str(Path(__file__).resolve().parents[1]))).resolve()
sys.path.insert(0, str(WS / "scripts"))
sys.path.insert(0, str(WS / "agents" / "common"))

import run_pipeline as RP  # noqa: E402  — the TestCases/Postman builders (single source of truth)
import report_bugs as RB    # noqa: E402  — deterministic bug-report materializer (reads guardrails)
import guardrails as G      # noqa: E402
from bugreport import run_date_time  # noqa: E402


_ARTIFACT_KEYS = {"screenshot_path": "screenshots", "recording_path": "recordings",
                  "log_path": "logs", "db_dump_path": "db"}
_BUG_ARTIFACT_SUBDIRS = {"screenshots", "recordings", "logs", "db"}


def _short_agent(agent_name: str) -> str:
    """'api-tester-test-authentication-flows' -> 'test-authentication-flows' so a bug's folder
    matches the agent's TestCases folder (G20 requires every BugReport agent to have a TestCases
    entry)."""
    for pre in ("api-tester-", "general-"):
        if agent_name.startswith(pre):
            return agent_name[len(pre):]
    return agent_name


# Severity = TECHNICAL impact on the system; Priority = BUSINESS urgency of the fix.
_SEVERITY_IMPACT = {"CRITICAL": "Blocker — crash, data loss, or auth/data exposure",
                    "HIGH": "Major — wrong behaviour on a supported feature",
                    "MEDIUM": "Moderate — degraded behaviour, workaround exists",
                    "LOW": "Minor — cosmetic / low-impact"}
_PRIORITY_URGENCY = {"P1": "High — fix now", "P2": "High", "P3": "Medium", "P4": "Low"}


def _agent_cases(out_root: Path, agent: str) -> list:
    """All of the agent's formatted test cases from its TestCases deliverable."""
    cf = out_root / "TestCases" / agent / "cases.json"
    try:
        return json.loads(cf.read_text())
    except (OSError, json.JSONDecodeError):
        return []


def _failed_cases(out_root: Path, agent: str) -> list:
    """The agent's Fail test cases — the source of the reproduction steps and the
    expected-vs-actual breakdown for its bug."""
    return [c for c in _agent_cases(out_root, agent) if c.get("status") == "Fail"]


# Human-scriptable reproduction recipes for AGGREGATE (metric-level) findings: what a person
# must script to reproduce the failure WITHOUT the agent harness. Placeholders: {target}.
_AGGREGATE_REPRO: dict = {
    "test-concurrent-request-handling": [
        "Write a concurrency script (Python asyncio+aiohttp, or `seq 20 | xargs -P20 -I_ curl -s "
        "-o /tmp/r_.json -w '%{{http_code}}\\n' {target}/products`) that fires 20 identical "
        "GET {target}/products requests in parallel.",
        "Assert all 20 responses carry the same status code and byte-identical bodies.",
        "Repeat with 20 concurrent PUT {target}/products/1 requests carrying distinct payloads, "
        "then GET /products/1 once — the final state must equal exactly one sent payload "
        "(no merged/torn write).",
    ],
    "verify-response-status-codes": [
        "Write a script that iterates every method+path in agent-foundry/data/openapi.json and "
        "sends the documented request (use the spec's example body) to {target}.",
        "Assert each observed status equals the documented code (200/201 on success; the "
        "documented error code for invalid-id variants such as GET /products/999999).",
    ],
    "test-pagination-behavior": [
        "Write a script that calls GET {target}/products?limit=10&skip=0 and then "
        "?limit=10&skip=10 (repeat for /users and /posts).",
        "Assert each page returns exactly `limit` items, the two pages share no ids, `total` is "
        "identical across pages, and `skip`/`limit` are echoed correctly.",
    ],
    "verify-error-message-clarity": [
        "Write a script that sends known-bad requests to {target}: GET /products/999999, "
        "POST /products/add with an empty JSON object, and a syntactically malformed body.",
        "Assert each error response uses the documented status and a non-empty message that "
        "names the offending field/resource.",
    ],
    "validate-query-parameter-handling": [
        "Write a script that calls GET {target}/products with valid "
        "(limit=5&skip=5&select=title,price), boundary (limit=0, limit=-1, limit=99999) and "
        "unknown (foo=bar) query parameters.",
        "Assert documented handling per case: valid params honored, invalid rejected or "
        "defaulted per docs, unknown params ignored.",
    ],
    "test-idempotency-of-endpoints": [
        "Write a script that sends the SAME PUT {target}/products/1 payload twice and the same "
        "DELETE /products/1 twice, capturing status+body each time.",
        "Assert each replay returns an identical outcome with no duplicated side effects, and "
        "that a repeated POST /products/add behaves per the documented create semantics.",
    ],
    "verify-content-type-negotiation": [
        "Write a script that sends GET {target}/products with Accept: application/json, "
        "text/html and application/xml, and POST /products/add with Content-Type: "
        "application/json vs text/plain.",
        "Assert the documented outcome per combination (JSON body + correct response "
        "Content-Type; unsupported types rejected with the documented 406/415).",
    ],
    "validate-null-empty-fields": [
        "Write a script that POSTs {target}/products/add and PUTs /products/1 with each "
        "required field null, empty-string and omitted, and each optional field null.",
        "Assert required-field violations return 400 with a clear message and documented "
        "nullable optionals are accepted.",
    ],
    "verify-crud-operation-integrity": [
        "Write a script that runs the full cycle against {target}: POST /products/add (capture "
        "id) → GET it back → PUT an update → GET again → DELETE → final GET.",
        "Assert every read-back reflects the preceding write per the documented persistence "
        "semantics (created fields present, update visible, delete behavior as documented).",
    ],
    "run-regression-suite": [
        "Write a script that replays every request in Postman/collection.json against {target} "
        "and diffs each status+body against the recorded expected values.",
        "Any case that previously passed and now fails is the regression.",
    ],
    "track-defect-density": [
        "Write a script that parses TestCases/*/cases.json, counts Fail cases per endpoint "
        "family, and divides by that family's total cases to compute defect density.",
        "Assert the computed densities match this run's recorded values; families with "
        "non-zero density are the defect clusters.",
    ],
    "test-bulk-operation-endpoints": [
        "Write a script that exercises each documented bulk-capable endpoint in "
        "agent-foundry/data/openapi.json against {target} with a multi-item payload, capturing "
        "per-item results.",
        "Assert the documented all-or-nothing / per-item semantics and read back each item to "
        "confirm it was applied.",
    ],
    "validate-search-and-filter-queries": [
        "Write a script that calls GET {target}/products/search?q=phone plus each documented "
        "filter parameter.",
        "Assert every returned item actually matches the predicate (e.g. title/description "
        "contains the query) and counts are consistent with `total`.",
    ],
    "verify-sorting-behavior": [
        "Write a script that calls GET {target}/products?sortBy=price&order=asc, then "
        "order=desc, then sortBy=title.",
        "Assert the returned list is monotonically ordered by the requested field and "
        "direction on every call.",
    ],
    "measure-api-consumer-satisfaction": [
        "Write a script that samples every endpoint in agent-foundry/data/openapi.json "
        "(~5 requests each) against {target}, recording latency, error rate and "
        "schema-consistency, and computes the satisfaction score per the evidence file's "
        "formula.",
        "Assert the score meets the pass threshold; sub-threshold endpoints locate the failure.",
    ],
    "test-soft-delete-behavior": [
        "Write a script that sends DELETE {target}/products/1 and captures the response body.",
        "Assert the documented soft-delete markers (isDeleted: true, deletedOn timestamp), then "
        "GET /products/1 and assert the documented post-delete visibility.",
    ],
}

_GENERIC_AGGREGATE_REPRO = [
    "Write a script that iterates every method+path in agent-foundry/data/openapi.json and "
    "performs this agent's '{scenario}' check against {target}: send the documented request "
    "and capture status + body.",
    "Assert each response against the expected_result recorded per scenario in the evidence "
    "file.",
]


def _aggregate_steps(agent: str, scenario: str, target: str, evidence: str,
                     n_fail: int, n_total: int) -> list:
    """Numbered, human-scriptable reproduction steps for a metric-level finding — the script a
    person must build to hit the bug without the agent harness."""
    recipe = _AGGREGATE_REPRO.get(agent, _GENERIC_AGGREGATE_REPRO)
    body = [s.format(target=target, scenario=scenario) for s in recipe]
    steps = ([f"Start the target API at {target}."] + body
             + [f"Compare your script's failures with the per-scenario evidence in {evidence} — "
                f"this run recorded {n_fail} of {n_total} checks failing."])
    return [f"{i}. {s}" for i, s in enumerate(steps, 1)]


def _has_postman_folder(out_root: Path, agent: str) -> bool:
    """True when the Postman deliverable has a folder for this agent. Only agents whose cases
    are concrete recorded API calls get one, so a bug report must never claim Postman
    references for an agent that has no folder."""
    try:
        col = json.loads((out_root / "Postman" / "collection.json").read_text())
    except (OSError, json.JSONDecodeError):
        return False
    return any(i.get("name") == agent for i in col.get("item", []))


_UNVERIFIED_ID_RE = __import__("re").compile(r"^(VULN|BIZ|SW)-(.+)-(\d{4})$")


def _seed_unverified_counters(run_id: str, *roots) -> dict:
    """Seed the unverified ID counters past every {PREFIX}-{run_id}-NNNN already on disk so
    demoted findings can never collide with adjudicate's per-case unverified bugs (HF19)."""
    counters: dict = {}
    for root in roots:
        if not root:
            continue
        # unverified bugs live in the top-level unverified/{category}/ tree
        for f in list(Path(root).glob("unverified/*/*.json")) + \
                list(Path(root).glob("*/unverified_bugs/*/*.json")):  # legacy layout tolerated
            m = _UNVERIFIED_ID_RE.match(f.stem)
            if m and m.group(2) == run_id:
                counters[m.group(1)] = max(counters.get(m.group(1), 0), int(m.group(3)))
    return counters


# Exact public-documentation URL for every doc-corpus file the reviewer can cite. The local
# corpus mirrors (data/documentation-reviewer/{cli,reference}) map to their dummyjson.com pages;
# harvested references/dummyjson-com/<page>.md files map by page name.
_DOC_URLS = {
    "dummyjson-com.md": "https://dummyjson.com/",
    "dummyjson-com-docs.md": "https://dummyjson.com/docs",
    "dummyjson-com-docs-auth.md": "https://dummyjson.com/docs/auth",
    "auth.md": "https://dummyjson.com/docs/auth",
    "products.md": "https://dummyjson.com/docs/products",
    "recipes.md": "https://dummyjson.com/docs/recipes",
}
_DOC_PAGE_RE = __import__("re").compile(r"^dummyjson-com-([a-z0-9-]+)\.md$")


def _doc_url(file_path) -> str | None:
    """Exact documentation link for a cited corpus file, or None when no public page maps."""
    name = Path(file_path or "").name
    if name in _DOC_URLS:
        return _DOC_URLS[name]
    m = _DOC_PAGE_RE.match(name)
    return f"https://dummyjson.com/{m.group(1)}" if m else None


def _rel_doc_path(file_path) -> str:
    """Normalize a cited doc file to a repo-relative path (reviewer sometimes emits absolute)."""
    p = Path(file_path or "")
    if p.is_absolute():
        for base in (WS, WS.parent):
            try:
                return str(p.relative_to(base))
            except ValueError:
                continue
    return str(file_path or "")


def _doc_reviewer() -> tuple:
    """(corpus, invoke) for the documentation-reviewer, or (None, None) when the backend is
    unavailable — bug materialization must never crash on a missing LLM."""
    try:
        import adjudicate as ADJ  # noqa: E402
        return ADJ.build_corpus(), ADJ._reviewer_invoke()
    except Exception:  # noqa: BLE001
        return None, None


def _doc_lookup(corpus, invoke, report: dict) -> dict:
    """Adjudicate one bug's expected behavior against the doc corpus. Returns the report's
    `documentation` block: a citation (file/line/text/source_url) when the docs state the
    expected behavior, else an explicit uncited note — never silently absent."""
    uncited_note = ("No public documentation states this expected behavior "
                    "(documentation-reviewer verdict: {v}). The expectation derives from the "
                    "universal HTTP/REST contract (agent-foundry/references/contract-oracle.md).")
    if corpus is None or invoke is None:
        return {"cited": False, "verdict": "unreviewed", "note": uncited_note.format(v="unreviewed")}
    import adjudicate as ADJ  # noqa: E402
    import docreview  # noqa: E402
    import docreview_spec  # noqa: E402
    m = {"agent": report.get("_source", {}).get("agent", ""),
         "scenario": report.get("title_summary", ""),
         "endpoint": report.get("environment", {}).get("endpoint", ""),
         "expected": report.get("expected_result", ""),
         "observed": report.get("actual_result", "")}
    try:
        parsed = docreview_spec.parse_bug_report(ADJ._bug_report_text(m))
        cand = docreview_spec.grep_corpus(corpus, ADJ._keywords(m))
        d = docreview.extract_json(invoke(docreview_spec.brief(parsed, corpus, cand, 3))) or {}
    except Exception:  # noqa: BLE001
        d = {}
    sot = d.get("source_of_truth") if isinstance(d.get("source_of_truth"), dict) else None
    if d.get("verdict") == "yes" and sot:
        cited_file = _rel_doc_path(sot.get("file"))
        return {"cited": True, "file": cited_file, "line": sot.get("line"),
                "text": sot.get("text"),
                "source_url": _doc_url(cited_file),
                "reviewer_reason": d.get("reason")}
    verdict = d.get("verdict") or "unreviewed"
    return {"cited": False, "verdict": verdict, "note": uncited_note.format(v=verdict)}


def _standard_report(raw: dict, agent: str, out_root: Path, run_id: str, target: str,
                     date: str, tm: str, attachments: dict) -> dict:
    """Transform a raw metric/artifact bug record into a standard defect report with the eight
    fields a developer expects: id, title/summary, description (When I…/I expect…/but I get…),
    steps to reproduce, actual-vs-expected, priority & severity, environment, attachments.

    Two honest shapes, never mixed: a failing case that carries a concrete recorded request
    (method + path in test_data) keeps its single-call reproduction; an AGGREGATE (metric-level)
    failure gets agent-level repro steps pointing at the case evidence — template placeholder
    steps are never passed off as a real API call, and the postman_references completeness flag
    always reflects the agent's actual Postman presence."""
    cases = _agent_cases(out_root, agent)
    fails = [c for c in cases if c.get("status") == "Fail"]
    rep = fails[0] if fails else {}
    td = rep.get("test_data") or {}
    method, path = td.get("method"), td.get("path")
    is_concrete = bool(method and path)
    evidence = f"TestCases/{agent}/cases.json"
    sev = raw.get("severity", "MEDIUM")
    if is_concrete:
        expected = rep.get("expected_result") or "the documented behaviour for this scenario"
        actual = rep.get("actual_result") or raw.get("title", "an incorrect result")
        steps = rep.get("test_steps") or [f"1. Send {method} {path} to the target.",
                                          "2. Read the HTTP status and body.",
                                          "3. Compare observed vs expected."]
        scenario = rep.get("title_summary") or agent.replace("-", " ")
        summary = scenario
        endpoint = f"{method} {path}"
        description = (f"When I exercise the '{scenario}' check against {endpoint} on {target}, "
                       f"I expect {expected} but I get: {actual}")
    else:
        # Aggregate (metric-level) finding: there is no single reproducible API call, so
        # describe the real failure signal and point at the per-scenario evidence instead.
        metric_line = raw.get("title") or f"{agent} aggregate check failed"
        scenario = agent.replace("-", " ")
        summary = (f"Aggregate failure: {scenario} "
                   f"({len(fails)}/{len(cases)} scenario checks failed)")
        expected = (f"All {len(cases)} '{scenario}' scenario checks pass against the documented "
                    f"behaviour" if cases else
                    "the agent's aggregate metric meets its pass threshold")
        actual = metric_line
        steps = _aggregate_steps(agent, scenario, target, evidence, len(fails), len(cases))
        endpoint = "n/a — aggregate finding across endpoints"
        description = (f"The {agent} check failed in aggregate against {target}: "
                       f"{metric_line}. The per-scenario evidence is in {evidence}. There is no "
                       f"single reproducible API call — reproduce it with the script described "
                       f"in the steps below (which is also why this bug has no Postman section).")
    completeness = dict(raw.get("artifact_completeness") or {})
    if completeness:
        completeness["postman_references"] = _has_postman_folder(out_root, agent)
    return {
        "id": raw.get("bug_id"),
        "title_summary": summary[:160],
        "description": description,
        "steps_to_reproduce": steps,
        "expected_result": expected,
        "actual_result": actual,
        "severity": sev,
        "severity_impact": _SEVERITY_IMPACT.get(sev, "Unclassified"),
        "priority": raw.get("priority", "P3"),
        "priority_urgency": _PRIORITY_URGENCY.get(raw.get("priority", "P3"), "Medium"),
        "environment": {"target": target, "api": "DummyJSON clone (local)", "runtime": "Node.js",
                        "endpoint": endpoint, "run_id": run_id, "date": f"{date} {tm.replace('-', ':')}"},
        "evidence": evidence,
        "attachments": attachments,
        "affected_test_cases": [c.get("test_case_id") for c in fails] or None,
        "_source": {"agent": raw.get("agent_name"), "raw_title": raw.get("title"),
                    "created_at": raw.get("created_at"),
                    "artifact_completeness": completeness or raw.get("artifact_completeness")},
    }


def _bug_markdown(r: dict) -> str:
    steps = "\n".join(f"{s}" if str(s).strip()[:2].strip().rstrip('.').isdigit()
                      else f"{i}. {s}" for i, s in enumerate(r["steps_to_reproduce"], 1))
    att = r["attachments"]
    att_md = "\n".join(f"- {k.replace('_path','').title()}: `{v}`" for k, v in att.items() if v) or "- (none)"
    env = r["environment"]
    doc = r.get("documentation") or {}
    if doc.get("cited"):
        doc_md = (f"- **Source:** {doc.get('file')}:{doc.get('line')}"
                  + (f" ({doc.get('source_url')})" if doc.get("source_url") else "") + "\n"
                  f"  > {doc.get('text')}\n"
                  f"- **Reviewer reason:** {doc.get('reviewer_reason')}")
    else:
        doc_md = f"- {doc.get('note', 'Not adjudicated against documentation.')}"
    return (f"# {r['id']} — {r['title_summary']}\n\n"
            f"## Description\n{r['description']}\n\n"
            f"## Steps to Reproduce\n{steps}\n\n"
            f"## Actual vs. Expected\n"
            f"- **Expected:** {r['expected_result']}\n"
            f"- **Actual:** {r['actual_result']}\n\n"
            f"## Severity & Priority\n"
            f"- **Severity (technical impact):** {r['severity']} — {r['severity_impact']}\n"
            f"- **Priority (business urgency):** {r['priority']} — {r['priority_urgency']}\n\n"
            f"## Environment\n"
            f"- Target: {env['target']}\n- API: {env['api']}\n- Runtime: {env['runtime']}\n"
            f"- Endpoint: {env['endpoint']}\n- Run: {env['run_id']} ({env['date']})\n\n"
            f"## Documentation\n{doc_md}\n\n"
            f"## Attachments\n{att_md}\n")


def _unverified_source(out_root: Path, run_id: str) -> Path | None:
    """Where the run's unverified bugs (missing-docs → VULN/BIZ/SW, written by adjudicate) live:
    the dated BugReport itself in a fresh orchestrate_full run (adjudicate runs before finalize),
    else the run's adjudication-BugReport archive. None if the run produced no unverified bugs.
    Unverified bugs live in ONE top-level tree: BugReport/unverified/{category}/."""
    tree = out_root / "BugReport"
    if (tree / "unverified").is_dir() and any((tree / "unverified").glob("*/*.json")):
        return tree
    arch = WS / "results" / "runs" / run_id / "adjudication-BugReport"
    if (arch / "unverified").is_dir() and any((arch / "unverified").glob("*/*.json")):
        return arch
    return None


def _snapshot_unverified(src: Path) -> Path:
    """Copy the unverified tree (unverified/{category}/**, incl. its screenshots/recordings/logs)
    to a temp dir so it survives the BugReport rmtree, then gets restored into the rebuilt
    deliverable. No index file is carried — guardrail G22 forbids any *-index.json under BugReport."""
    snap = Path(tempfile.mkdtemp(prefix="unv-"))
    uv = src / "unverified"
    if uv.is_dir():
        shutil.copytree(uv, snap / "unverified")
    return snap


def _restore_unverified(tree: Path, snap: Path) -> dict:
    """Restore the unverified bugs into the rebuilt BugReport at BugReport/unverified/{category}/
    (with their co-located artifacts). No index file is written (guardrail G22); counts are derived
    from the restored reports themselves."""
    src = snap / "unverified"
    if src.is_dir():
        shutil.copytree(src, tree / "unverified", dirs_exist_ok=True)
    files = [p for p in (tree / "unverified").glob("*/*.json")] if (tree / "unverified").is_dir() else []
    by_cat: dict = {}
    for p in files:
        cat = p.parent.name
        by_cat[cat] = by_cat.get(cat, 0) + 1
    agents = len({json.loads(p.read_text()).get("finding_agent")
                  for p in files if p.suffix == ".json"})
    return {"reports": len(files), "agents": agents, "by_category": by_cat}


def _materialize_bugreport(out_root: Path, run_id: str, target: str) -> dict:
    """Build the deliverable BugReport/ tree, self-contained, holding BOTH bug classes per the
    unverified-bugs implementation plan:
      - VERIFIED bugs (FAIL/EMPTY/ERROR features) in the STANDARD defect format at
        BugReport/<agent>/verified_bugs/BUG-*.{json,md} with embedded screenshots/recordings/logs;
      - UNVERIFIED bugs (missing-docs → categorized VULN/BIZ/SW by adjudicate) at
        BugReport/<agent>/unverified_bugs/{category}/{PREFIX}-*.json, preserved across the rebuild
        (report-only; they never change the exit code).
    No *-index.json is written under BugReport (guardrail G22 forbids it).
    Rebuilt from scratch each call. Returns {reports, agents, artifacts, unverified}."""
    date, tm = run_date_time(run_id)
    src = WS / "results" / "runs" / run_id / "general-bug-reporter.bug-reports"
    tree = out_root / "BugReport"
    # snapshot adjudicate's unverified bugs BEFORE we blow the tree away, so they survive the rebuild
    unv_src = _unverified_source(out_root, run_id)
    unv_snap = _snapshot_unverified(unv_src) if unv_src else None
    if tree.exists():
        shutil.rmtree(tree)
    reports = sorted(src.glob("BUG-*.json")) if src.is_dir() else []
    if not reports and unv_snap is None:
        return {"reports": 0, "agents": 0, "artifacts": 0, "unverified": {"reports": 0}}

    # REVIEWER GATE (non-negotiable): every failed finding is adjudicated against the doc
    # corpus BEFORE it may be called a verified bug. Only a documentation-reviewer citation
    # ("yes" + source_of_truth) earns verified_bugs/BUG-*; an uncited finding is demoted to a
    # categorized report-only unverified bug; a "no" (docs say observed IS correct) files nothing.
    verified_agents: set = set()
    verified_count = 0
    demoted_count = 0
    rejected: list = []
    artifacts = 0
    corpus, invoke = _doc_reviewer() if reports else (None, None)
    counters = _seed_unverified_counters(run_id, unv_snap, tree)
    import bugreport as BRP  # noqa: E402
    BRP.WORKSPACE = WS
    BRP.SANDBOX_ROOT = WS
    for bf in reports:
        try:
            raw = json.loads(bf.read_text())
        except (OSError, json.JSONDecodeError):
            continue
        agent = _short_agent(raw.get("agent_name", "unknown"))
        # copy artifacts into the deliverable and build the relative-path attachments block
        arts = raw.get("artifacts") or {}
        attachments: dict = {}
        for key, sub in _ARTIFACT_KEYS.items():
            p = arts.get(key)
            if not p:
                continue
            srcf = WS / p if not Path(p).is_absolute() else Path(p)
            if srcf.is_file():
                dest_dir = tree / agent / sub
                dest_dir.mkdir(parents=True, exist_ok=True)
                shutil.copy2(srcf, dest_dir / srcf.name)
                attachments[key.replace("_path", "")] = f"BugReport/{agent}/{sub}/{srcf.name}"
                artifacts += 1
        report = _standard_report(raw, agent, out_root, run_id, target, date, tm, attachments)
        report["documentation"] = _doc_lookup(corpus, invoke, report)
        doc = report["documentation"]
        if doc.get("cited"):
            adir = tree / agent / "verified_bugs"
            adir.mkdir(parents=True, exist_ok=True)
            (adir / bf.name).write_text(json.dumps(report, indent=2))
            (adir / (bf.stem + ".md")).write_text(_bug_markdown(report))
            verified_agents.add(agent)
            verified_count += 1
        elif doc.get("verdict") == "no":
            rejected.append({"agent": agent, "bug_id": raw.get("bug_id"),
                             "reason": doc.get("note")})
        else:
            ctx = {"agent": agent, "endpoint": report["environment"]["endpoint"],
                   "scenario": report["title_summary"],
                   "expected": report["expected_result"], "observed": report["actual_result"],
                   "spec_path": f"agents/api-tester/{agent}", "stderr": raw.get("title") or "",
                   "severity": report["severity"], "priority": report["priority"],
                   "testing_steps": report["steps_to_reproduce"], "postman_references": []}
            uv = BRP.write_unverified_bug(run_id, ctx, counters, db_available=False, workspace=WS)
            meta = uv.pop("_meta", {})
            merged = {**uv, "description": report["description"],
                      "steps_to_reproduce": report["steps_to_reproduce"],
                      "evidence": report["evidence"], "documentation": report["documentation"],
                      "environment": report["environment"],
                      "affected_test_cases": report["affected_test_cases"],
                      "_source": report["_source"]}
            rp_path = WS / meta.get("report_path", "")
            if meta.get("report_path") and rp_path.is_file():
                rp_path.write_text(json.dumps(merged, indent=2))
            demoted_count += 1

    tree.mkdir(parents=True, exist_ok=True)
    # No verified-index.json / unverified-index.json is written — guardrail G22 forbids any
    # *-index.json under BugReport. The bug JSONs themselves are the source of truth.

    # restore the categorized unverified bugs (missing-docs) into the rebuilt deliverable
    unverified = {"reports": 0}
    if unv_snap is not None:
        unverified = _restore_unverified(tree, unv_snap)
        shutil.rmtree(unv_snap, ignore_errors=True)

    # drop any agent dir left empty (e.g. an agent whose only findings were unverified — those
    # now live under BugReport/unverified/, attributed by finding_agent, not per-agent).
    for p in list(tree.iterdir()):
        if (p.is_dir() and p.name not in ("unverified",) and p.name not in _BUG_ARTIFACT_SUBDIRS
                and not (p / "cases.json").is_file()
                and not ((p / "verified_bugs").is_dir() and any((p / "verified_bugs").glob("*.json")))):
            shutil.rmtree(p, ignore_errors=True)

    return {"reports": verified_count, "agents": len(verified_agents), "artifacts": artifacts,
            "demoted_unverified": demoted_count, "rejected_not_a_bug": rejected,
            "unverified": unverified}


_DATE_RE = __import__("re").compile(r"^\d{4}-\d{2}-\d{2}$")
# Kept under results/: dated deliverables + the code-review subsystem's shared dir (a different
# subsystem; user chose to leave it). Everything else is this run's transient working data.
_RESULTS_KEEP = {"_global"}


def tidy_results(run_id: str) -> dict:
    """Delete this run's transient working data as soon as the deliverable is built — the date-tree
    deliverable is fully self-contained, so nothing under results/ but the dated folders (and the
    code-review _global dir) needs to survive. Removes results/runs/<RUN_ID> (this run's forensics),
    an empty results/runs, the legacy results/bug-reports dual-write, and the loose
    test-case-registry*.json strays. Never touches other date dirs or _global. Returns what it removed
    and any remaining non-deliverable strays."""
    results = WS / "results"
    removed: list = []
    run_dir = results / "runs" / run_id
    if run_dir.exists():
        shutil.rmtree(run_dir, ignore_errors=True)
        removed.append(f"runs/{run_id}")
    runs = results / "runs"
    if runs.is_dir():
        (runs / ".DS_Store").unlink(missing_ok=True)
        if not any(runs.iterdir()):
            runs.rmdir()
            removed.append("runs/")
    for stray in ("bug-reports", "test-case-registry.json", "test-case-registry-summary.json"):
        p = results / stray
        if p.is_dir():
            shutil.rmtree(p, ignore_errors=True)
            removed.append(stray)
        elif p.exists():
            p.unlink()
            removed.append(stray)
    strays = [e.name for e in results.iterdir()
              if e.name not in _RESULTS_KEEP and not (e.is_dir() and _DATE_RE.match(e.name))
              and "code-review" not in e.name and e.name != ".DS_Store"] if results.is_dir() else []
    return {"removed": removed, "remaining_strays": sorted(strays)}


def finalize(run_id: str, target: str | None = None, do_bugs: bool = True) -> dict:
    """Build the clean per-run deliverable tree (TestCases/ + Postman/ + BugReport/) under
    results/{date}/{time}/ and return a summary incl. the deliverable-gate results.

    The BugReport/ folder holds THIS run's ACTUAL bug reports (report_bugs materializes the
    FAIL/EMPTY/ERROR features from guardrails-report.json into the dated BugReport tree — the same
    reports mirrored under results/runs/<RUN_ID>/general-bug-reporter.bug-reports/). Because
    guardrails is regenerated with the reconciled capability map first, ENV-LIMITED features are
    correctly excluded, so the deliverable bug set reflects real failures only. BugReport/ is
    optional in G13/G20 — a clean run with no failures simply has no BugReport/."""
    target = target or os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899")
    date, tm = run_date_time(run_id)
    out_root = WS / "results" / date / tm
    out_root.mkdir(parents=True, exist_ok=True)

    # 1. TestCases/<agent>/ for every tested agent (from this run's executor cases).
    per_agent = RP.build_test_cases(out_root, run_id)

    # 2. Fold in any recorded raw requests (guarded — the full-orch driver may not record them).
    try:
        import request_cases  # noqa: E402
        req_dir = WS / "results" / "runs" / run_id / "requests"
        if req_dir.is_dir():
            request_cases.augment(out_root, req_dir, RP.CORE_AGENTS)
    except Exception as exc:  # noqa: BLE001 — request fold-in is best-effort
        print(f"[deliverables] request fold-in skipped: {exc}", flush=True)

    # 3. Deterministic Core-Requirements contract against the live target -> deep core TestCases +
    #    the Postman deliverable. THIS is what exercises AUTH-ME-MALFORMED et al. every run.
    core = RP.build_core_requirements(out_root, target)
    per_agent.update(core)

    # 4. BugReport/ — the run's actual bug reports (report_bugs writes the System-A tree into the
    #    dated BugReport via bug_paths). Deterministic: sourced from guardrails-report.json.
    #    Then EMBED each report's artifacts (screenshots, screen recordings, logs) into the
    #    deliverable so every bug is self-contained — no loose bug, no artifact left in runs/.
    bug = {}
    if do_bugs:
        try:
            # regenerate the run's bug reports from the reconciled guardrails state (clear stale
            # first so ENV-LIMITED/removed features never linger), then own the dated BugReport tree.
            legacy = WS / "results" / "runs" / run_id / "general-bug-reporter.bug-reports"
            if legacy.exists():
                shutil.rmtree(legacy)
            RB.run(run_id)
            bug = _materialize_bugreport(out_root, run_id, target)
            # 4b. Replace the deterministic placeholder artifacts with REAL captured evidence:
            #     reproduce each bug against the target and render a PNG screenshot + a stepped
            #     .cast recording + best-effort server logs (G24). Server-log capture is enabled
            #     only when the target's own request log is provided via FORGE_TARGET_SERVER_LOG.
            try:
                import recapture_bug_evidence as RCE  # noqa: E402
                srv_log = os.environ.get("FORGE_TARGET_SERVER_LOG")
                cap = RCE.run(out_root, target,
                              Path(srv_log).resolve() if srv_log else None)
                print(f"[deliverables] evidence recapture: {json.dumps(cap)}", flush=True)
                bug["evidence_recapture"] = cap
            except Exception as exc:  # noqa: BLE001 — capture is best-effort; placeholders remain
                print(f"[deliverables] evidence recapture skipped: {exc}", flush=True)
        except Exception as exc:  # noqa: BLE001 — BugReport is optional; never crash finalize
            print(f"[deliverables] bug materialization skipped: {exc}", flush=True)
            bug = {"error": str(exc)}

    # 5. CI regression suite — the run's PASSING, executable cases grouped by the creating agent
    #    (refresh each run). Deterministic replay set the CI job runs; excludes unverified (they are
    #    not in TestCases) and ambiguous template-path/no-path cases.
    regression = {}
    try:
        import ci_regression_suite as CRS  # noqa: E402
        regression = CRS.build(out_root)
        print(f"[deliverables] CI regression suite: {regression.get('total_cases', 0)} passing cases "
              f"across {regression.get('agents', 0)} agents", flush=True)
    except Exception as exc:  # noqa: BLE001 — suite build is best-effort
        print(f"[deliverables] regression-suite build skipped: {exc}", flush=True)
        regression = {"error": str(exc)}

    # 6. The per-run deliverable gate (HARD subset) + the full core_gate for reporting.
    gates = G.deliverable_gate(out_root)
    full_gates = G.core_gate(out_root)
    hard_fail = any(g["status"] == "FAIL" and g.get("hard") for g in gates)

    return {
        "out_root": str(out_root),
        "date": date, "time": tm,
        "testcase_agents": len(per_agent),
        "bug_reporting": bug,
        "regression_suite": regression,
        "gates": gates,
        "core_gate": full_gates,
        "hard_fail": hard_fail,
    }


def main() -> None:
    if len(sys.argv) < 2:
        print("usage: python build_deliverables.py <RUN_ID> [--no-bugs]", file=sys.stderr)
        sys.exit(2)
    run_id = sys.argv[1]
    do_bugs = "--no-bugs" not in sys.argv[2:]
    res = finalize(run_id, do_bugs=do_bugs)
    b = res.get("bug_reporting", {})
    uv = (b.get("unverified") or {}).get("reports", 0) if isinstance(b, dict) else 0
    print(f"DELIVERABLES -> {res['out_root']}  TestCases={res['testcase_agents']} agents  "
          f"BugReport={b.get('reports', 0)} verified / {uv} unverified / "
          f"{b.get('artifacts', 0)} artifacts", flush=True)
    for g in res["gates"]:
        print(f"  {g['id']} {g['name']}: {g['status']} — {g['detail']}", flush=True)
    sys.exit(2 if res["hard_fail"] else 0)


if __name__ == "__main__":
    main()
