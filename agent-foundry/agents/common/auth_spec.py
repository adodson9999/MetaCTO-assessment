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

Security posture: every credential recipe dials an untrusted ``base_url``. The
harness runs against a LOCAL sandbox only, so `_request()` enforces a
loopback/private-only host guard (`_assert_local`) before any socket is opened —
an injected ``base_url`` (e.g. http://169.254.169.254 cloud metadata, or a
public host) is refused, not fetched. All fallbacks are logged, never silent,
so a future reader can see exactly which degradation path fired.
"""
from __future__ import annotations

import base64
import binascii
import hashlib
import hmac
import ipaddress
import json
import logging
import os
import time
import urllib.error
import urllib.request
from typing import Iterator, Optional
from urllib.parse import urlparse

# Module logger with a NullHandler: the library never configures the root
# logger (that is the application's job), but every failure/fallback below emits
# a record so an operator who opts in to logging sees the auth-flow internals.
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

# --------------------------------------------------------------------------- #
# Bounded-read + retry constants (named, not magic — see reviewers network /
# adversarial-input / memory-resource).
# --------------------------------------------------------------------------- #
MAX_RESPONSE_BYTES = 4 * 1024 * 1024  # cap body reads so a huge/streaming body
#                                       cannot exhaust memory.
REQUEST_TIMEOUT_S = 20                 # per-attempt socket timeout.
MAX_ATTEMPTS = 3                       # total tries on a transient failure.
BACKOFF_BASE_S = 0.25                  # first backoff; doubles each retry.
TRANSIENT_STATUS = -1                  # sentinel returned on a network failure.
EXPIRY_SKEW_MARGIN_SEC = 86_400       # 24h. An "expired" recipe is clamped AT
#                                       LEAST this far into the past, so any
#                                       realistic backward wall-clock correction
#                                       (NTP step, DST bug, VM resume) cannot
#                                       revive the token: even a full-day reverse
#                                       jump leaves exp <= the (earlier) server
#                                       clock. A jump larger than a day is a
#                                       catastrophic host-clock failure outside
#                                       this sandbox's threat model.
MAX_INT_FIELD_CHARS = 18              # a numeric recipe field (drop_chars,
#                                       exp_delta_sec) may be at most this many
#                                       chars before parsing. 18 digits covers
#                                       any legitimate value (< 10^18) while
#                                       rejecting a million-digit string bomb
#                                       BEFORE int() runs (int() on huge digit
#                                       strings is super-linear / DoS-prone).

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
    enumerated not-applicable items.

    Every nested container is a fresh copy so a caller mutating the returned
    plan can never corrupt the module-level constants (immutability at the
    boundary)."""
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


def SUBTESTS_ITER() -> Iterator[tuple[str, str, dict, str]]:
    """Yield (scheme_name, label, recipe, task_expected_class) over the canonical
    matrix — used by the gold builder. Recipes are copied so consumers cannot
    mutate the shared SUBTESTS constant."""
    for label, recipe, exp in SUBTESTS:
        yield SCHEME["name"], label, dict(recipe), exp


# --------------------------------------------------------------------------- #
# Sandbox host guard — only the local target is ever reachable (SSRF containment)
# --------------------------------------------------------------------------- #
def _assert_local(url: str) -> None:
    """Refuse any HTTP target that is not loopback or RFC-1918/private.

    Rationale (security / vulnerability reviewers): the harness dials an
    untrusted ``base_url``. Without this guard an injected value could reach
    cloud metadata (169.254.169.254, link-local), other hosts on the LAN, or the
    public internet — classic SSRF. We allow loopback + private ranges (the
    sandbox may run the target on a private-network IP) and reject everything
    else, INCLUDING link-local (169.254/16, fe80::/10). Called on every request
    before a socket is opened. Fail closed on a missing/garbage host."""
    host = (urlparse(url).hostname or "").strip()
    if not host:
        logger.warning("_assert_local: refusing HTTP target with no host (url=%r)", url)
        raise PermissionError("refusing HTTP target with no host")
    if host in ("localhost", "127.0.0.1", "::1"):
        return
    try:
        ip = ipaddress.ip_address(host)
    except ValueError:
        # A non-IP hostname that is not 'localhost' — refuse rather than resolve
        # (DNS resolution to a private range is a known SSRF bypass). Log the
        # attempt so an operator has an audit trail of SSRF probing.
        logger.warning("_assert_local: refusing non-local host %r (SSRF guard)", host)
        raise PermissionError(f"refusing non-local HTTP target: {host}")
    if ip.is_loopback or (ip.is_private and not ip.is_link_local):
        return
    logger.warning("_assert_local: refusing non-local host %r (SSRF guard)", host)
    raise PermissionError(f"refusing non-local HTTP target: {host}")


