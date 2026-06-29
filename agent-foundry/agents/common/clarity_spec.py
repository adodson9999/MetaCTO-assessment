"""Canonical recipe + clarity assertions for the Verify-Error-Message-Clarity task.

ONE definition of:
  - the per-(operation, documented-error-code) request descriptor that TRIGGERS
    that error, derived from a small fixed set of named triggers, and
  - the deterministic clarity assertions run on the error response BODY.

Shared by:
  - the deterministic gold reference (data/clarity/build_gold.py), and
  - the harness (agents/common/clarity_contract.py), which iterates whatever an
    agent emitted and runs the identical assertions.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on exactly the
same case-key scheme — (slug, documented_code) — so the judge compares them
field-for-field.

A request descriptor is:
    {"code": <int documented error code>,
     "method": "GET" | "POST" | "PUT" | "PATCH",
     "path": "<path with {id} / query already substituted>",
     "auth": "none" | "valid" | "malformed",
     "body": <json object> | null}

The TRIGGER names (one per documented case) and their compilation:
    passthrough    : hook op — method/path copied unchanged, auth "none", body null
    no_auth        : {id}->"1", auth "none", body null
    malformed_auth : {id}->"1", auth "malformed", body null
    bad_path_id    : {id}->"nonexistent-id-000000", auth valid-if-required else none, body null
    bad_query      : path + the op's documented bad-query suffix, auth valid-if-required else none, body null
    missing_field  : {id}->"1", auth valid-if-required else none,
                     body = valid example with the FIRST required field removed

`reference_request` is the GOLD recipe. Agents must REPRODUCE it by reasoning over
the operation brief (which names the trigger per documented code) — they do not
import this module.
"""
from __future__ import annotations

import json
import re

EXISTING_ID = "1"
NONEXISTENT_ID = "nonexistent-id-000000"
BODY_METHODS = ("POST", "PUT", "PATCH")
MIN_MESSAGE_CHARS = 5

# Triggers that compile to a request needing no auth header at all.
TRIGGERS = ("passthrough", "no_auth", "malformed_auth",
            "bad_path_id", "bad_query", "missing_field")


def _sub(path: str, ident: str) -> str:
    return path.replace("{id}", ident)


def _valid_auth(op: dict) -> str:
    return "valid" if bool(op.get("auth_required")) else "none"


def reference_request(op: dict, code: int) -> dict:
    """Deterministic canonical request descriptor that triggers `code` on `op`.

    `op` keys: method, path, auth_required (bool), required (list[str]),
    example (dict | None), is_hook (bool), bad_query (str | None),
    triggers (dict[int|str, str]) mapping each documented code to its trigger name.
    This is the reference the gold builder applies and the agents must reproduce.
    """
    method = op["method"]
    path = op["path"]
    trigger = op["triggers"][code] if code in op["triggers"] else op["triggers"][str(code)]

    if trigger == "passthrough":
        return {"code": code, "method": method, "path": path,
                "auth": "none", "body": None}
    if trigger == "no_auth":
        return {"code": code, "method": method, "path": _sub(path, EXISTING_ID),
                "auth": "none", "body": None}
    if trigger == "malformed_auth":
        return {"code": code, "method": method, "path": _sub(path, EXISTING_ID),
                "auth": "malformed", "body": None}
    if trigger == "bad_path_id":
        return {"code": code, "method": method, "path": _sub(path, NONEXISTENT_ID),
                "auth": _valid_auth(op), "body": None}
    if trigger == "bad_query":
        suffix = op.get("bad_query") or ""
        return {"code": code, "method": method, "path": _sub(path, EXISTING_ID) + suffix,
                "auth": _valid_auth(op), "body": None}
    if trigger == "missing_field":
        example = op.get("example")
        body = dict(example) if isinstance(example, dict) else {}
        required = op.get("required") or []
        if required:
            body.pop(required[0], None)
        body_takes = method in BODY_METHODS
        return {"code": code, "method": method, "path": _sub(path, EXISTING_ID),
                "auth": _valid_auth(op), "body": body if body_takes else None}
    raise ValueError(f"unknown trigger {trigger!r} for code {code} on {op.get('slug')}")


