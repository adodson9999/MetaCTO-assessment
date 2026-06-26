"""Canonical scenario structure for the GraphQL-query-depth-limit testing task.

ONE definition of the depth test plan + the per-scenario evaluation + the
deterministic depth->query generator, shared by:
  - the deterministic gold reference (data/validate-graphql-depth-limits/build_gold.py), and
  - the harness (agents/common/gqldepth.py) — which executes whatever plan an agent
    emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(endpoint, scenario) key scheme so the judge can compare them field-for-field.

Target reality (the LOCAL GraphQL depth SUT — see tools/graphql-depth-server;
DummyJSON is never used or modified). The documented depth-limit contract is:
  - depth <= max_depth -> 200, non-null "data", no "errors".
  - depth >  max_depth -> 400, "errors" array (>=1) whose first message mentions
                          "depth" or "complexity", no non-null "data".
  - a too-deep (depth-15) query is rejected in well under one second (the depth check
    runs before any resolution).

Depth means the maximum count of nested field selection sets in a query — NOT
character count or token count.

A plan for one endpoint (the agent's output, and the reference) looks like:
  {
    "endpoint": "/graphql", "max_depth": 7,
    "cases": [
      {"label": "depth_3",   "type": "accept",        "depth": 3},
      {"label": "at_limit",  "type": "accept",        "depth": 7},
      {"label": "one_over",  "type": "reject",        "depth": 8},
      {"label": "deep_15",   "type": "reject_timed",  "depth": 15}
    ]
  }

The agent emits these 4 cases (deriving at_limit=max_depth and one_over=max_depth+1);
the harness builds the GraphQL query for each requested depth, sends it, and derives
the 13 scored scenarios below.
"""
from __future__ import annotations

# The exact four executable cases the agent must emit, by label, with the rule that
# fixes each case's depth relative to the endpoint's max_depth.
CASE_LABELS = ["depth_3", "at_limit", "one_over", "deep_15"]
CASE_TYPE = {
    "depth_3": "accept",
    "at_limit": "accept",
    "one_over": "reject",
    "deep_15": "reject_timed",
}

# The fixed, literal depths.
DEPTH_3 = 3
DEEP_DEPTH = 15
# Below-one-second budget for the deep-query rejection (seconds).
DEEP_TIME_BUDGET_S = 1.0


def reference_depth(label: str, max_depth: int) -> int:
    """The CORRECT depth for a case given the endpoint's max_depth."""
    if label == "depth_3":
        return DEPTH_3
    if label == "at_limit":
        return max_depth
    if label == "one_over":
        return max_depth + 1
    if label == "deep_15":
        return DEEP_DEPTH
    raise KeyError(label)


# The full, ordered scenario set scored per endpoint (the metric denominator).
# Each tuple is (scenario_label, ideal_token). All ideals are fixed constants — the
# documented contract's outcome for a correctly-constructed probe.
SCENARIOS = [
    ("depth_3_status",      "200"),
    ("depth_3_data",        "true"),    # response "data" is non-null
    ("depth_3_no_errors",   "true"),    # no errors key / empty errors
    ("at_limit_status",     "200"),
    ("at_limit_data",       "true"),
    ("at_limit_no_errors",  "true"),
    ("one_over_status",     "400"),
    ("one_over_errors",     "true"),    # errors array has >=1 element
    ("one_over_message",    "true"),    # message contains "depth" or "complexity"
    ("deep_15_status",      "400"),
    ("deep_15_errors",      "true"),
    ("deep_15_message",     "true"),
    ("deep_15_within_1s",   "true"),    # rejection arrived in < 1 second
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
_IDEAL = dict(SCENARIOS)

# Documented depth-limit contract handed to the agent (per endpoint, max_depth varies).
DEPTH_UNIT = "the maximum count of nested field selection sets in a query"


def build_query(depth: int) -> str:
    """Deterministically build a syntactically valid GraphQL query whose selection-set
    nesting depth equals `depth` exactly (server-computed depth == depth). The chain is
    node -> child (depth-2 times) -> name, against the recursive Node schema.

    depth must be >= 2 (an object field always needs a sub-selection). Every depth used
    by this task (3, max_depth>=4, max_depth+1, 15) satisfies that.
    """
    if depth < 2:
        # Degenerate: a single scalar selection (depth 1). Not used by this task.
        return "query { __typename }"
    objs = ["node"] + ["child"] * (depth - 2)
    sel = "{ name }"
    for f in reversed(objs):
        sel = "{ " + f + " " + sel + " }"
    return "query " + sel


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT 4-case depth test plan for one endpoint, derived
    deterministically from its max_depth."""
    md = cfg["max_depth"]
    return {
        "endpoint": cfg["endpoint"],
        "max_depth": md,
        "cases": [
            {"label": lbl, "type": CASE_TYPE[lbl], "depth": reference_depth(lbl, md)}
            for lbl in CASE_LABELS
        ],
    }


def ideal_for(scenario: str) -> str:
    """The idealized expected token for a scenario (a fixed constant)."""
    return _IDEAL[scenario]


def _status_class(code) -> str:
    if code is None:
        return "none"
    if 200 <= code < 300:
        return "200"
    if code == 400:
        return "400"
    if code == 404:
        return "404"
    if code == 405:
        return "405"
    if code == 422:
        return "422"
    return f"other_{code}"


def _message_has_depth_or_complexity(message) -> str:
    if not isinstance(message, str):
        return "false"
    low = message.lower()
    return "true" if ("depth" in low or "complexity" in low) else "false"


def evaluate(case_obs: dict) -> dict:
    """Compute the observed token for every scenario from raw per-case observations.

    case_obs : {case_label: {"status": int, "data_present": bool,
                             "errors": list|None, "message": str|None,
                             "elapsed": float|None}}
               A missing case label => the agent never emitted that case.

    Returns {scenario_label: observed_token}. "missing" marks a scenario whose
    required request the agent never emitted (counts as a mismatch vs gold).
    """
    obs: dict[str, str] = {}

    def rec(label):
        return case_obs.get(label)

    # accept cases
    for lab in ("depth_3", "at_limit"):
        r = rec(lab)
        obs[f"{lab}_status"] = _status_class(r["status"]) if r and "status" in r else "missing"
        if not r:
            obs[f"{lab}_data"] = "missing"
            obs[f"{lab}_no_errors"] = "missing"
        else:
            obs[f"{lab}_data"] = "true" if r.get("data_present") else "false"
            errs = r.get("errors")
            obs[f"{lab}_no_errors"] = "true" if not errs else "false"

    # reject cases
    for lab in ("one_over", "deep_15"):
        r = rec(lab)
        obs[f"{lab}_status"] = _status_class(r["status"]) if r and "status" in r else "missing"
        if not r:
            obs[f"{lab}_errors"] = "missing"
            obs[f"{lab}_message"] = "missing"
        else:
            errs = r.get("errors")
            obs[f"{lab}_errors"] = "true" if (isinstance(errs, list) and len(errs) >= 1) else "false"
            obs[f"{lab}_message"] = _message_has_depth_or_complexity(r.get("message"))

    # deep_15 timing
    r = rec("deep_15")
    if not r:
        obs["deep_15_within_1s"] = "missing"
    else:
        el = r.get("elapsed")
        obs["deep_15_within_1s"] = ("true" if isinstance(el, (int, float)) and el < DEEP_TIME_BUDGET_S
                                    else "false")
    return obs


def correct(scenario: str, observed_token: str) -> bool:
    """Did the API behave per the idealized depth-limit contract for this scenario?"""
    return observed_token == ideal_for(scenario)