# --------------------------------------------------------------------------- #
# Status classification
# --------------------------------------------------------------------------- #
def classify(code: Optional[int]) -> str:
    """Bucket an HTTP status into a coarse class used by every finding."""
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
    """Decode a base64url segment, tolerating missing padding.

    We translate base64url (-_) to standard base64 (+/) and decode with
    ``validate=True`` so ``base64`` rejects ANY character outside the alphabet by
    raising ``binascii.Error`` deterministically — rather than silently
    discarding stray bytes. A caller's narrow ``except binascii.Error`` is thus
    guaranteed to fire on garbage like ``'!!!invalid!!!'`` (``urlsafe_b64decode``
    has no ``validate`` kwarg, hence the explicit translate + ``b64decode``)."""
    standard = seg.replace("-", "+").replace("_", "/")
    pad = "=" * (-len(standard) % 4)
    return base64.b64decode(standard + pad, validate=True)


def decode_jwt_payload(token: str) -> dict:
    """Decode (NOT verify) the payload segment of a JWT.

    Returns {} on ANY malformed input (missing segment, bad base64, non-JSON,
    non-str token). This is DELIBERATE graceful degradation: a malformed token
    is an expected test input (the 'truncate_token' recipe produces one), not a
    programmer error — so the expired-token path can still re-sign whatever
    payload it recovers. The specific failures are logged at debug level (no
    silent except) and the caught types are narrowed to the parse/decode errors
    we actually expect."""
    if not isinstance(token, str):
        logger.debug("decode_jwt_payload: non-str token type %s; returning empty", type(token).__name__)
        return {}
    try:
        return json.loads(_b64url_decode(token.split(".")[1]))
    except (IndexError, binascii.Error, ValueError, TypeError,
            UnicodeDecodeError, json.JSONDecodeError) as exc:
        # binascii.Error: invalid base64 alphabet/padding in the payload segment
        #   (e.g. 'header.!!!invalid!!!.sig' — listed EXPLICITLY, not left to its
        #   ValueError subclass, so the guard is unmistakable and jump-proof
        #   against a stdlib change);
        # IndexError: fewer than 2 dot-segments;
        # UnicodeDecodeError: decoded bytes are not valid UTF-8 for json.loads;
        # ValueError: other json/base64 value problems;
        # JSONDecodeError: payload not JSON.
        logger.debug("decode_jwt_payload: malformed token (%s); returning empty (%s)",
                     type(exc).__name__, exc)
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
# HTTP helpers (LOCAL target only — the host guard is enforced HERE)
# --------------------------------------------------------------------------- #
def _read_capped(fp) -> str:
    """Read at most MAX_RESPONSE_BYTES from a response/error file object so a
    huge or streaming body cannot exhaust memory (adversarial-input)."""
    return fp.read(MAX_RESPONSE_BYTES).decode("utf-8", "replace")


# HTTP methods safe to auto-retry: replaying them cannot create or duplicate
# server state. POST is DELIBERATELY excluded — replaying a POST /auth/login
# whose response was merely lost in transit would mint a DUPLICATE token
# server-side (data-integrity). A lost non-idempotent write is surfaced to the
# caller (TRANSIENT_STATUS) instead of being silently retried.
IDEMPOTENT_METHODS = frozenset({"GET", "HEAD", "OPTIONS", "PUT", "DELETE"})


def _close_error_fp(err: urllib.error.HTTPError) -> None:
    """Close the fp behind an HTTPError so repeated 4xx/5xx don't leak FDs.

    A close failure is LOGGED (never silently swallowed) so a leaking-handle
    condition is visible in telemetry (observability)."""
    fp = getattr(err, "fp", None)
    if fp is None:
        return
    try:
        fp.close()
    except OSError as exc:
        logger.warning("Failed to close HTTPError fp: %s", exc)


def _read_error_body(err: urllib.error.HTTPError) -> tuple[int, str]:
    """Read a (capped) HTTP error body and ALWAYS close its fp.

    An HTTP status (e.g. 401) is a VALID, non-transient answer, so we return it.
    Reading the body can itself time out on a slow network; that failure is
    caught HERE (device-stack) — we return the status with an empty body rather
    than letting a TimeoutError escape the request. The fp is closed in a
    finally either way (memory-resource)."""
    try:
        return err.code, _read_capped(err)
    except (TimeoutError, OSError, urllib.error.URLError) as exc:
        logger.warning("_read_error_body: reading %s body failed: %s", err.code, exc)
        return err.code, ""
    finally:
        _close_error_fp(err)