# --------------------------------------------------------------------------- #
# Tolerant flattening of an agent's emitted output into descriptors
# --------------------------------------------------------------------------- #
def _toint(v):
    try:
        return int(v)
    except (TypeError, ValueError):
        return None


def iter_agent_requests(out) -> list[dict]:
    """Flatten an agent's output into a list of descriptors.

    Accepts {"requests": [ ... ]}, a bare list, or a dict keyed by code-string
    ({"404": {...}}). Only well-formed descriptors carrying an integer 'code'
    survive.
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


# --------------------------------------------------------------------------- #
# Clarity assertions — deterministic, identical for gold and every agent.
# These live in code (not in any agent prompt): the task itself prescribes a
# Python re scan, and the checks MUST be identical across all four agents, so
# they belong in the shared substrate, never in framework-specific reasoning.
# --------------------------------------------------------------------------- #

# Pattern 1 — exception classes / stack-trace / Java markers. Dots that act as
# package/file separators are escaped to their literal meaning (the task's intent:
# detect "at com.<pkg>" / "<file>.java:<line>"), the alternation tokens otherwise
# match verbatim.
_P1 = re.compile(r"(Exception|stack trace|SQLException|NullPointerException"
                 r"|at com\.|at org\.|\.java:\d+)")
# Pattern 2 — a slash-initiated token that contains a file extension, e.g.
# "/app/src/handler.py". A "/" followed by path characters, then a dot and a
# 1-8 char alphanumeric extension at a token boundary.
_P2 = re.compile(r"/[^\s\"'<>]*\.[A-Za-z0-9]{1,8}(?![A-Za-z0-9])")
# Pattern 3 — internal double-underscore identifier names.
_P3 = re.compile(r"[A-Za-z_][A-Za-z0-9_]*__[A-Za-z0-9_]+")


def internal_detail_matches(serialized_body: str) -> list[str]:
    """Every internal-detail substring found in the serialized body, across all
    three patterns. Empty list == clean."""
    matches: list[str] = []
    for pat in (_P1, _P2, _P3):
        for m in pat.finditer(serialized_body or ""):
            matches.append(m.group(0))
    return matches


def message_present(obj) -> bool:
    """Top-level "message" is a string of >= MIN_MESSAGE_CHARS non-space chars."""
    if not isinstance(obj, dict):
        return False
    v = obj.get("message")
    return isinstance(v, str) and len(v.strip()) >= MIN_MESSAGE_CHARS


def code_present(obj) -> bool:
    """Top-level "code" OR "error_code" is a non-empty string or a non-zero int."""
    if not isinstance(obj, dict):
        return False
    for key in ("code", "error_code"):
        if key not in obj:
            continue
        v = obj[key]
        if isinstance(v, bool):  # bool is an int subclass — never a valid code
            continue
        if isinstance(v, str) and v.strip():
            return True
        if isinstance(v, int) and v != 0:
            return True
    return False


def clarity_verdict(raw_text: str) -> dict:
    """Run the three documented assertions on one error response body.

    A response PASSES only when it is valid JSON, has a usable "message", has a
    usable "code"/"error_code", AND leaks zero internal details.
    """
    obj = None
    valid_json = False
    try:
        obj = json.loads(raw_text) if raw_text is not None else None
        valid_json = isinstance(obj, (dict, list))
    except Exception:  # noqa
        valid_json = False

    # Serialize the WHOLE body to a single string for the leak scan. Prefer the
    # parsed-then-re-serialized form when valid; otherwise scan the raw text.
    if valid_json:
        serialized = json.dumps(obj, ensure_ascii=False)
    else:
        serialized = raw_text or ""

    msg_ok = message_present(obj)
    code_ok = code_present(obj)
    leaks = internal_detail_matches(serialized)
    passed = bool(valid_json and msg_ok and code_ok and not leaks)
    return {
        "valid_json": valid_json,
        "message_present": msg_ok,
        "code_present": code_ok,
        "sensitive_found": bool(leaks),
        "sensitive_matches": leaks,
        "passed": passed,
    }
