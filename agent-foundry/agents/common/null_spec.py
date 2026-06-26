"""Canonical structure for the API null-and-empty-fields testing task.

ONE definition of the labeled test matrix + the per-case idealized contract,
shared by:
  - the deterministic gold reference (data/validate-null-empty-fields/build_gold.py), and
  - the harness (agents/common/null_contract.py) — which iterates whatever an agent
    emitted and scores it on exactly the same (category, label) key scheme.

Pure: no env, no I/O, no LLM. Keeps the agent output and the gold set on the same
case-key scheme so the judge can compare them field-for-field.

Output object (six top-level keys; see null_prompt.APPROVED_LINES):
  required_state      : [ {field, state, body} ]   7 states per required field
  optional_state      : [ {field, state, body} ]   6 states per optional field
  all_required_null   : one body                   every required field = null
  each_required_null  : [ {field, body} ]          one required field = null each
  combo_required_null : [ {fields, body} ]         pairwise (<=5 req) OR half (>5 req)
  string_null         : [ {field, body} ]          string-typed required field = "null"
"""
from __future__ import annotations

from itertools import combinations

# Sentinel: a body that omits this field's key entirely (the "key absent" state).
ABSENT = object()

# The seven absent/empty states a REQUIRED field is exercised in, fixed order.
# Each is (state_name, value) where value ABSENT means "remove the key".
REQUIRED_STATES = [
    ("key_absent", ABSENT),
    ("json_null", None),
    ("empty_string", ""),
    ("integer_zero", 0),
    ("boolean_false", False),
    ("empty_array", []),
    ("empty_object", {}),
]

# The six states an OPTIONAL field is exercised in, fixed order (NO boolean_false,
# per the task's optional-field sub-test list a–f).
OPTIONAL_STATES = [
    ("key_absent", ABSENT),
    ("json_null", None),
    ("empty_string", ""),
    ("integer_zero", 0),
    ("empty_array", []),
    ("empty_object", {}),
]

STRING_NULL_VALUE = "null"  # the four-character string, NOT the JSON null token

# The pairwise-vs-half threshold (task steps 6 & 7): pairwise iff required count <= 5.
PAIRWISE_MAX_REQUIRED = 5

# Categories scored by the judge, in a stable order.
CATEGORIES = [
    "required_state",
    "optional_state",
    "all_required_null",
    "each_required_null",
    "combo_required_null",
    "string_null",
]


# --------------------------------------------------------------------------- #
# Body construction (immutable: always returns a fresh dict)
# --------------------------------------------------------------------------- #
def _with_field(example: dict, field: str, value) -> dict:
    body = dict(example)
    if value is ABSENT:
        body.pop(field, None)
    else:
        body[field] = value
    return body


def _with_fields_null(example: dict, fields: list[str]) -> dict:
    body = dict(example)
    for f in fields:
        body[f] = None
    return body


def optional_fields(props: dict, required: list[str]) -> list[str]:
    """Optional = documented fields not in the required list, in schema order."""
    return [k for k in props if k not in required]


def string_required_fields(props: dict, required: list[str]) -> list[str]:
    """Required fields whose declared type is string, in required-list order."""
    return [f for f in required if props.get(f, {}).get("type") == "string"]


