"""Canonical scenario structure for the API sorting-behavior testing task.

ONE definition of the sort test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/verify-sorting-behavior/build_gold.py), and
  - the harness (agents/common/sorting.py) — which seeds an isolated reference
    resource with the plan's seed records, executes the plan's sort requests, and
    scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM, no HTTP. Keeps agent output and the gold set on the
same (scenario) key scheme so the judge can compare them field-for-field.

Why an isolated reference resource and NOT DummyJSON
----------------------------------------------------
This task is inherently stateful: it seeds 20 records with known, non-sequential
"name" values and `created_at` timestamps inserted two seconds apart, then verifies
that ascending/descending GETs return every adjacent pair in the correct order, and
that an invalid sort field and an invalid order direction each yield 400. DummyJSON
is tested read-only by every other agent in this foundry and MUST NEVER be modified
(it has no seamable `created_at` field, uses `sortBy` not `sort`, and silently
ignores an unknown sort field with 200 rather than 400). So seeding it is impossible
without mutating it. Instead, the harness stands up a small, in-process, loopback-only
reference resource (agents/common/sortserver.py) that implements the idealized sort
contract, seeds it with the AGENT's emitted seed records, and issues real read-only
GETs to it. DummyJSON is never touched by this task at all. The reference resource is
deterministic substrate (no debate-gated prompt line), exactly like sorting.py.

The idealized sort contract the reference resource implements:
  GET /resources?sort=<field>&order=<asc|desc>
    - sort must be one of the seamable fields {name, created_at}; any other value
      (e.g. "nonexistent_field") -> 400 with a message naming the invalid field.
    - order, when present, must be one of {asc, desc}; any other value
      (e.g. "sideways") -> 400. order defaults to "asc" when absent.
    - on success -> 200 with {"resources": [...sorted...], "total": <count>}.
    - name sorts case-insensitively; created_at sorts as ISO-8601 instants.

A plan (the agent's output, and the reference) looks like:
  {
    "resource_path": "/resources",
    "list_field": "resources",
    "name_field": "name",
    "timestamp_field": "created_at",
    "seed": [ {"name": "Zebra", "created_at": "2026-06-25T12:00:00Z"}, ... 20 total ],
    "sort_cases": [
      {"label": "asc_by_name",   "type": "order", "field": "name",       "direction": "asc",  "params": {"sort": "name",       "order": "asc"},  "expect_status": 200},
      {"label": "desc_by_name",  "type": "order", "field": "name",       "direction": "desc", "params": {"sort": "name",       "order": "desc"}, "expect_status": 200},
      {"label": "asc_by_created_at",  "type": "order", "field": "created_at", "direction": "asc",  "params": {"sort": "created_at", "order": "asc"},  "expect_status": 200},
      {"label": "desc_by_created_at", "type": "order", "field": "created_at", "direction": "desc", "params": {"sort": "created_at", "order": "desc"}, "expect_status": 200},
      {"label": "invalid_sort_field",      "type": "invalid_field", "invalid_field_name": "nonexistent_field", "params": {"sort": "nonexistent_field"}, "expect_status": 400},
      {"label": "invalid_order_direction", "type": "invalid_order", "params": {"sort": "name", "order": "sideways"}, "expect_status": 400}
    ]
  }

The agent emits these six cases plus the 20 seed records; the harness derives the
12 scored scenarios below from the executed plan.
"""
from __future__ import annotations

from datetime import datetime, timedelta, timezone

# --------------------------------------------------------------------------- #
# The fixed seed: 20 distinct, non-alphabetically-sequential "name" values, with
# created_at timestamps two seconds apart in insertion order (so created_at sort
# order == insertion order, while name sort order is a genuine re-ordering).
# --------------------------------------------------------------------------- #
SEED_NAMES = [
    "Zebra", "Apple", "Mango", "Quartz", "Lemon",
    "Cobalt", "Violet", "Indigo", "Bronze", "Walnut",
    "Olive", "Falcon", "Topaz", "Daisy", "Saffron",
    "Hazel", "Nutmeg", "Garnet", "Yarrow", "Emerald",
]
SEED_COUNT = 20
SEED_BASE_TS = "2026-06-25T12:00:00Z"   # first record; each subsequent +2 seconds
SEED_STEP_SECONDS = 2