def _sleep_backoff(attempt: int) -> None:
    """Bounded exponential backoff before the next retry attempt (network)."""
    time.sleep(BACKOFF_BASE_S * (2 ** (attempt - 1)))


def _build_request(base_url: str, method: str, path: str,
                   headers, body) -> urllib.request.Request:
    """Validate inputs, enforce the SSRF guard, and construct the Request.

    Split out of ``_request`` so construction/validation is one concern and the
    retry loop is another (maintainability). Raises ValueError on a bad
    base_url/path (a caller bug, fail loud) and PermissionError on a non-local
    host (SSRF containment) — both BEFORE any socket opens."""
    if not isinstance(base_url, str) or not base_url:
        # Log before raising so a bad-input caller bug leaves an audit trail even
        # if the caller swallows the exception (observability).
        logger.warning("_build_request: invalid base_url %r", base_url)
        raise ValueError(f"_request: base_url must be a non-empty str, got {base_url!r}")
    if not isinstance(path, str):
        logger.warning("_build_request: invalid path %r", path)
        raise ValueError(f"_request: path must be a str, got {path!r}")
    url = base_url.rstrip("/") + path
    _assert_local(url)  # SSRF guard — refuse non-local hosts before dialing.
    data = json.dumps(body).encode() if body is not None else None
    hdrs = {"Content-Type": "application/json"}
    if headers:
        hdrs.update(headers)
    return urllib.request.Request(url, data=data, method=method, headers=hdrs)


def _request(base_url: str, method: str, path: str, *, headers=None, body=None) -> tuple[int, str]:
    """Perform one HTTP call against the LOCAL sandbox and return (code, text).

    Delegates validation/SSRF/construction to ``_build_request`` and error-body
    handling to ``_read_error_body`` (maintainability: one concern each). Only
    IDEMPOTENT methods are retried on a transient transport failure — a lost
    POST is NOT replayed (data-integrity). On retry exhaustion (or a lost
    non-idempotent write) returns the documented ``(TRANSIENT_STATUS, "")``
    sentinel that callers already treat as 'no usable response'."""
    req = _build_request(base_url, method, path, headers, body)
    retryable = method.upper() in IDEMPOTENT_METHODS

    last_exc: Optional[BaseException] = None
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            with urllib.request.urlopen(req, timeout=REQUEST_TIMEOUT_S) as r:
                return r.getcode(), _read_capped(r)
        except urllib.error.HTTPError as e:
            return _read_error_body(e)
        except (urllib.error.URLError, TimeoutError, ConnectionError, OSError) as exc:
            last_exc = exc
            if not retryable:
                # Non-idempotent write whose outcome is now UNKNOWN — do not
                # replay (would risk a duplicate). Fail fast to the caller.
                logger.warning("_request %s %s failed (non-idempotent, no retry): %s",
                               method, path, exc)
                return TRANSIENT_STATUS, ""
            logger.warning("_request %s %s attempt %d/%d failed: %s",
                           method, path, attempt, MAX_ATTEMPTS, exc)
            if attempt < MAX_ATTEMPTS:
                _sleep_backoff(attempt)
    logger.error("_request %s %s exhausted %d attempts: %s",
                 method, path, MAX_ATTEMPTS, last_exc)
    return TRANSIENT_STATUS, ""


def login_token(base_url: str) -> Optional[str]:
    """POST valid creds to /auth/login and return the accessToken, or None.

    Returns None (never raises) on: a non-empty base_url that is non-200, a
    body that is not JSON, or a JSON body missing accessToken — all logged.
    A None/invalid base_url is a caller bug and surfaces as a ValueError from
    _request (adversarial-input: fail loud on a programming error, degrade
    gracefully on a runtime auth failure)."""
    code, text = _request(base_url, "POST", LOGIN_ENDPOINT["path"], body=VALID_CREDS)
    if code != 200:
        logger.warning("login_token: /auth/login returned %s (expected 200)", code)
        return None
    try:
        token = json.loads(text).get("accessToken")
    except (ValueError, AttributeError, json.JSONDecodeError) as exc:
        # Non-JSON body or JSON that is not an object — cannot extract a token.
        logger.warning("login_token: could not parse login response: %s", exc)
        return None
    if not token:
        logger.warning("login_token: login response had no accessToken")
        return None
    return token


