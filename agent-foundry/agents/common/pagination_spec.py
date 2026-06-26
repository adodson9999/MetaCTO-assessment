"""Canonical scenario structure for the API pagination-behavior testing task.

ONE definition of the pagination test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/test-pagination-behavior/build_gold.py), and
  - the harness (agents/common/pagination.py) — which executes whatever plan an
    agent emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(collection, scenario) key scheme so the judge can compare them field-for-field.

Target reality (DummyJSON, tested READ-ONLY as-is — never modified):
  - Offset pagination via query params `limit` (page size) and `skip` (offset).
  - Response shape: {<list_field>:[...], total, skip, limit}. No cursor / next_cursor.
  - "Has next page" is DERIVED: (requested_skip + returned_count) < total.
  - The idealized pagination contract (cursor semantics, strict 400s on bad params)
    is what each scenario's `ideal` token encodes; the gold records the API's REAL
    token. Where they differ is a genuine QA finding about DummyJSON, not an agent bug.

A plan for one collection (the agent's output, and the reference) looks like:
  {
    "collection": "/products", "list_field": "products",
    "id_field": "id", "limit_param": "limit", "offset_param": "skip",
    "page_size": 10, "window_size": 25,
    "pages": [
      {"label": "page1", "limit": 10, "skip": 0},
      {"label": "page2", "limit": 10, "skip": 10},
      {"label": "page3", "limit": 5,  "skip": 20}
    ],
    "invalid": [
      {"label": "invalid_page_size_negative",  "params": {"limit": "-1"}},
      {"label": "invalid_page_size_zero",       "params": {"limit": "0"}},
      {"label": "invalid_page_size_nonnumeric", "params": {"limit": "abc"}},
      {"label": "invalid_cursor",               "params": {"cursor": "invalid-cursor-xyz"}}
    ]
  }
"""
from __future__ import annotations

PAGE_LABELS = ["page1", "page2", "page3"]
INVALID_LABELS = [
    "invalid_page_size_negative",
    "invalid_page_size_zero",
    "invalid_page_size_nonnumeric",
    "invalid_cursor",
]

