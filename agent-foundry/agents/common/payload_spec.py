"""Canonical payload structure for the API request-body contract-testing task.

ONE definition of the labeled-array output, shared by:
  - the deterministic gold reference (data/build_gold.py) — generates payloads, and
  - the harness (agents/common/contract.py) — iterates whatever an agent emitted.

Pure: no env, no I/O, no LLM. Keeps the agent output and the gold set on exactly
the same case-key scheme so the judge can compare them field-for-field.

Output object (six top-level keys):
  valid                 : one body            (expected 2xx)
  inv_all_null          : one body            (expected 400)
  inv_missing_required  : [ {field, variant, body} ]            (expected 400 each)
  inv_wrong_type        : [ {field, wrong_type, value, body} ]  (expected 400 each)
  inv_extra_field       : [ {extra_type, extra_value, body} ]   (expected 400 each, exactly 9)
  inv_maxlength         : [ {field, max_length, value_length, body} ] | null  (expected 400 each)
"""
from __future__ import annotations

CATEGORIES = ["valid", "inv_missing_required", "inv_wrong_type",
              "inv_extra_field", "inv_all_null", "inv_maxlength"]

# The 9 wrong-type values, in fixed order, with their exact constant names.
WRONG_TYPE_VALUES = [
    ("INT_VAL", 42),
    ("FLOAT_VAL", 3.14),
    ("BOOL_TRUE", True),
    ("BOOL_FALSE", False),
    ("STRING_VAL", "wrong_type_string"),
    ("CHAR_VAL", "x"),
    ("LIST_VAL", [1, "a", True]),
    ("OBJECT_VAL", {"key": "value"}),
    ("NULL_NONE", None),
]

# Per schema type, the WRONG_TYPE constant names to skip (their JSON type matches).
EXCLUDE_BY_TYPE = {
    "string": {"STRING_VAL", "CHAR_VAL"},
    "integer": {"INT_VAL"},
    "number": {"FLOAT_VAL", "INT_VAL"},
    "boolean": {"BOOL_TRUE", "BOOL_FALSE"},
    "array": {"LIST_VAL"},
    "object": {"OBJECT_VAL"},
}


def maxlength_string_fields(props: dict) -> list[tuple[str, int]]:
    """All string fields carrying a maxLength constraint, in schema order."""
    return [(k, v["maxLength"]) for k, v in props.items()
            if v.get("type") == "string" and "maxLength" in v]


# --------------------------------------------------------------------------- #
# Deterministic reference generator (used by the gold builder)
# --------------------------------------------------------------------------- #
def generate_payloads(props: dict, required: list[str], example: dict) -> dict:
    """Produce the canonical six-key output deterministically from the schema."""
    valid = dict(example)

    missing = []
    for f in required:
        absent = dict(valid)
        absent.pop(f, None)
        missing.append({"field": f, "variant": "key_absent", "body": absent})
        present_null = dict(valid)
        present_null[f] = None
        missing.append({"field": f, "variant": "key_present_null", "body": present_null})

    wrong = []
    for f in required:
        ftype = props.get(f, {}).get("type", "any")
        skip = EXCLUDE_BY_TYPE.get(ftype, set())
        for name, val in WRONG_TYPE_VALUES:
            if name in skip:
                continue
            body = dict(valid)
            body[f] = val
            wrong.append({"field": f, "wrong_type": name, "value": val, "body": body})

    extra = []
    for name, val in WRONG_TYPE_VALUES:  # all 9, no exclusion
        body = dict(valid)
        body["extra_field"] = val
        extra.append({"extra_type": name, "extra_value": val, "body": body})

    all_null = {k: None for k in props}

    mls = maxlength_string_fields(props)
    if mls:
        maxlen = []
        for f, n in mls:
            body = dict(valid)
            body[f] = "a" * (n + 1)
            maxlen.append({"field": f, "max_length": n, "value_length": n + 1, "body": body})
    else:
        maxlen = None

    return {
        "valid": valid,
        "inv_missing_required": missing,
        "inv_wrong_type": wrong,
        "inv_extra_field": extra,
        "inv_all_null": all_null,
        "inv_maxlength": maxlen,
    }


# --------------------------------------------------------------------------- #
# Case iteration — flattens ANY output (agent or gold) into labeled cases.
# Each case is identified by (category, label); the harness/gold builder add
# the slug to make the full judge key (slug, category, label).
# --------------------------------------------------------------------------- #
def iter_cases(out: dict):
    """Yield (category, label, field, expected_class, body) for one endpoint's
    output. Tolerant of missing/malformed keys (an agent may omit some)."""
    if not isinstance(out, dict):
        return

    if "valid" in out and isinstance(out["valid"], dict):
        yield ("valid", "", None, "2xx", out["valid"])

    if "inv_all_null" in out and isinstance(out["inv_all_null"], dict):
        yield ("inv_all_null", "", None, "400", out["inv_all_null"])

    for item in _as_list(out.get("inv_missing_required")):
        f = item.get("field", "?")
        variant = item.get("variant", "?")
        yield ("inv_missing_required", f"{f}:{variant}", f, "400", item.get("body"))

    for item in _as_list(out.get("inv_wrong_type")):
        f = item.get("field", "?")
        wt = item.get("wrong_type", "?")
        yield ("inv_wrong_type", f"{f}:{wt}", f, "400", item.get("body"))

    for item in _as_list(out.get("inv_extra_field")):
        et = item.get("extra_type", "?")
        yield ("inv_extra_field", et, None, "400", item.get("body"))

    for item in _as_list(out.get("inv_maxlength")):
        f = item.get("field", "?")
        yield ("inv_maxlength", f, f, "400", item.get("body"))


def _as_list(v):
    return v if isinstance(v, list) else []