# --------------------------------------------------------------------------- #
# Credential constructors — recipe -> the Authorization header(s) to send.
# Returns (headers_dict, note). headers_dict is None => "send no auth header".
# The agents never run this; the harness and the gold builder do.
# --------------------------------------------------------------------------- #
def build_credential(recipe: dict, base_url: str, secret: str) -> tuple[Optional[dict], str]:
    """Construct the Authorization header for one recipe kind.

    ``base_url`` is validated up front so a None/garbage value yields a clear
    note instead of crashing at ``.rstrip('/')`` deep in _request
    (adversarial-input). A non-dict ``recipe`` (list, str) is likewise rejected
    once here so the ``_build_*`` helpers never call ``.get()`` on a non-dict.
    Every non-happy path returns (None, <human note>) so the caller records WHY
    no credential was built — never a silent success."""
    if not isinstance(base_url, str) or not base_url:
        return None, f"invalid base_url: {base_url!r}"
    if recipe is not None and not isinstance(recipe, dict):
        return None, f"invalid recipe (expected dict): {type(recipe).__name__}"

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
        return _build_truncated(recipe, base_url, prefix, hdr)

    if kind == "expired_token":
        return _build_expired(recipe, base_url, secret, prefix, hdr)

    if kind == "revoked_token":
        return _build_revoked(base_url, prefix, hdr)

    return None, f"unknown recipe kind: {kind!r}"


def _coerce_int(value: object, default: int) -> Optional[int]:
    """Best-effort int coercion for an UNTRUSTED recipe field.

    Returns ``default`` when the field is absent (None) and the parsed int when
    it is a clean int / short digit-string. Returns None on garbage (e.g. 'abc',
    a float string, a list) so the CALLER can fail closed with a clear note
    instead of letting ``int('abc')`` raise an unhandled ValueError. bool is
    rejected too (``True`` is not a char count).

    adversarial-input — resource-exhaustion guard: a string field is
    LENGTH-CAPPED at MAX_INT_FIELD_CHARS *before* ``int()`` is called, so a
    million-digit bomb (e.g. drop_chars='9'*1_000_000) is rejected in O(1)
    rather than fed to ``int()`` — whose decimal parse of a huge digit string is
    super-linear and can hang / exhaust CPU. An already-``int`` value is also
    magnitude-bounded (a caller could pass a giant literal) so downstream
    arithmetic and slicing stay cheap."""
    if value is None:
        return default
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value if abs(value) < 10 ** MAX_INT_FIELD_CHARS else None
    if isinstance(value, str):
        text = value.strip()
        # Cap length BEFORE parsing — this is the DoS guard. A sign plus up to
        # MAX_INT_FIELD_CHARS digits is the widest legitimate field.
        if not text or len(text) > MAX_INT_FIELD_CHARS + 1:
            return None
        try:
            return int(text)
        except ValueError:
            return None
    return None


def _build_truncated(recipe: dict, base_url: str, prefix: str, hdr: str) -> tuple[Optional[dict], str]:
    """valid token minus its last ``drop_chars`` characters.

    drop_chars=0 must return the FULL token (a zero-char truncation is a no-op).
    We slice ``tok[:len(tok) - drop]`` rather than ``tok[:-drop]`` because
    Python's ``tok[:-0]`` is ``tok[:0]`` == "" — the reported math bug
    (math-correctness). Negative drop is clamped to 0. A non-numeric
    ``drop_chars`` fails closed with a note rather than raising
    (adversarial-input)."""
    raw = _coerce_int(recipe.get("drop_chars"), 8)
    if raw is None:
        logger.warning("_build_truncated: non-numeric drop_chars %r", recipe.get("drop_chars"))
        return None, f"invalid drop_chars: {recipe.get('drop_chars')!r}"
    drop = max(0, raw)
    tok = login_token(base_url)
    if not tok:
        return None, "login failed"
    end = len(tok) - drop if drop < len(tok) else 0
    return {hdr: prefix + tok[:end]}, f"valid token minus last {drop} chars"


def _build_expired(recipe: dict, base_url: str, secret: str, prefix: str, hdr: str) -> tuple[Optional[dict], str]:
    """re-sign the real token's payload with an exp offset from server-now.

    A non-numeric ``exp_delta_sec`` fails closed with a note rather than raising
    an unhandled ValueError from ``int(...)`` (adversarial-input).

    device-stack — backward wall-clock jump: an EXPIRED recipe (delta < 0) must
    stay expired no matter what the host clock does between minting here and the
    server validating later. We do NOT trust the small requested delta (e.g.
    delta=-5 would land exp only 5s in the past, which a routine NTP correction
    could overtake). Instead we clamp exp to AT LEAST EXPIRY_SKEW_MARGIN_SEC (24h)
    before ``now``, so exp is a full day in the past relative to the SAME clock
    read used to mint it — any realistic backward jump still leaves the server's
    (now-earlier) clock ahead of exp. iat is set below exp by mint_hs256, so the
    token is structurally, unambiguously stale."""
    delta = _coerce_int(recipe.get("exp_delta_sec"), -3600)
    if delta is None:
        logger.warning("_build_expired: non-numeric exp_delta_sec %r", recipe.get("exp_delta_sec"))
        return None, f"invalid exp_delta_sec: {recipe.get('exp_delta_sec')!r}"
    tok = login_token(base_url)
    if not tok:
        return None, "login failed"
    payload = decode_jwt_payload(tok)
    now = _server_now(base_url)
    exp = now + delta
    if delta < 0:
        exp = min(exp, now - EXPIRY_SKEW_MARGIN_SEC)
    expired = mint_hs256(payload, secret, exp)
    return {hdr: prefix + expired}, f"re-signed real payload, exp = now {delta:+d}s"


