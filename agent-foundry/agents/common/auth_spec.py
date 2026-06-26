"""Shared, deterministic substrate for the four authentication-flow agents.

This module carries NO debate-gated agent instruction. It is the identical
plumbing the gold builder AND every framework harness sit on, so that
leaderboard differences are attributable to the framework + its gated prompt +
its evolved skill — never to divergent credential construction.

It defines, once:
  - the canonical auth scenario matrix (the structure agents emit AND the gold)
  - deterministic credential CONSTRUCTORS for each recipe kind (login, mint an
    expired HS256 token, truncate a token, logout-then-reuse a token)
  - a tolerant iterator over an agent's (or the gold's) plan
  - status-code classification

Faithful to the live DummyJSON target (per the Phase 2 decisions):
  - DummyJSON documents exactly ONE auth scheme: Bearer JWT (HS256, JWT_SECRET).
  - The other schemes the generic task names (API key, HTTP Basic, OAuth2), the
    api-key-wrong-location sub-test, and a dedicated /auth/revoke endpoint are
    NOT implemented here. They are enumerated as `not_applicable` with status
    "needs_to_be_built_and_tested" — never fabricated, never executed.

JWT minting uses stdlib HMAC-SHA256 only (no PyJWT dependency) so the whole
substrate stays stdlib-only and air-gapped, matching data/build_gold*.py.
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import json
import os
import urllib.error
import urllib.request

# --------------------------------------------------------------------------- #
# The one documented scheme + the protected endpoint under test
# --------------------------------------------------------------------------- #
# The protected endpoint defaults to /auth/me but is overridable via
# FORGE_PROTECTED_PATH so the evolution gate can validate on a DISJOINT held-out
# endpoint (e.g. /user/me, guarded by the same authUser middleware).
PROTECTED_ENDPOINT = {"method": "GET",
                      "path": os.environ.get("FORGE_PROTECTED_PATH", "/auth/me")}
LOGIN_ENDPOINT = {"method": "POST", "path": "/auth/login"}
REVOKE_EQUIVALENT = {"method": "POST", "path": "/auth/logout"}  # no /auth/revoke exists
VALID_CREDS = {"username": "emilys", "password": "emilyspass"}

SCHEME = {
    "name": "bearerJWT",
    "type": "http",
    "scheme": "bearer",
    "bearerFormat": "JWT",
    "in": "header",
    "header_name": "Authorization",
    "prefix": "Bearer ",
    "implemented": True,
}

# Each sub-test: (label, recipe, task_rule_expected_class).
# task_rule_expected_class is the code a CORRECT API should return (200 for valid,
# 401 for every invalid credential) — used for the Auth Flow Pass Rate / False
# Acceptance / False Rejection findings. It is NOT the gold (the gold records the
# live API's ACTUAL behavior, per the Phase 2 decision).
SUBTESTS = [
    ("valid", {"kind": "valid_token"}, "2xx"),
    ("missing", {"kind": "no_auth"}, "401"),
    ("malformed", {"kind": "truncate_token", "drop_chars": 8}, "401"),
    ("expired", {"kind": "expired_token", "exp_delta_sec": -3600}, "401"),
    ("revoked", {"kind": "revoked_token", "revoke_via": "POST /auth/logout"}, "401"),
]

# Documented-by-the-generic-task but NOT implemented by DummyJSON. Enumerated,
# marked, never fabricated or executed (Phase 2 decision #1).
NOT_APPLICABLE = [
    {"item": "apiKey", "kind": "scheme",
     "reason": "no API-key security scheme is documented in DummyJSON",
     "status": "needs_to_be_built_and_tested"},
    {"item": "basic", "kind": "scheme",
     "reason": "no HTTP Basic security scheme is documented in DummyJSON",
     "status": "needs_to_be_built_and_tested"},
    {"item": "oauth2", "kind": "scheme",
     "reason": "no OAuth2 security scheme is documented in DummyJSON",
     "status": "needs_to_be_built_and_tested"},
    {"item": "apikey_wrong_location", "kind": "subtest",
     "reason": "the wrong-location sub-test applies only to an API-key scheme, "
               "which DummyJSON does not document",
     "status": "needs_to_be_built_and_tested"},
    {"item": "dedicated_revoke_endpoint", "kind": "endpoint",
     "reason": "DummyJSON exposes no POST /auth/revoke; the revoked sub-test uses "
               "POST /auth/logout as the documented equivalent",
     "status": "needs_to_be_built_and_tested"},
]


def canonical_plan() -> dict:
    """The reference auth test plan: what the gold builder executes and what a
    perfect agent would emit. One documented scheme, five sub-tests, the
    enumerated not-applicable items."""
    return {
        "protected_endpoint": dict(PROTECTED_ENDPOINT),
        "schemes": [{
            "scheme": SCHEME["name"],
            "type": SCHEME["type"],
            "in": SCHEME["in"],
            "header_name": SCHEME["header_name"],
            "prefix": SCHEME["prefix"],
            "implemented": True,
            "subtests": [
                {"label": label, "credential": dict(recipe), "expected_class": exp}
                for label, recipe, exp in SUBTESTS
            ],
        }],
        "not_applicable": [dict(x) for x in NOT_APPLICABLE],
    }


def SUBTESTS_ITER():
    """Yield (scheme_name, label, recipe, task_expected_class) over the canonical
    matrix — used by the gold builder."""
    for label, recipe, exp in SUBTESTS:
        yield SCHEME["name"], label, recipe, exp


# --------------------------------------------------------------------------- #
# Sandbox host guard — only the local target is ever reachable
# --------------------------------------------------------------------------- #
def _assert_local(url: str) -> None:
    from urllib.parse import urlparse
    host = urlparse(url).hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise PermissionError(f"refusing non-local HTTP target: {host}")


# --------------------------------------------------------------------------- #
# Status classification
# --------------------------------------------------------------------------- #
def classify(code: int | None) -> str:
    if code is None:
        return "none"
    if 200 <= code < 300:
        return "2xx"
    if code == 401:
        return "401"
    if 400 <= code < 500:
        return f"4xx_{code}"
    return f"other_{code}"


# --------------------------------------------------------------------------- #
# Minimal stdlib JWT (HS256) — mint only; we never need to verify
# --------------------------------------------------------------------------- #
def _b64url(raw: bytes) -> str:
    return base64.urlsafe_b64encode(raw).rstrip(b"=").decode()


def _b64url_decode(seg: str) -> bytes:
    pad = "=" * (-len(seg) % 4)
    return base64.urlsafe_b64decode(seg + pad)


def decode_jwt_payload(token: str) -> dict:
    """Decode (NOT verify) the payload segment of a JWT."""
    try:
        return json.loads(_b64url_decode(token.split(".")[1]))
    except Exception:  # noqa
        return {}


def mint_hs256(payload: dict, secret: str, exp_unix: int) -> str:
    """Mint a valid-signature HS256 token with a chosen exp. Signing with the
    REAL secret matters: jsonwebtoken verifies the signature BEFORE the expiry,
    so a correctly-signed-but-expired token yields 'jwt expired' (the path we
    want) rather than 'invalid signature'."""
    body = {k: v for k, v in payload.items() if k not in ("iat", "exp")}
    body["iat"] = max(0, exp_unix - 60)
    body["exp"] = exp_unix
    header = {"alg": "HS256", "typ": "JWT"}
    signing_input = _b64url(json.dumps(header, separators=(",", ":")).encode()) + "." + \
        _b64url(json.dumps(body, separators=(",", ":")).encode())
    sig = hmac.new(secret.encode(), signing_input.encode(), hashlib.sha256).digest()
    return signing_input + "." + _b64url(sig)


# --------------------------------------------------------------------------- #
# HTTP helpers (LOCAL target only — the caller enforces the host guard)
# --------------------------------------------------------------------------- #
def _request(base_url: str, method: str, path: str, *, headers=None, body=None):
    url = base_url.rstrip("/") + path
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    req = urllib.request.Request(url, data=data, method=method, headers=hdrs)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.getcode(), r.read().decode("utf-8", "replace")
    except urllib.error.HTTPError as e:
        return e.code, e.read().decode("utf-8", "replace")
    except Exception:  # noqa
        return -1, ""


def login_token(base_url: str) -> str | None:
    code, text = _request(base_url, "POST", LOGIN_ENDPOINT["path"], body=VALID_CREDS)
    if code != 200:
        return None
    try:
        return json.loads(text).get("accessToken")
    except Exception:  # noqa
        return None


# --------------------------------------------------------------------------- #
# Credential constructors — recipe -> the Authorization header(s) to send.
# Returns (headers_dict, note). headers_dict is None => "send no auth header".
# The agents never run this; the harness and the gold builder do.
# --------------------------------------------------------------------------- #
def build_credential(recipe: dict, base_url: str, secret: str) -> tuple[dict | None, str]:
    kind = (recipe or {}).get("kind")
    prefix = SCHEME["prefix"]
    hdr = SCHEME["header_name"]

    if kind == "no_auth":
        return None, "no Authorization header, no cookie"

    if kind == "valid_token":
        tok = login_token(base_url)
        if not tok:
            return None, "login failed (could not obtain valid token)"
        return {hdr: prefix + tok}, "valid token from /auth/login"

    if kind == "truncate_token":
        drop = int(recipe.get("drop_chars", 8))
        tok = login_token(base_url)
        if not tok:
            return None, "login failed"
        return {hdr: prefix + tok[:-drop]}, f"valid token minus last {drop} chars"

    if kind == "expired_token":
        delta = int(recipe.get("exp_delta_sec", -3600))
        tok = login_token(base_url)
        if not tok:
            return None, "login failed"
        payload = decode_jwt_payload(tok)
        now = _server_now(base_url)
        expired = mint_hs256(payload, secret, now + delta)
        return {hdr: prefix + expired}, f"re-signed real payload, exp = now {delta:+d}s"

    if kind == "revoked_token":
        tok = login_token(base_url)
        if not tok:
            return None, "login failed"
        # Revoke via the documented equivalent (logout), then REUSE the same token.
        _request(base_url, REVOKE_EQUIVALENT["method"], REVOKE_EQUIVALENT["path"],
                 headers={hdr: prefix + tok})
        return {hdr: prefix + tok}, "same token reused after POST /auth/logout"

    return None, f"unknown recipe kind: {kind!r}"


def _server_now(base_url: str) -> int:
    """Use wall-clock for exp deltas. The server and this process share the host
    clock (air-gapped, same machine), so local time is the server's time."""
    import time
    return int(time.time())


# --------------------------------------------------------------------------- #
# Tolerant iteration over a plan (agent's OR canonical)
# --------------------------------------------------------------------------- #
def iter_subtests(plan: dict):
    """Yield (scheme_name, label, recipe, expected_class) for each executable
    sub-test in a plan. Tolerant of a partial / malformed agent plan."""
    for scheme in (plan or {}).get("schemes", []) or []:
        sname = scheme.get("scheme") or scheme.get("name") or "unknown"
        if scheme.get("implemented") is False:
            continue
        for st in scheme.get("subtests", []) or []:
            label = st.get("label")
            if not label:
                continue
            recipe = st.get("credential") or st.get("recipe") or {}
            expected = st.get("expected_class") or _default_expected(label)
            yield sname, label, recipe, expected


def iter_not_applicable(plan: dict):
    """Yield each not-applicable item id the agent enumerated."""
    for x in (plan or {}).get("not_applicable", []) or []:
        item = x.get("item") or x.get("scheme") or x.get("subtest")
        if item:
            yield str(item), x.get("status")


def _default_expected(label: str) -> str:
    return "2xx" if label == "valid" else "401"
