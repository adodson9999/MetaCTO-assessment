"""Canonical structure for the api-tester / create-postman-collection task ("n601").

ONE definition of the Postman-generation contract + the per-scenario evaluation, shared
by:
  - the deterministic gold reference (data/create-postman-collection/build_gold.py),
  - the production CLI (scripts/postman_collection_cli.py), and
  - the harness (agents/common/postman.py) — which applies whatever CONTRACT an agent
    emitted to the registry and scores the resulting collection on the same scenario-key
    scheme.

Pure: no env, no I/O, no LLM, no HTTP. Keeps agent output and the gold set on the same
scenario-key scheme so the judge can compare them field-for-field.

What the agent emits (and what gold/the CLI use):
A *Postman Generation Contract* — the tunable knobs of n601 steps 3-8 (the method/path/
status regexes, the body-trigger substrings, the ordered header-trigger map, the folder
group key, the collection variables, the base_url, the collection-name prefix). The
deterministic substrate (read the registry, gap pre-check, filter involves_http_call,
build one item per HTTP test case via this contract, group into per-agent folders,
assemble the collection, read it back, recursively count request items, write the gaps
and summary files, run Newman) is identical for every agent, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing.

DummyJSON is NOT touched and NOT used: n601 is a pure registry->collection transform
over JSON files; it makes no HTTP calls of its own.
"""
from __future__ import annotations

import re

# --------------------------------------------------------------------------- #
# Canonical extraction constants (n601 step 3, verbatim from the spec)
# --------------------------------------------------------------------------- #
METHOD_PATTERN = r"\b(GET|POST|PUT|DELETE|PATCH|HEAD)\b"
DEFAULT_METHOD = "GET"
PATH_PATTERN = r"(\/[\w\-\.{}\/]+)"
DEFAULT_PATH = "/unknown"
BODY_TRIGGERS = ["with body", "with a valid body", "body:", "body ="]
STATUS_PRIMARY = (
    r"(?:Assert(?:s)?\s+(?:response\s+)?(?:code\s+)?"
    r"(?:=|equals|is\s+exactly|exactly)\s*)([1-9][0-9]{2})"
)
STATUS_FALLBACK = r"→\s+assert\s+(?:exactly\s*)?([1-9][0-9]{2})"

# Ordered header-trigger map (n601 step 3d). Each: substring -> Postman header object.
HEADER_TRIGGERS = [
    {"match": "Authorization", "key": "Authorization", "value": "{{auth_token}}"},
    {"match": "X-Correlation-ID", "key": "X-Correlation-ID", "value": "{{corr_id}}"},
    {"match": "If-None-Match", "key": "If-None-Match", "value": "{{etag_value}}"},
    {"match": "Content-Type: multipart", "key": "Content-Type", "value": "multipart/form-data"},
    {"match": "Idempotency-Key", "key": "Idempotency-Key", "value": "{{idempotency_key}}"},
]

# Collection-level variables (n601 step 7).
VARIABLES = [
    {"key": "base_url", "value": "http://localhost:8080", "type": "string"},
    {"key": "auth_token", "value": "", "type": "string"},
    {"key": "corr_id", "value": "", "type": "string"},
    {"key": "etag_value", "value": "", "type": "string"},
    {"key": "idempotency_key", "value": "", "type": "string"},
]

BASE_URL = "http://localhost:8080"
COLLECTION_NAME_PREFIX = "API Test Agent Suite"
FILTER_FIELD = "involves_http_call"
GROUP_BY = "agent"
SCHEMA_URL = "https://schema.getpostman.com/json/collection/v2.1.0/collection.json"

# The ordered scenario set scored per run (the fidelity metric denominator).
SCENARIO_LABELS = [
    "gaps_precheck_pass",     # summary.gaps_found == false -> n601 may proceed
    "http_tc_count",          # canonical count of involves_http_call==true cases
    "postman_item_count",     # recursive-walk count of request items in the collection
    "count_matches",          # postman_item_count == http_tc_count
    "coverage_rate",          # round(items / http_tc * 100, 2)
    "gaps_found_false",       # no unrepresented HTTP test cases
    "agents_covered",         # distinct agents with >=1 item
    "all_items_named_tc_id",  # every request item name is exactly a tc_id (1:1 with HTTP set)
    "methods_correct",        # each item's request.method == canonical extraction
    "paths_correct",          # each item's url.raw + path array == canonical extraction
    "statuses_correct",       # each item's test-script exec == canonical status assertion
    "headers_correct",        # each item's header array == canonical header triggers
    "bodies_correct",         # each item's body mode/raw/options == canonical
    "variables_correct",      # collection variable array == the 5 canonical variables
]


