"""Canonical structure for the API enum-value-restriction testing task.

ONE definition of the labeled test matrix + the per-case idealized contract,
shared by:
  - the deterministic gold reference (data/verify-enum-value-restrictions/build_gold.py), and
  - the harness (agents/common/enum_contract.py) — which iterates whatever an agent
    emitted and scores it on exactly the same (category, label) key scheme.

Pure: no env, no I/O, no LLM. Keeps the agent output and the gold set on the same
case-key scheme so the judge can compare them field-for-field.

Output object (six top-level keys; see enum_prompt.APPROVED_LINES). Every value is an
array of {field, value, body} payload objects:
  valid_values   : one per value V in each enum field's VALID_ENUMS (field = V)
  unknown_string : one per enum field (field = "INVALID_ENUM_THAT_DOES_NOT_EXIST")
  empty_string   : one per enum field (field = "")
  null_value     : one per enum field (field = JSON null token, key present)
  wrong_type     : one per enum field (field = integer 0)
  case_variant   : one per enum field whose VALID_ENUMS are all uppercase-only strings
                   (field = first VALID_ENUMS value lowercased)
"""
from __future__ import annotations

# Fixed sentinel/literal values for the four single-per-field invalid categories.
UNKNOWN_STRING_VALUE = "INVALID_ENUM_THAT_DOES_NOT_EXIST"
EMPTY_STRING_VALUE = ""
WRONG_TYPE_VALUE = 0  # the JSON integer zero, NOT the string "0"

# Categories scored by the judge, in a stable order.
CATEGORIES = [
    "valid_values",
    "unknown_string",
    "empty_string",
    "null_value",
    "wrong_type",
    "case_variant",
]

# The four categories that probe an INVALID value for EVERY enum field (used by the
# Invalid-Value Rejection Rate sub-metric). null_value is excluded because a nullable
# field legitimately accepts null, so it is graded per-field by ideal_token instead.
INVALID_VALUE_CATEGORIES = ("unknown_string", "empty_string", "wrong_type", "case_variant")


# --------------------------------------------------------------------------- #
# Enum-field discovery
# --------------------------------------------------------------------------- #
def enum_fields(props: dict) -> list[str]:
    """Documented fields that carry an `enum` array, in schema (insertion) order."""
    return [k for k, v in props.items()
            if isinstance(v, dict) and isinstance(v.get("enum"), list)]


def valid_enums(props: dict, field: str) -> list:
    """The ordered VALID_ENUMS list for one enum field."""
    return list(props.get(field, {}).get("enum", []))


def is_nullable(props: dict, field: str) -> bool:
    return bool(props.get(field, {}).get("nullable", False))


def is_uppercase_enum(values: list) -> bool:
    """True iff every value is a string that has at least one uppercase letter and no
    lowercase letter (so a lowercase variant is a genuine, distinct case-probe)."""
    if not values:
        return False
    for v in values:
        if not isinstance(v, str):
            return False
        if any(c.islower() for c in v):
            return False
        if not any(c.isupper() for c in v):
            return False
    return True


# --------------------------------------------------------------------------- #
# Body construction (immutable: always returns a fresh dict)
# --------------------------------------------------------------------------- #
def with_field(example: dict, field: str, value) -> dict:
    body = dict(example)
    body[field] = value
    return body


# --------------------------------------------------------------------------- #
# Deterministic reference generator (used by the gold builder AND the reference run)
# --------------------------------------------------------------------------- #
def generate_cases(props: dict, required: list[str], example: dict) -> dict:
    """Produce the canonical six-key output deterministically from the schema.

    `required` is accepted for signature parity with the other tasks; enum testing
    exercises every enum field regardless of required/optional (the harness records
    that distinction separately).
    """
    fields = enum_fields(props)

    valid = []
    for f in fields:
        for v in valid_enums(props, f):
            valid.append({"field": f, "value": v, "body": with_field(example, f, v)})

    unknown = [{"field": f, "value": UNKNOWN_STRING_VALUE,
                "body": with_field(example, f, UNKNOWN_STRING_VALUE)} for f in fields]
    empty = [{"field": f, "value": EMPTY_STRING_VALUE,
              "body": with_field(example, f, EMPTY_STRING_VALUE)} for f in fields]
    nulls = [{"field": f, "value": None, "body": with_field(example, f, None)} for f in fields]
    wrong = [{"field": f, "value": WRONG_TYPE_VALUE,
              "body": with_field(example, f, WRONG_TYPE_VALUE)} for f in fields]

    case_variant = []
    for f in fields:
        vals = valid_enums(props, f)
        if is_uppercase_enum(vals):
            lowered = vals[0].lower()
            case_variant.append({"field": f, "value": lowered,
                                 "body": with_field(example, f, lowered)})

    return {
        "valid_values": valid,
        "unknown_string": unknown,
        "empty_string": empty,
        "null_value": nulls,
        "wrong_type": wrong,
        "case_variant": case_variant,
    }


# --------------------------------------------------------------------------- #
# Case iteration — flattens ANY output (agent or gold) into labeled cases.
# Each case is identified by (category, label); the harness/gold builder add the
# slug to make the full judge key (slug, category, label).
# --------------------------------------------------------------------------- #
def iter_cases(out: dict):
    """Yield (category, label, field, value, body) for one endpoint's output.
    Tolerant of missing/malformed keys (an agent may omit some)."""
    if not isinstance(out, dict):
        return

    for item in _as_list(out.get("valid_values")):
        f = item.get("field", "?")
        v = item.get("value")
        yield ("valid_values", f"{f}:{_vlabel(v)}", f, v, _body(item))

    for category in ("unknown_string", "empty_string", "null_value", "wrong_type", "case_variant"):
        for item in _as_list(out.get(category)):
            f = item.get("field", "?")
            yield (category, f"{f}", f, item.get("value"), _body(item))


def _vlabel(v) -> str:
    """A stable label fragment for a sent enum value."""
    return v if isinstance(v, str) else str(v)


def _body(item):
    return item.get("body") if isinstance(item, dict) else None


def _as_list(v):
    return v if isinstance(v, list) else []


# --------------------------------------------------------------------------- #
# Idealized contract — the token a strict, spec-faithful validator would return.
# Gold records the API's REAL token; correctness = (real == ideal).
# This logic lives in the GOLD/JUDGE layer only — never in an agent prompt.
# --------------------------------------------------------------------------- #
def ideal_token(category: str, field: str | None, props: dict) -> str:
    if category == "valid_values":
        return "2xx"                       # a documented enum value must be accepted
    if category == "null_value":
        # A null is accepted only when the field is explicitly nullable: true.
        return "2xx" if (field is not None and is_nullable(props, field)) else "400"
    if category in ("unknown_string", "empty_string", "wrong_type", "case_variant"):
        return "400"                       # every off-enum value must be rejected
    return "?"