# --------------------------------------------------------------------------- #
# Deterministic reference generator (used by the gold builder)
# --------------------------------------------------------------------------- #
def generate_cases(props: dict, required: list[str], example: dict) -> dict:
    """Produce the canonical six-key output deterministically from the schema.

    `required` is taken as spec order (the OpenAPI `required` array order); optional
    fields follow `props` insertion order.
    """
    req = list(required)
    opt = optional_fields(props, req)

    required_state = []
    for f in req:
        for state, val in REQUIRED_STATES:
            required_state.append({"field": f, "state": state, "body": _with_field(example, f, val)})

    optional_state = []
    for f in opt:
        for state, val in OPTIONAL_STATES:
            optional_state.append({"field": f, "state": state, "body": _with_field(example, f, val)})

    all_required_null = _with_fields_null(example, req)

    each_required_null = [{"field": f, "body": _with_fields_null(example, [f])} for f in req]

    combo_required_null = []
    if len(req) > PAIRWISE_MAX_REQUIRED:
        half = req[: len(req) // 2]
        if half:
            combo_required_null.append({"fields": list(half), "body": _with_fields_null(example, half)})
    else:
        for a, b in combinations(req, 2):
            combo_required_null.append({"fields": [a, b], "body": _with_fields_null(example, [a, b])})

    string_null = [{"field": f, "body": _with_field(example, f, STRING_NULL_VALUE)}
                   for f in string_required_fields(props, req)]

    return {
        "required_state": required_state,
        "optional_state": optional_state,
        "all_required_null": all_required_null,
        "each_required_null": each_required_null,
        "combo_required_null": combo_required_null,
        "string_null": string_null,
    }


# --------------------------------------------------------------------------- #
# Case iteration — flattens ANY output (agent or gold) into labeled cases.
# Each case is identified by (category, label); the harness/gold builder add the
# slug to make the full judge key (slug, category, label).
# --------------------------------------------------------------------------- #
def iter_cases(out: dict):
    """Yield (category, label, field, state, body) for one endpoint's output.
    Tolerant of missing/malformed keys (an agent may omit some)."""
    if not isinstance(out, dict):
        return

    for item in _as_list(out.get("required_state")):
        f = item.get("field", "?")
        st = item.get("state", "?")
        yield ("required_state", f"{f}:{st}", f, st, _body(item))

    for item in _as_list(out.get("optional_state")):
        f = item.get("field", "?")
        st = item.get("state", "?")
        yield ("optional_state", f"{f}:{st}", f, st, _body(item))

    # all_required_null is ONE body object (per the spec), emitted directly — never a
    # {"body": ...} wrapper. We must NOT unwrap a "body" key here: endpoints whose field
    # is literally named "body" (the comments routes) would otherwise have their
    # all_required_null body ({"body": null}) stripped to null and dropped.
    arn = out.get("all_required_null")
    if isinstance(arn, dict):
        yield ("all_required_null", "", None, None, arn)

    for item in _as_list(out.get("each_required_null")):
        f = item.get("field", "?")
        yield ("each_required_null", f, f, None, _body(item))

    for item in _as_list(out.get("combo_required_null")):
        fields = item.get("fields") if isinstance(item.get("fields"), list) else []
        label = "+".join(str(x) for x in fields)
        yield ("combo_required_null", label, None, None, _body(item))

    for item in _as_list(out.get("string_null")):
        f = item.get("field", "?")
        yield ("string_null", f, f, None, _body(item))


def _body(item):
    return item.get("body") if isinstance(item, dict) else None


def _as_list(v):
    return v if isinstance(v, list) else []


# --------------------------------------------------------------------------- #
# Idealized contract — the token a strict, spec-faithful validator would return.
# Gold records the API's REAL token; correctness = (real == ideal).
# This logic lives in the GOLD/JUDGE layer only — never in an agent prompt.
# --------------------------------------------------------------------------- #
def ideal_token(category: str, field: str | None, state: str | None, props: dict) -> str:
    # Any absent/empty state on a required field, and every null combination, must reject.
    if category in ("required_state", "all_required_null", "each_required_null", "combo_required_null"):
        return "400"
    # The four-character string "null" is a valid non-null string value.
    if category == "string_null":
        return "2xx"
    if category == "optional_state":
        if state == "key_absent":
            return "2xx"                       # omission of an optional field is valid
        if state == "json_null":
            return "400"                       # no field declares nullable:true ⇒ reject
        ftype = props.get(field, {}).get("type")
        if state == "empty_string":
            return "2xx" if ftype == "string" else "400"
        if state == "integer_zero":
            return "2xx" if ftype in ("integer", "number") else "400"
        if state == "empty_array":
            return "2xx" if ftype == "array" else "400"
        if state == "empty_object":
            return "2xx" if ftype == "object" else "400"
    return "?"


# Which categories count toward the Required-Field Invalid-State Rejection Rate
# (string_null is a VALID-state probe, so it is excluded).
REQUIRED_INVALID_CATEGORIES = (
    "required_state", "all_required_null", "each_required_null", "combo_required_null",
)