# --------------------------------------------------------------------------- #
# The contract the agent emits (and the gold/CLI reference)
# --------------------------------------------------------------------------- #
def reference_contract(cfg: dict | None = None) -> dict:
    """The canonical CORRECT contract, derived from the constants above (+ cfg overrides).
    An agent that emits this contract reproduces the gold collection exactly."""
    cfg = cfg or {}
    base_url = cfg.get("base_url", BASE_URL)
    variables = [dict(v) for v in VARIABLES]
    if base_url != BASE_URL:
        for v in variables:
            if v["key"] == "base_url":
                v["value"] = base_url
    return {
        "filter_field": cfg.get("filter_field", FILTER_FIELD),
        "method_pattern": METHOD_PATTERN,
        "default_method": DEFAULT_METHOD,
        "path_pattern": PATH_PATTERN,
        "default_path": DEFAULT_PATH,
        "body_triggers": list(BODY_TRIGGERS),
        "header_triggers": [dict(h) for h in HEADER_TRIGGERS],
        "status_pattern_primary": STATUS_PRIMARY,
        "status_pattern_fallback": STATUS_FALLBACK,
        "group_by": cfg.get("group_by", GROUP_BY),
        "base_url": base_url,
        "variables": variables,
        "collection_name_prefix": cfg.get("collection_name_prefix", COLLECTION_NAME_PREFIX),
    }


def _c(contract: dict, key: str, default):
    if not isinstance(contract, dict):
        return default
    val = contract.get(key, default)
    return val if val is not None else default


# --------------------------------------------------------------------------- #
# Per-field extraction (n601 step 3) — parametrised by the contract
# --------------------------------------------------------------------------- #
# Build-path fallbacks are deliberately BENIGN-WRONG (empty), NOT the canonical
# constants: if an agent's contract omits a required knob, the built collection must
# DIVERGE from gold (an omitted knob is a defect, not a free pass). The gold/CLI path
# always uses reference_contract(), which sets every knob explicitly, so these empty
# fallbacks never fire for the reference.
def extract_method(text: str, contract: dict) -> str:
    pat = _c(contract, "method_pattern", "")
    default = _c(contract, "default_method", "")
    return _first_group(pat, text, default)


def extract_path(text: str, contract: dict) -> str:
    pat = _c(contract, "path_pattern", "")
    default = _c(contract, "default_path", "")
    return _first_group(pat, text, default)


def _first_group(pat: str, text: str, default: str) -> str:
    """First capture group of pat in text, else default. An empty/groupless/invalid
    pattern yields the default (so an omitted contract knob diverges from gold)."""
    if not pat:
        return default
    try:
        m = re.search(pat, text or "")
    except re.error:
        return default
    if not m or m.re.groups < 1:
        return default
    return m.group(1)


def extract_body(text: str, contract: dict) -> tuple[str, str, dict]:
    """Return (mode, raw, options) per n601 step 3c."""
    triggers = _c(contract, "body_triggers", [])
    t = text or ""
    if any(sub in t for sub in triggers):
        return "raw", "{}", {"raw": {"language": "json"}}
    return "none", "", {}


def extract_headers(text: str, contract: dict) -> list:
    """Append a header object for every trigger substring present, in contract order."""
    out: list = []
    t = text or ""
    for h in _c(contract, "header_triggers", []):
        if not isinstance(h, dict):
            continue
        if h.get("match") and h["match"] in t:
            out.append({"key": h.get("key", ""), "value": h.get("value", ""), "type": "text"})
    return out


def extract_status(text: str, contract: dict) -> int:
    """First primary-pattern match, else fallback, else 0 (n601 step 3e)."""
    t = text or ""
    for key in ("status_pattern_primary", "status_pattern_fallback"):
        pat = _c(contract, key, "")
        if not pat:
            continue
        try:
            m = re.search(pat, t)
        except re.error:
            continue
        if m and m.re.groups >= 1:
            try:
                return int(m.group(1))
            except (ValueError, IndexError):
                return 0
    return 0


def path_array(url_path: str) -> list:
    """Split on '/', drop empties (n601 step 3f)."""
    return [seg for seg in (url_path or "").split("/") if seg]