def _iso(dt: datetime) -> str:
    return dt.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")


def seed_records() -> list[dict]:
    """The canonical 20 seed records, in insertion order."""
    base = parse_iso(SEED_BASE_TS)
    return [
        {"name": name, "created_at": _iso(base + timedelta(seconds=SEED_STEP_SECONDS * i))}
        for i, name in enumerate(SEED_NAMES)
    ]


def parse_iso(value: str) -> datetime:
    """Parse an ISO-8601 instant (tolerating a trailing Z) to an aware datetime."""
    s = str(value).strip().replace("Z", "+00:00")
    dt = datetime.fromisoformat(s)
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt


# The exact six executable sort cases the agent must emit, by label.
CASE_LABELS = [
    "asc_by_name",
    "desc_by_name",
    "asc_by_created_at",
    "desc_by_created_at",
    "invalid_sort_field",
    "invalid_order_direction",
]

# The seamable fields and the valid order directions of the idealized contract.
SORTABLE_FIELDS = ["name", "created_at"]
VALID_ORDERS = ["asc", "desc"]
INVALID_SORT_FIELD = "nonexistent_field"
INVALID_ORDER_VALUE = "sideways"

# The full, ordered scenario set scored (the metric denominator). Each scenario's
# `ideal` is the token the idealized contract produces; gold records the reference
# resource's REAL token (which equals ideal, the resource being correct-by-construction).
SCENARIOS = [
    ("asc_by_name_status",             "200"),
    ("asc_by_name_ordering",           "true"),
    ("desc_by_name_status",            "200"),
    ("desc_by_name_ordering",          "true"),
    ("asc_by_created_at_status",       "200"),
    ("asc_by_created_at_ordering",     "true"),
    ("desc_by_created_at_status",      "200"),
    ("desc_by_created_at_ordering",    "true"),
    ("invalid_sort_field_status",      "400"),
    ("invalid_sort_field_message",     "true"),   # 400 body names the invalid field
    ("invalid_order_direction_status", "400"),
    ("seed_count",                     "true"),    # exactly 20 distinct records seeded
]
SCENARIO_LABELS = [s for s, _ in SCENARIOS]
IDEAL = dict(SCENARIOS)

# The four ordering scenarios are the headline Sorting Accuracy Rate denominator.
ORDERING_SCENARIOS = [
    "asc_by_name_ordering",
    "desc_by_name_ordering",
    "asc_by_created_at_ordering",
    "desc_by_created_at_ordering",
]


