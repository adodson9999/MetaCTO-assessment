"""Canonical request-construction + response-schema-lookup recipe for the
validate-json-schema-responses task.

ONE definition shared by:
  - the deterministic gold reference (data/schema/build_gold.py builds its own
    valid bodies from the catalogue; this module's reference_request mirrors the
    same construction rules), and
  - the harness (agents/common/schema_contract.py), which iterates whatever an
    agent emitted.

Pure: no env, no I/O, no LLM. Keeps agent output and gold on the same case-key
scheme — keyed by endpoint slug — so the judge can compare field-for-field.

An agent's per-endpoint output is:
    {"request": {"method","path","auth","body"},
     "documented_response_schemas": [{"code": <str key, e.g. "2xx">,
                                      "has_json_schema": <bool>}, ...]}

Response "codes" are the documented response KEYS exactly as written in the spec
(e.g. "2xx", "400"), not necessarily integers — DummyJSON's authored spec uses
range keys. They are kept as strings throughout.
"""
from __future__ import annotations

EXISTING_ID = "1"
AUTH_MODES = ("none", "valid")
BODY_METHODS = ("POST", "PUT", "PATCH")


def _sub(path: str, ident: str) -> str:
    return path.replace("{id}", ident)


def reference_request(op: dict) -> dict:
    """Deterministic canonical VALID request descriptor for one endpoint — the
    reference the agents must reproduce by reasoning over the endpoint brief.

    `op` keys: method, path, auth_required (bool), example (dict | None).
    """
    method = op["method"]
    body_taking = method in BODY_METHODS
    example = op.get("example")
    return {
        "method": method,
        "path": _sub(op["path"], EXISTING_ID),
        "auth": "valid" if op.get("auth_required") else "none",
        "body": dict(example) if (body_taking and isinstance(example, dict)) else None,
    }


def reference_schema_map(op: dict) -> list[dict]:
    """The documented response-schema map for one endpoint: one entry per
    documented response key, each with whether a JSON response schema is
    documented (keys kept as strings, e.g. "2xx", "400")."""
    return [{"code": c, "has_json_schema": bool(op.get("schema_by_code", {}).get(c, False))}
            for c in op.get("codes", [])]


def normalize_request(out) -> dict:
    """Pull a well-formed request descriptor out of an agent's output.

    Accepts {"request": {...}, ...} or a bare descriptor dict. Returns a dict with
    method/path/auth/body keys (missing keys -> None / defaults)."""
    req = out.get("request") if isinstance(out, dict) else None
    if not isinstance(req, dict):
        # tolerate an agent that returned the descriptor at top level
        if isinstance(out, dict) and {"method", "path"} <= set(out):
            req = out
        else:
            req = {}
    return {
        "method": req.get("method"),
        "path": req.get("path"),
        "auth": req.get("auth", "none"),
        "body": req.get("body"),
    }


def normalize_schema_map(out) -> list[dict]:
    """Pull the documented_response_schemas array out of an agent's output.

    Accepts {"documented_response_schemas": [...]}; tolerates a dict keyed by
    code-string ({"200": true, "404": false}). Only entries with an integer code
    survive."""
    raw = out.get("documented_response_schemas") if isinstance(out, dict) else None
    items = []
    if isinstance(raw, list):
        items = raw
    elif isinstance(raw, dict):
        for k, v in raw.items():
            items.append({"code": k, "has_json_schema": bool(v)})
    norm = []
    for it in items:
        if not isinstance(it, dict):
            continue
        code = it.get("code")
        if code is None:
            continue
        norm.append({"code": str(code),
                     "has_json_schema": bool(it.get("has_json_schema", False))})
    return norm