def test_lines(tc_id: str, status: int) -> list:
    """Postman test-script exec lines (n601 step 4). NOTE: the spec's draft had an
    obvious typo 'functi()'; valid JavaScript requires 'function()', so the collection is
    importable + Newman-runnable."""
    if status > 0:
        return [
            f"pm.test('{tc_id} status {status}', function() {{",
            f"  pm.response.to.have.status({status});",
            "});",
            f"pm.test('{tc_id} response time < 5000ms', function() {{",
            "  pm.expect(pm.response.responseTime).to.be.below(5000);",
            "});",
        ]
    return [
        f"pm.test('{tc_id} — expected status unknown, verify manually', function() {{",
        "  pm.expect(pm.response.code).to.be.above(0);",
        "});",
    ]


# --------------------------------------------------------------------------- #
# Collection assembly (n601 steps 5-8)
# --------------------------------------------------------------------------- #
def build_item(tc: dict, contract: dict) -> dict:
    tc_id = tc.get("tc_id", "")
    text = tc.get("step_text", "")
    method = extract_method(text, contract)
    url_path = extract_path(text, contract)
    body_mode, body_raw, body_options = extract_body(text, contract)
    headers = extract_headers(text, contract)
    status = extract_status(text, contract)
    base_url = _c(contract, "base_url", "")
    return {
        "name": tc_id,
        "request": {
            "method": method,
            "header": headers,
            "url": {
                "raw": "{{base_url}}" + url_path,
                "host": ["{{base_url}}"],
                "path": path_array(url_path),
            },
            "body": {"mode": body_mode, "raw": body_raw, "options": body_options},
        },
        "response": [],
        "event": [
            {
                "listen": "test",
                "script": {"type": "text/javascript", "exec": test_lines(tc_id, status)},
            }
        ],
        "_n601": {"method": method, "path": url_path, "status": status,
                  "body_mode": body_mode, "header_keys": [h["key"] for h in headers]},
    }


def filter_http(registry: list, contract: dict) -> list:
    """The involves_http_call==true subset, in registry order (n601 step 2)."""
    field = _c(contract, "filter_field", "")
    if not field:
        return []
    out = []
    for tc in (registry or []):
        if isinstance(tc, dict) and bool(tc.get(field)) is True:
            out.append(tc)
    return out


def _ordered_agents(http_tcs: list, contract: dict) -> list:
    """Distinct agent names in first-appearance order (n601 step 6)."""
    key = _c(contract, "group_by", "")
    seen, order = set(), []
    for tc in http_tcs:
        a = tc.get(key, "")
        if a not in seen:
            seen.add(a)
            order.append(a)
    return order


def build_collection(http_tcs: list, contract: dict, iso_date: str, postman_id: str) -> dict:
    """Assemble the full Postman v2.1 collection (n601 steps 5-8)."""
    key = _c(contract, "group_by", "")
    items_by_agent: dict[str, list] = {}
    for tc in http_tcs:
        items_by_agent.setdefault(tc.get(key, ""), []).append(build_item(tc, contract))

    folders = []
    for agent in _ordered_agents(http_tcs, contract):
        folders.append({
            "name": agent,
            "item": items_by_agent.get(agent, []),
            "description": f"Test cases for agent {agent} — auto-generated by n601",
        })

    prefix = _c(contract, "collection_name_prefix", "")
    return {
        "info": {
            "name": f"{prefix} — {iso_date}",
            "_postman_id": postman_id,
            "description": ("Auto-generated by n601 from test-case-registry.json. Every "
                            "item name matches a tc_id in the registry. Do not rename "
                            "items manually."),
            "schema": SCHEMA_URL,
        },
        "variable": [dict(v) for v in _c(contract, "variables", [])],
        "item": folders,
    }


# --------------------------------------------------------------------------- #
# Recursive walk (n601 step 9)
# --------------------------------------------------------------------------- #
def collect_request_items(node, acc: list | None = None) -> list:
    """Every dict that has a 'request' key, at any nesting depth."""
    acc = [] if acc is None else acc
    if isinstance(node, dict):
        if "request" in node:
            acc.append(node)
        for v in node.values():
            collect_request_items(v, acc)
    elif isinstance(node, list):
        for v in node:
            collect_request_items(v, acc)
    return acc


def recursive_item_count(collection) -> int:
    return len(collect_request_items(collection))


# --------------------------------------------------------------------------- #
# Evaluation -> observed scenario tokens
# --------------------------------------------------------------------------- #
def _strip_internal(item: dict) -> dict:
    """Item without the _n601 debug annotation, for field-equality comparisons."""
    return {k: v for k, v in item.items() if k != "_n601"}


