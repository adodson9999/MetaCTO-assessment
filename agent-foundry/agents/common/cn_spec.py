"""Canonical scenario structure for the API content-type-negotiation testing task.

ONE definition of the negotiation test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/verify-content-type-negotiation/build_gold.py), and
  - the harness (agents/common/cn.py) — which executes whatever plan an agent emitted
    and scores it on exactly the same (endpoint, scenario) key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same key
scheme so the judge can compare them field-for-field.

Target reality (DummyJSON, tested as-is — its repo/data are NEVER modified):
  - DummyJSON implements NO content negotiation. It ignores the request `Accept`
    header entirely and always replies 200 with `Content-Type: application/json`,
    and it ignores the request `Content-Type` header entirely (an application/xml
    or text/plain body on POST/PUT is accepted, returning 201/200, never 415).
  - The IDEALIZED RFC-7231 negotiation contract — declared in
    data/verify-content-type-negotiation/cn_openapi.json, which describes the
    contract a properly negotiating API WOULD publish, without touching DummyJSON —
    is what each scenario's `ideal` token encodes. The gold records the API's REAL
    observed token. Where they differ is a genuine QA finding about DummyJSON, not
    an agent bug.

Two endpoint families, both derived from the reused 22-endpoint catalogue:
  - "accept"  family: GET targets (the readable counterpart of each write op,
                       deduped). Exercises Accept-header response negotiation.
  - "consumes" family: the 22 write ops themselves (POST/PUT/PATCH). Exercises
                       request-body Content-Type acceptance (the 415 surface).

A plan for one endpoint (the agent's output, and the reference) looks like, for
an "accept" endpoint:
  {
    "endpoint": "/products", "kind": "accept",
    "probes": [
      {"label": "accept_application_json",          "accept": "application/json"},
      {"label": "accept_application_xml",           "accept": "application/xml"},
      {"label": "accept_text_csv",                  "accept": "text/csv"},
      {"label": "accept_text_html_unsupported",     "accept": "text/html"},
      {"label": "accept_wildcard",                  "accept": "*/*"}
    ]
  }
and for a "consumes" endpoint:
  {
    "endpoint": "/products/add", "kind": "consumes", "method": "POST",
    "probes": [
      {"label": "ctype_application_json_supported",  "content_type": "application/json"},
      {"label": "ctype_application_xml_unsupported", "content_type": "application/xml"},
      {"label": "ctype_text_plain_unsupported",      "content_type": "text/plain"}
    ]
  }
"""
from __future__ import annotations

# Documented contract (cn_openapi.json). GET ops declare these produces; the first
# is the default. Write ops declare a single consumes (application/json).
SUPPORTED_FORMATS = ["application/json", "application/xml", "text/csv"]
DEFAULT_FORMAT = "application/json"
UNSUPPORTED_ACCEPT = "text/html"   # a format NOT in produces -> ideal 406
WILDCARD = "*/*"                    # ideal -> 200 in the default format
SUPPORTED_CONTENT_TYPE = "application/json"
UNSUPPORTED_CONTENT_TYPES = ["application/xml", "text/plain"]   # ideal 415 each

# ---- scenario sets (the metric denominator per endpoint) -------------------- #
ACCEPT_SCENARIOS = [
    ("accept_application_json",       "match"),
    ("accept_application_xml",        "match"),
    ("accept_text_csv",               "match"),
    ("accept_text_html_unsupported",  "406"),
    ("accept_wildcard",               "match"),
]
CONSUMES_SCENARIOS = [
    ("ctype_application_json_supported",  "supported"),
    ("ctype_application_xml_unsupported", "415"),
    ("ctype_text_plain_unsupported",      "415"),
]

# label -> the requested format the accept probe carries (for body-validity checks).
ACCEPT_PROBE_FORMAT = {
    "accept_application_json":      "application/json",
    "accept_application_xml":       "application/xml",
    "accept_text_csv":              "text/csv",
    "accept_text_html_unsupported": "text/html",
    "accept_wildcard":              DEFAULT_FORMAT,   # wildcard => server's default
}
ACCEPT_PROBE_ACCEPT_HEADER = {
    "accept_application_json":      "application/json",
    "accept_application_xml":       "application/xml",
    "accept_text_csv":              "text/csv",
    "accept_text_html_unsupported": UNSUPPORTED_ACCEPT,
    "accept_wildcard":              WILDCARD,
}
CONSUMES_PROBE_CONTENT_TYPE = {
    "ctype_application_json_supported":  "application/json",
    "ctype_application_xml_unsupported": "application/xml",
    "ctype_text_plain_unsupported":      "text/plain",
}