# The full, ordered scenario set scored per collection (the metric denominator).
# Each scenario carries the idealized expectation under a correct cursor-paginated
# contract over a 25-record window paged by 10. `ideal` is the token a perfectly
# behaving API would produce; gold records the REAL token DummyJSON produces.
SCENARIOS = [
    ("page1_status",                 "200"),
    ("page1_count",                  "10"),
    ("page1_has_next",               "true"),
    ("page2_status",                 "200"),
    ("page2_count",                  "10"),
    ("page2_no_overlap",             "true"),
    ("page2_has_next",               "true"),
    ("page3_status",                 "200"),
    ("page3_count",                  "5"),
    ("page3_no_overlap",             "true"),
    ("page3_is_last",                "true"),   # last page => NO next page
    ("union_unique_count",           "25"),
    ("union_zero_duplicates",        "true"),
    ("union_equals_window",          "true"),
    ("invalid_page_size_negative",   "400"),
    ("invalid_page_size_zero",       "400"),
    ("invalid_page_size_nonnumeric", "400"),
    ("invalid_cursor",               "400_or_422"),
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan for one collection, derived deterministically
    from its config. page3 is capped to the window remainder so the three pages
    partition exactly `window_size` records (10 + 10 + 5 = 25)."""
    ps = cfg["page_size"]
    win = cfg["window_size"]
    lp = cfg.get("limit_param", "limit")
    op = cfg.get("offset_param", "skip")
    pages = []
    skip = 0
    for label in PAGE_LABELS:
        remaining = win - skip
        limit = ps if remaining >= ps else max(remaining, 0)
        pages.append({"label": label, "limit": limit, "skip": skip})
        skip += limit
    invalid = [
        {"label": "invalid_page_size_negative",  "params": {lp: "-1"}},
        {"label": "invalid_page_size_zero",       "params": {lp: "0"}},
        {"label": "invalid_page_size_nonnumeric", "params": {lp: "abc"}},
        {"label": "invalid_cursor",               "params": {"cursor": "invalid-cursor-xyz"}},
    ]
    return {
        "collection": cfg["collection"],
        "list_field": cfg["list_field"],
        "id_field": cfg.get("id_field", "id"),
        "limit_param": lp,
        "offset_param": op,
        "page_size": ps,
        "window_size": win,
        "pages": pages,
        "invalid": invalid,
    }


def _status_class(code) -> str:
    if code is None:
        return "none"
    if 200 <= code < 300:
        return "200"
    if code == 400:
        return "400"
    if code == 422:
        return "422"
    return f"other_{code}"


def evaluate(window_ids: list, page_obs: dict, invalid_obs: dict) -> dict:
    """Compute the observed token for every scenario from raw observations.

    window_ids   : the EXPECTED_IDS list (the 25-record window), order irrelevant.
    page_obs     : {page_label: {"status":int, "ids":[...], "skip":int, "total":int|None}}
                   missing labels => that page was not produced by the agent.
    invalid_obs  : {invalid_label: {"status":int}}  (missing => not produced)

    Returns {scenario_label: observed_token}. "missing" marks a scenario whose
    required request the agent never emitted (counts as a mismatch vs gold).
    """
    obs: dict[str, str] = {}
    window = list(window_ids)

    def ids_of(label):
        rec = page_obs.get(label)
        return list(rec["ids"]) if rec and isinstance(rec.get("ids"), list) else None

    def has_next(label):
        rec = page_obs.get(label)
        if not rec or rec.get("total") is None or not isinstance(rec.get("ids"), list):
            return None
        return (rec.get("skip", 0) + len(rec["ids"])) < rec["total"]

    # page1
    p1 = page_obs.get("page1")
    obs["page1_status"] = _status_class(p1["status"]) if p1 else "missing"
    obs["page1_count"] = str(len(p1["ids"])) if p1 and isinstance(p1.get("ids"), list) else "missing"
    hn1 = has_next("page1")
    obs["page1_has_next"] = ("true" if hn1 else "false") if hn1 is not None else "missing"

    # page2
    p2 = page_obs.get("page2")
    obs["page2_status"] = _status_class(p2["status"]) if p2 else "missing"
    obs["page2_count"] = str(len(p2["ids"])) if p2 and isinstance(p2.get("ids"), list) else "missing"
    i1, i2 = ids_of("page1"), ids_of("page2")
    obs["page2_no_overlap"] = (
        ("true" if set(i1).isdisjoint(i2) else "false") if i1 is not None and i2 is not None else "missing"
    )
    hn2 = has_next("page2")
    obs["page2_has_next"] = ("true" if hn2 else "false") if hn2 is not None else "missing"

    # page3
    p3 = page_obs.get("page3")
    obs["page3_status"] = _status_class(p3["status"]) if p3 else "missing"
    obs["page3_count"] = str(len(p3["ids"])) if p3 and isinstance(p3.get("ids"), list) else "missing"
    i3 = ids_of("page3")
    obs["page3_no_overlap"] = (
        ("true" if set(i3).isdisjoint(set((i1 or []) + (i2 or []))) else "false")
        if i3 is not None and i1 is not None and i2 is not None else "missing"
    )
    hn3 = has_next("page3")
    obs["page3_is_last"] = ("true" if hn3 is False else "false") if hn3 is not None else "missing"

    # union across all three observed pages
    if i1 is not None and i2 is not None and i3 is not None:
        allids = list(i1) + list(i2) + list(i3)
        uniq = set(allids)
        obs["union_unique_count"] = str(len(uniq))
        obs["union_zero_duplicates"] = "true" if len(allids) == len(uniq) else "false"
        obs["union_equals_window"] = "true" if uniq == set(window) else "false"
    else:
        obs["union_unique_count"] = "missing"
        obs["union_zero_duplicates"] = "missing"
        obs["union_equals_window"] = "missing"

    # invalid probes
    for label in INVALID_LABELS:
        rec = invalid_obs.get(label)
        obs[label] = _status_class(rec["status"]) if rec else "missing"

    return obs


def correct(scenario: str, observed_token: str) -> bool:
    """Did the API behave per the idealized pagination contract for this scenario?"""
    ideal = IDEAL[scenario]
    if scenario == "invalid_cursor":
        return observed_token in ("400", "422")
    return observed_token == ideal