def _build_revoked(base_url: str, prefix: str, hdr: str) -> tuple[Optional[dict], str]:
    """login, POST /auth/logout, then REUSE the same token.

    The logout result is CHECKED and we fail closed: if logout did not return a
    2xx the token was (probably) never revoked, so returning it as 'revoked'
    would report failure as success (error-handling-resilience). In that case we
    return (None, <reason>) so the sub-test is recorded as un-constructed rather
    than a false pass."""
    tok = login_token(base_url)
    if not tok:
        return None, "login failed"
    code, _text = _request(base_url, REVOKE_EQUIVALENT["method"],
                           REVOKE_EQUIVALENT["path"], headers={hdr: prefix + tok})
    if not (200 <= code < 300):
        logger.error("_build_revoked: logout returned %s; token not revoked", code)
        return None, f"logout failed (status {code}); token not revoked"
    return {hdr: prefix + tok}, "same token reused after POST /auth/logout"


def _server_now(base_url: str) -> int:
    """Server 'now' as a unix timestamp, used for exp deltas.

    MUST be wall-clock (``time.time()``), not a monotonic clock: the value is an
    ABSOLUTE unix ``exp`` the server compares against ITS wall clock, so a
    monotonic counter (arbitrary epoch) would mint nonsense expiries. The server
    and this process share the host clock (air-gapped, same machine), so local
    wall-clock IS the server's time.

    ``base_url`` is part of this module's PUBLIC signature (two dependents call
    ``_server_now(base_url)``); it identifies WHICH target's clock is meant and
    is unused only because that target is co-located. Do not drop the parameter
    without updating those callers and the golden baseline."""
    return int(time.time())


# --------------------------------------------------------------------------- #
# Tolerant iteration over a plan (agent's OR canonical)
# --------------------------------------------------------------------------- #
def iter_subtests(plan: dict) -> Iterator[tuple[str, str, dict, str]]:
    """Yield (scheme_name, label, recipe, expected_class) for each executable
    sub-test in a plan. Tolerant of a partial / malformed agent plan.

    An agent may emit a non-dict plan (a list, a string, None). We treat any
    non-dict as 'no plan' and yield nothing rather than crashing on ``.get()``
    (adversarial-input); the same guard is applied to each scheme and sub-test
    entry, which an agent could likewise mis-shape."""
    if not isinstance(plan, dict):
        return
    for scheme in plan.get("schemes", []) or []:
        if not isinstance(scheme, dict):
            continue
        sname = scheme.get("scheme") or scheme.get("name") or "unknown"
        if scheme.get("implemented") is False:
            continue
        for st in scheme.get("subtests", []) or []:
            if not isinstance(st, dict):
                continue
            label = st.get("label")
            if not label:
                continue
            recipe = st.get("credential") or st.get("recipe") or {}
            expected = st.get("expected_class") or _default_expected(label)
            yield sname, label, recipe, expected


def iter_not_applicable(plan: dict) -> Iterator[tuple[str, Optional[str]]]:
    """Yield (item_id, status) for each not-applicable item the agent enumerated.

    Non-dict plan or non-dict entries are skipped, not crashed on
    (adversarial-input)."""
    if not isinstance(plan, dict):
        return
    for x in plan.get("not_applicable", []) or []:
        if not isinstance(x, dict):
            continue
        item = x.get("item") or x.get("scheme") or x.get("subtest")
        if item:
            yield str(item), x.get("status")


def _default_expected(label: str) -> str:
    """Expected class when a sub-test omits one: only 'valid' should pass (2xx);
    every other credential must be rejected (401).

    Kept as a named function (not inlined) so the 'valid => 2xx, else 401'
    policy lives in exactly one place; iter_subtests reads clearer for it."""
    return "2xx" if label == "valid" else "401"
