"""Canonical computation + scoring structure for the Test-Case-Creator task (n600).

ONE definition of how an agent spec is turned into structured test-case objects, the
deterministic reference that produces them, and the per-cell comparator — shared by:
  - the gold reference (data/test-case-creator/build_gold.py), and
  - the harness (agents/common/testcase.py) — which takes whatever registry an agent
    emitted and scores it cell-for-cell against the same reference.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(agent, step_id, field) key scheme so the judge can compare them cell-for-cell.

Task reality (air-gapped fixtures, NOT DummyJSON — DummyJSON has no agent-spec /
build-manifest surface and is never touched or modified):
  - A build manifest (data/test-case-creator/manifest.json) lists agent nodes, each
    with name + enabled + spec_path. Each spec file is an agent node card written in
    the "- **What:** / - **How:** / - **Tools:** / - **Metric:**" bullet format.
  - The reference extracts every numbered step from every enabled agent's How section
    and produces exactly one test-case object per step, so gold is fully deterministic.

The registry object schema (the literal n600 -> n601 contract; field names are verbatim
as specified, INCLUDING `step_ext` which downstream n601/Postman-Collection-Creator
consumes — do not "correct" it without re-running the gate and updating n601):
  {
    "tc_id", "agent", "step_id", "step_ext",
    "involves_http_call", "involves_db_query", "involves_file_write",
    "involves_assertion", "involves_metric_check",
    "expected_outcome", "fail_condition"
  }
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Literal registry field schema (n600 -> n601 contract; order is canonical).
# --------------------------------------------------------------------------- #
# `step_ext` is the verbatim key from the task spec (a known typo for step_text,
# preserved on purpose so the n601 Postman-Collection-Creator contract stays stable).
STEP_TEXT_KEY = "step_ext"

REGISTRY_FIELDS = [
    "tc_id",
    "agent",
    "step_id",
    STEP_TEXT_KEY,
    "involves_http_call",
    "involves_db_query",
    "involves_file_write",
    "involves_assertion",
    "involves_metric_check",
    "expected_outcome",
    "fail_condition",
]

# Fields compared as exact booleans during scoring.
BOOL_FIELDS = {
    "involves_http_call",
    "involves_db_query",
    "involves_file_write",
    "involves_assertion",
    "involves_metric_check",
}

# --------------------------------------------------------------------------- #
# Section extraction.
# --------------------------------------------------------------------------- #
HOW_MARKER = "- **How:**"
TOOLS_MARKER = "- **Tools:**"
METRIC_MARKER = "- **Metric:**"

# A step begins with: optional leading whitespace, an integer, an OPTIONAL single
# lowercase letter, a period, then at least one space/tab. The captured id keeps the
# number+letter prefix WITHOUT the trailing period (e.g. "3b").
STEP_RE = re.compile(r"^[ \t]*([0-9]+[a-z]?)\.[ \t]+", re.MULTILINE)

# Each "Assert ..." clause = the literal "Assert " plus everything up to (not
# including) the next sentence boundary (period or semicolon) or end of text.
ASSERT_CLAUSE_RE = re.compile(r"Assert [^.;]*")


def extract_how(spec_text: str) -> str | None:
    """Return the How section body: the substring AFTER `- **How:**` up to (not
    including) the next line that begins with `- **Tools:**`. None if not found."""
    if not spec_text:
        return None
    start = spec_text.find(HOW_MARKER)
    if start == -1:
        return None
    body_start = start + len(HOW_MARKER)
    # The next line beginning with the Tools marker (line-anchored).
    m = re.search(r"(?m)^" + re.escape(TOOLS_MARKER), spec_text[body_start:])
    body = spec_text[body_start:body_start + m.start()] if m else spec_text[body_start:]
    body = body.strip()
    return body or None


def extract_steps(how_text: str) -> list[tuple[str, str]]:
    """Every numbered step in How order as (step_id, step_text) pairs.

    step_id  = the number+optional-lowercase-letter prefix without the trailing period.
    step_text = all characters after the first space following the id up to the start of
                the next step id (or end of how_text), leading/trailing whitespace trimmed.
    """
    if not how_text:
        return []
    matches = list(STEP_RE.finditer(how_text))
    pairs: list[tuple[str, str]] = []
    for i, m in enumerate(matches):
        step_id = m.group(1)
        text_start = m.end()
        text_end = matches[i + 1].start() if i + 1 < len(matches) else len(how_text)
        step_text = how_text[text_start:text_end].strip()
        pairs.append((step_id, step_text))
    return pairs


# --------------------------------------------------------------------------- #
# Boolean flags (case-sensitive exact-substring membership, per the n600 spec).
# --------------------------------------------------------------------------- #
HTTP_SUBSTRINGS = (
    "Send ", "GET /", "POST /", "PUT /", "DELETE /", "PATCH /", "curl ",
    "request", " endpoint", "HTTP ", "response code",
    "assert exactly 2", "assert exactly 4", "assert exactly 5", "→ assert",
)
DB_SUBSTRINGS = (
    "SELECT ", "INSERT ", "UPDATE ", "DELETE FROM", "psql", "mysql",
    "COUNT(*)", "WHERE ", "database", " DB",
)
FILE_WRITE_SUBSTRINGS = (
    "Write ", "write ", "Record ", "log ", "produce ", "emit ", "save ",
    "publish ", "output ",
)
ASSERT_SUBSTRINGS = ("Assert ", "assert ")
METRIC_SUBSTRINGS = ("Pass:", "Fail:", "rate", "÷")


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    return any(n in text for n in needles)


def involves_http_call(step_text: str) -> bool:
    return _contains_any(step_text, HTTP_SUBSTRINGS)


def involves_db_query(step_text: str) -> bool:
    return _contains_any(step_text, DB_SUBSTRINGS)


def involves_file_write(step_text: str) -> bool:
    return _contains_any(step_text, FILE_WRITE_SUBSTRINGS)


def involves_assertion(step_text: str) -> bool:
    return _contains_any(step_text, ASSERT_SUBSTRINGS)


def involves_metric_check(step_text: str) -> bool:
    return _contains_any(step_text, METRIC_SUBSTRINGS)


# --------------------------------------------------------------------------- #
# Derived text fields.
# --------------------------------------------------------------------------- #
def expected_outcome(step_text: str) -> str:
    """All `Assert ...` clauses joined with ' AND ', or 'see step_text' if none."""
    clauses = [c.strip() for c in ASSERT_CLAUSE_RE.findall(step_text)]
    clauses = [c for c in clauses if c]
    return " AND ".join(clauses) if clauses else "see step_text"


def fail_condition(spec_text: str) -> str:
    """From the `- **Metric:**` line, the substring beginning at 'Fail:' to end of line.
    'none_stated' when there is no Metric line or no 'Fail:' on it."""
    if not spec_text:
        return "none_stated"
    for line in spec_text.splitlines():
        if line.lstrip().startswith(METRIC_MARKER):
            idx = line.find("Fail:")
            if idx != -1:
                return line[idx:].strip()
            return "none_stated"
    return "none_stated"


# --------------------------------------------------------------------------- #
# Object + registry assembly.
# --------------------------------------------------------------------------- #
def build_test_case(agent_name: str, step_id: str, step_text: str, spec_text: str) -> dict:
    """The single canonical test-case object for one (agent, step)."""
    return {
        "tc_id": f"{agent_name}-step-{step_id}",
        "agent": agent_name,
        "step_id": step_id,
        STEP_TEXT_KEY: step_text,
        "involves_http_call": involves_http_call(step_text),
        "involves_db_query": involves_db_query(step_text),
        "involves_file_write": involves_file_write(step_text),
        "involves_assertion": involves_assertion(step_text),
        "involves_metric_check": involves_metric_check(step_text),
        "expected_outcome": expected_outcome(step_text),
        "fail_condition": fail_condition(spec_text),
    }


def build_agent_cases(agent_name: str, spec_text: str) -> dict:
    """Deterministic per-agent extraction result.

    Returns {parse_error: bool, steps: [(id, text)], cases: [objects]}.
    parse_error is True when the How section is absent/empty (no cases emitted).
    """
    how_text = extract_how(spec_text)
    if not how_text:
        return {"parse_error": True, "steps": [], "cases": []}
    steps = extract_steps(how_text)
    cases = [build_test_case(agent_name, sid, stext, spec_text) for sid, stext in steps]
    return {"parse_error": False, "steps": steps, "cases": cases}


def build_reference_registry(agents: list[dict]) -> dict:
    """The canonical CORRECT registry for a list of agent specs.

    Each `agents` element: {name, spec_text}. (Disabled agents are excluded by the
    caller; only enabled agents reach here.) Returns the gold registry + the gold
    summary/gaps used to score an emitted registry and as the metric ground truth.
    """
    registry: list[dict] = []
    total_steps = 0
    parse_errors: list[str] = []
    for a in agents:
        result = build_agent_cases(a["name"], a["spec_text"])
        total_steps += len(result["steps"])
        if result["parse_error"]:
            parse_errors.append(a["name"])
            continue
        registry.extend(result["cases"])

    registry.sort(key=lambda tc: tc["tc_id"])
    total_tc = len(registry)
    gaps_found = total_tc != total_steps
    summary = {
        "agents_processed": len(agents),
        "agents_parse_error": len(parse_errors),
        "total_steps_extracted": total_steps,
        "total_test_cases_created": total_tc,
        "coverage_rate": round(100.0 * total_tc / total_steps, 2) if total_steps else 0.0,
        "http_call_count": sum(1 for tc in registry if tc["involves_http_call"]),
        "db_query_count": sum(1 for tc in registry if tc["involves_db_query"]),
        "file_write_count": sum(1 for tc in registry if tc["involves_file_write"]),
        "assertion_count": sum(1 for tc in registry if tc["involves_assertion"]),
        "gaps_found": gaps_found,
        "gap_count": total_steps - total_tc,
    }
    return {"registry": registry, "summary": summary, "parse_error_agents": parse_errors}


# --------------------------------------------------------------------------- #
# Scoring: an emitted registry vs the gold registry.
# --------------------------------------------------------------------------- #
def _index_by_tc_id(registry: list[dict]) -> dict[str, dict]:
    out: dict[str, dict] = {}
    for tc in registry or []:
        if isinstance(tc, dict) and isinstance(tc.get("tc_id"), str):
            out.setdefault(tc["tc_id"], tc)
    return out


def field_matches(field: str, emitted, gold) -> bool:
    if field in BOOL_FIELDS:
        return isinstance(emitted, bool) and bool(emitted) == bool(gold)
    return isinstance(emitted, str) and emitted == gold


def score_registry(emitted: list[dict], gold_registry: list[dict]) -> dict:
    """Coverage (gold tc_ids present in emitted) + field accuracy over present cells.

    coverage_rate_pct  = present_tc / gold_tc * 100  (the headline n600 metric)
    field_accuracy_pct = correct_fields / (present_tc * 11) * 100  (tiebreaker)
    """
    gold_idx = _index_by_tc_id(gold_registry)
    emit_idx = _index_by_tc_id(emitted)

    present = 0
    correct_fields = 0
    cells = []
    missing = []
    for tc_id, gold_tc in gold_idx.items():
        em = emit_idx.get(tc_id)
        if em is None:
            missing.append({"agent": gold_tc["agent"], "step_id": gold_tc["step_id"],
                            "tc_id": tc_id, "reason": "extraction_failure"})
            continue
        present += 1
        for field in REGISTRY_FIELDS:
            ok = (field in em) and field_matches(field, em.get(field), gold_tc.get(field))
            correct_fields += 1 if ok else 0
            if not ok:
                cells.append({"tc_id": tc_id, "field": field,
                              "gold": gold_tc.get(field), "emitted": em.get(field)})

    gold_tc = len(gold_idx)
    coverage = round(100.0 * present / gold_tc, 2) if gold_tc else 0.0
    denom = present * len(REGISTRY_FIELDS)
    field_acc = round(100.0 * correct_fields / denom, 2) if denom else 0.0
    return {
        "coverage_rate_pct": coverage,
        "field_accuracy_pct": field_acc,
        "gold_tc": gold_tc,
        "present_tc": present,
        "missing_tc": missing,
        "field_mismatches": cells,
    }