ACCEPT_LABELS = [s for s, _ in ACCEPT_SCENARIOS]
CONSUMES_LABELS = [s for s, _ in CONSUMES_SCENARIOS]
IDEAL_ACCEPT = dict(ACCEPT_SCENARIOS)
IDEAL_CONSUMES = dict(CONSUMES_SCENARIOS)

# Format-match scenarios (vs the 406 status scenario) within the accept family.
_ACCEPT_MATCH_LABELS = {
    "accept_application_json", "accept_application_xml",
    "accept_text_csv", "accept_wildcard",
}


def scenarios_for(kind: str) -> list[str]:
    return ACCEPT_LABELS if kind == "accept" else CONSUMES_LABELS


def ideal_for(kind: str) -> dict:
    return dict(IDEAL_ACCEPT) if kind == "accept" else dict(IDEAL_CONSUMES)


# --------------------------------------------------------------------------- #
# Reference plan (the canonical CORRECT probe matrix for one endpoint)
# --------------------------------------------------------------------------- #
def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan for one endpoint, derived deterministically
    from its kind. Identical to what a perfectly-behaving agent emits."""
    if cfg["kind"] == "accept":
        return {
            "endpoint": cfg["endpoint"],
            "kind": "accept",
            "probes": [
                {"label": lbl, "accept": ACCEPT_PROBE_ACCEPT_HEADER[lbl]}
                for lbl in ACCEPT_LABELS
            ],
        }
    return {
        "endpoint": cfg["endpoint"],
        "kind": "consumes",
        "method": cfg["method"],
        "probes": [
            {"label": lbl, "content_type": CONSUMES_PROBE_CONTENT_TYPE[lbl]}
            for lbl in CONSUMES_LABELS
        ],
    }


# --------------------------------------------------------------------------- #
# Evaluation: raw observations -> observed token per scenario
# --------------------------------------------------------------------------- #
def _ct_matches(actual_ct: str | None, fmt: str) -> bool:
    """Per the task: the response Content-Type header 'begins with' the format,
    so 'application/json; charset=utf-8' satisfies Accept: application/json."""
    if not actual_ct:
        return False
    return actual_ct.strip().lower().startswith(fmt.lower())


def evaluate_accept(probe_obs: dict) -> dict:
    """probe_obs: {label: {"status":int, "content_type":str|None, "body_valid":bool}}
    Missing labels => that probe was not emitted by the agent (scores 'missing')."""
    obs: dict[str, str] = {}
    for label in ACCEPT_LABELS:
        rec = probe_obs.get(label)
        if not rec:
            obs[label] = "missing"
            continue
        if label in _ACCEPT_MATCH_LABELS:
            fmt = ACCEPT_PROBE_FORMAT[label]
            ok = (rec.get("status") == 200
                  and _ct_matches(rec.get("content_type"), fmt)
                  and bool(rec.get("body_valid")))
            obs[label] = "match" if ok else "mismatch"
        else:  # accept_text_html_unsupported -> status-class token
            code = rec.get("status")
            obs[label] = "406" if code == 406 else (str(code) if code is not None else "missing")
    return obs


def evaluate_consumes(probe_obs: dict) -> dict:
    """probe_obs: {label: {"status":int}}.  Missing labels => 'missing'."""
    obs: dict[str, str] = {}
    for label in CONSUMES_LABELS:
        rec = probe_obs.get(label)
        if not rec or rec.get("status") is None:
            obs[label] = "missing"
            continue
        code = rec["status"]
        if label == "ctype_application_json_supported":
            obs[label] = "supported" if 200 <= code < 300 else str(code)
        else:
            obs[label] = "415" if code == 415 else str(code)
    return obs


def evaluate(kind: str, probe_obs: dict) -> dict:
    return evaluate_accept(probe_obs) if kind == "accept" else evaluate_consumes(probe_obs)


def correct(kind: str, scenario: str, observed_token: str) -> bool:
    """Did the API behave per the idealized RFC-7231 negotiation contract?"""
    ideal = (IDEAL_ACCEPT if kind == "accept" else IDEAL_CONSUMES)[scenario]
    return observed_token == ideal
