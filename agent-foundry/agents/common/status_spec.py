"""Canonical request-construction recipe for the response status-code task.

ONE definition of the per-(operation, documented-code) request descriptor, shared by:
  - the deterministic gold reference (data/status/build_gold.py), and
  - the harness (agents/common/status_contract.py), which iterates whatever an
    agent emitted.

Pure: no env, no I/O, no LLM. Keeps the agent output and the gold set on exactly
the same case-key scheme — (slug, documented_code) — so the judge can compare them
field-for-field.

A request descriptor is:
    {"code": <int documented code>,
     "method": "GET" | "POST" | "PUT" | "PATCH",
     "path": "<path with {id} already substituted>",
     "auth": "none" | "valid" | "malformed",
     "body": <json object> | null}

`reference_request` is the GOLD recipe. Agents must REPRODUCE it by reasoning over
the operation brief — they do not import this module.
"""
from __future__ import annotations

EXISTING_ID = "1"
NONEXISTENT_ID = "999999"
AUTH_MODES = ("none", "valid", "malformed")
BODY_METHODS = ("POST", "PUT", "PATCH")


def _sub(path: str, ident: str) -> str:
    return path.replace("{id}", ident)


def reference_request(op: dict, code: int) -> dict:
    """Deterministic canonical request descriptor for one documented code on one
    operation. This is the reference recipe the gold builder applies and that the
    agents must reproduce.

    `op` keys: method, path, auth_required (bool), required (list[str]),
    example (dict | None), is_hook (bool).
    """
    method = op["method"]
    path = op["path"]
    auth_required = bool(op.get("auth_required", False))
    required = op.get("required", []) or []
    example = op.get("example")
    body_taking = method in BODY_METHODS

    # Status-hook operation (/http/<n>): documented code == path number; send as-is.
    if op.get("is_hook"):
        return {"code": code, "method": method, "path": path, "auth": "none", "body": None}

    valid_auth = "valid" if auth_required else "none"
    body_valid = dict(example) if (body_taking and isinstance(example, dict)) else None

    if code in (200, 201):
        return {"code": code, "method": method, "path": _sub(path, EXISTING_ID),
                "auth": valid_auth, "body": body_valid}
    if code == 400:
        body = dict(example) if isinstance(example, dict) else {}
        if required:
            body.pop(required[0], None)
        return {"code": code, "method": method, "path": _sub(path, EXISTING_ID),
                "auth": valid_auth, "body": body if body_taking else None}
    if code == 401:
        return {"code": code, "method": method, "path": _sub(path, EXISTING_ID),
                "auth": "none", "body": body_valid}
    if code == 404:
        return {"code": code, "method": method, "path": _sub(path, NONEXISTENT_ID),
                "auth": valid_auth, "body": body_valid}
    if code == 500:
        return {"code": code, "method": method, "path": _sub(path, EXISTING_ID),
                "auth": "malformed", "body": body_valid}
    # Codes the resource recipe doesn't explicitly target (403/409/422/429 on a
    # non-hook op): send the operation as documented and let the API reveal its code.
    return {"code": code, "method": method, "path": _sub(path, EXISTING_ID),
            "auth": "none", "body": body_valid}


def _toint(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def iter_agent_requests(out) -> list[dict]:
    """Tolerantly flatten an agent's output into a list of descriptors.

    Accepts {"requests": [ ... ]}, a bare list, or a dict keyed by code-string
    ({"200": {...}, "404": {...}}). Only well-formed descriptors carrying an
    integer 'code' survive.
    """
    if isinstance(out, dict) and isinstance(out.get("requests"), list):
        items = out["requests"]
    elif isinstance(out, list):
        items = out
    elif isinstance(out, dict):
        items = []
        for k, v in out.items():
            if isinstance(v, dict):
                d = dict(v)
                d.setdefault("code", _toint(k))
                items.append(d)
    else:
        return []

    norm = []
    for it in items:
        if not isinstance(it, dict):
            continue
        code = it.get("code")
        if not isinstance(code, int):
            code = _toint(code)
        if code is None:
            continue
        norm.append({"code": code,
                     "method": it.get("method"),
                     "path": it.get("path"),
                     "auth": it.get("auth", "none"),
                     "body": it.get("body")})
    return norm