def evaluate(collection: dict, registry: list, summary: dict, cfg: dict | None = None) -> dict:
    """Compute the observed token for every scenario from a built collection.

    Truth (the canonical HTTP set, the expected items, the variables) is recomputed here
    from the reference contract over the registry, so an agent that built the collection
    from a divergent contract diverges on the relevant *_correct token. A token of
    'missing' marks a fact the collection never expressed (counts as a mismatch vs gold).
    """
    cfg = cfg or {}
    ref = reference_contract(cfg)
    canonical = filter_http(registry, ref)
    n_canon = len(canonical)

    built_items = collect_request_items(collection or {})
    item_count = len(built_items)
    by_name = {it.get("name"): it for it in built_items}
    expected = {tc.get("tc_id"): build_item(tc, ref) for tc in canonical}

    obs: dict[str, str] = {}

    # gap pre-check (n601 step 1)
    gp = summary.get("gaps_found") if isinstance(summary, dict) else None
    obs["gaps_precheck_pass"] = "true" if gp is False else ("false" if gp is True else "missing")

    obs["http_tc_count"] = str(n_canon)
    obs["postman_item_count"] = str(item_count)
    obs["count_matches"] = "true" if item_count == n_canon else "false"

    rate = round(100.0 * item_count / n_canon, 2) if n_canon else 0.0
    obs["coverage_rate"] = repr(rate)  # e.g. '100.0'

    obs["gaps_found_false"] = "true" if item_count == n_canon else "false"

    # agents_covered reflects the AGENT's actual top-level folder grouping (so a wrong
    # group_by is caught): distinct top-level folders that hold >=1 request item.
    folders = collection.get("item", []) if isinstance(collection, dict) else []
    folder_names = {f.get("name") for f in folders
                    if isinstance(f, dict) and collect_request_items(f)}
    obs["agents_covered"] = str(len(folder_names))

    canon_ids = sorted(tc.get("tc_id") for tc in canonical)
    built_ids = sorted(n for n in by_name.keys() if n is not None)
    obs["all_items_named_tc_id"] = "true" if built_ids == canon_ids and built_ids else "false"

    def _all(field_getter) -> str:
        if not expected:
            return "missing"
        for tcid, exp in expected.items():
            act = by_name.get(tcid)
            if act is None or field_getter(act) != field_getter(exp):
                return "false"
        return "true"

    obs["methods_correct"] = _all(lambda it: it["request"]["method"])
    obs["paths_correct"] = _all(lambda it: (it["request"]["url"].get("raw"),
                                            it["request"]["url"].get("path")))
    obs["statuses_correct"] = _all(lambda it: it["event"][0]["script"]["exec"])
    obs["headers_correct"] = _all(lambda it: it["request"].get("header"))
    obs["bodies_correct"] = _all(lambda it: it["request"].get("body"))

    exp_vars = [dict(v) for v in _c(ref, "variables", VARIABLES)]
    act_vars = collection.get("variable") if isinstance(collection, dict) else None
    obs["variables_correct"] = "true" if act_vars == exp_vars else "false"

    return obs


def ideal_for(registry: list, cfg: dict | None = None) -> dict:
    """The token a spec-correct n601 produces over this registry (count tokens scale)."""
    cfg = cfg or {}
    ref = reference_contract(cfg)
    canonical = filter_http(registry, ref)
    n = len(canonical)
    grp = _c(ref, "group_by", GROUP_BY)
    n_agents = len({tc.get(grp) for tc in canonical})
    d = {
        "gaps_precheck_pass": "true",
        "http_tc_count": str(n),
        "postman_item_count": str(n),
        "count_matches": "true",
        "coverage_rate": repr(round(100.0, 2)),
        "gaps_found_false": "true",
        "agents_covered": str(n_agents),
        "all_items_named_tc_id": "true",
        "methods_correct": "true",
        "paths_correct": "true",
        "statuses_correct": "true",
        "headers_correct": "true",
        "bodies_correct": "true",
        "variables_correct": "true",
    }
    return d


def correct(scenario: str, observed_token: str, ideal: dict) -> bool:
    return observed_token == ideal.get(scenario)


def coverage_rate(item_count: int, http_tc_count: int) -> float:
    """Headline Postman Coverage Rate (n601 metric)."""
    return round(100.0 * item_count / http_tc_count, 2) if http_tc_count else 0.0