def build_reference_plan() -> dict:
    """The canonical CORRECT plan: 20 seed records + the six sort cases. This is
    what the gold reference executes; the agents must reproduce it from their brief."""
    return {
        "resource_path": "/resources",
        "list_field": "resources",
        "name_field": "name",
        "timestamp_field": "created_at",
        "seed": seed_records(),
        "sort_cases": [
            {"label": "asc_by_name", "type": "order", "field": "name", "direction": "asc",
             "params": {"sort": "name", "order": "asc"}, "expect_status": 200},
            {"label": "desc_by_name", "type": "order", "field": "name", "direction": "desc",
             "params": {"sort": "name", "order": "desc"}, "expect_status": 200},
            {"label": "asc_by_created_at", "type": "order", "field": "created_at", "direction": "asc",
             "params": {"sort": "created_at", "order": "asc"}, "expect_status": 200},
            {"label": "desc_by_created_at", "type": "order", "field": "created_at", "direction": "desc",
             "params": {"sort": "created_at", "order": "desc"}, "expect_status": 200},
            {"label": "invalid_sort_field", "type": "invalid_field",
             "invalid_field_name": INVALID_SORT_FIELD,
             "params": {"sort": INVALID_SORT_FIELD}, "expect_status": 400},
            {"label": "invalid_order_direction", "type": "invalid_order",
             "params": {"sort": "name", "order": INVALID_ORDER_VALUE}, "expect_status": 400},
        ],
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
    if code == 404:
        return "404"
    return f"other_{code}"


def _ordering_holds(records, field: str, direction: str, name_field: str,
                    timestamp_field: str) -> str:
    """'true'/'false'/'missing' for whether every adjacent pair of `records` is in
    `direction` order on `field`. One out-of-order pair => 'false'."""
    if not isinstance(records, list) or len(records) < 2:
        return "missing"
    keys = []
    for r in records:
        if not isinstance(r, dict) or field not in r:
            return "false"
        v = r[field]
        if field == name_field:
            keys.append(str(v).lower())
        elif field == timestamp_field:
            try:
                keys.append(parse_iso(v))
            except Exception:  # noqa
                return "false"
        else:
            keys.append(v)
    if direction == "asc":
        return "true" if all(keys[i] <= keys[i + 1] for i in range(len(keys) - 1)) else "false"
    return "true" if all(keys[i] >= keys[i + 1] for i in range(len(keys) - 1)) else "false"


def _message_names_field(case_rec: dict, field_name: str) -> str:
    """'true' if the 400 body's message references the invalid sort field name."""
    if not case_rec or case_rec.get("status") != 400:
        return "missing"
    msg = case_rec.get("message")
    if not isinstance(msg, str):
        return "false"
    return "true" if field_name.lower() in msg.lower() else "false"


def evaluate(case_obs: dict, seed_meta: dict, name_field: str = "name",
             timestamp_field: str = "created_at") -> dict:
    """Compute the observed token for every scenario from raw per-case observations.

    case_obs : {case_label: {"status": int, "records": [...]|None, "message": str|None}}
               A missing case label => the agent never emitted that case.
    seed_meta: {"emitted": int, "distinct": int} describing the agent's seed array.
    """
    obs: dict[str, str] = {}

    def status_tok(label):
        rec = case_obs.get(label)
        return _status_class(rec["status"]) if rec and "status" in rec else "missing"

    for case_label, status_key, order_key, field, direction in (
        ("asc_by_name",        "asc_by_name_status",        "asc_by_name_ordering",        name_field,      "asc"),
        ("desc_by_name",       "desc_by_name_status",       "desc_by_name_ordering",       name_field,      "desc"),
        ("asc_by_created_at",  "asc_by_created_at_status",  "asc_by_created_at_ordering",  timestamp_field, "asc"),
        ("desc_by_created_at", "desc_by_created_at_status", "desc_by_created_at_ordering", timestamp_field, "desc"),
    ):
        rec = case_obs.get(case_label)
        obs[status_key] = _status_class(rec["status"]) if rec and "status" in rec else "missing"
        obs[order_key] = (_ordering_holds(rec.get("records"), field, direction,
                                          name_field, timestamp_field)
                          if rec else "missing")

    obs["invalid_sort_field_status"] = status_tok("invalid_sort_field")
    obs["invalid_sort_field_message"] = _message_names_field(
        case_obs.get("invalid_sort_field"), INVALID_SORT_FIELD)
    obs["invalid_order_direction_status"] = status_tok("invalid_order_direction")

    emitted = seed_meta.get("emitted", 0)
    distinct = seed_meta.get("distinct", 0)
    obs["seed_count"] = "true" if (emitted == SEED_COUNT and distinct == SEED_COUNT) else "false"

    return obs


def correct(scenario: str, observed_token: str) -> bool:
    """Did the API behave per the idealized sort contract for this scenario?"""
    return observed_token == IDEAL[scenario]
