#!/usr/bin/env python3
"""Unit tests for agents/common/auth_spec.py — the shared auth-flow substrate.

Covers the whole credential-construction WORKFLOW and its safety properties:
  * canonical_plan() / SUBTESTS_ITER() shape and contents;
  * classify() for every branch (2xx / 401 / 4xx / other / None);
  * decode_jwt_payload() valid / malformed / truncated / non-str;
  * mint_hs256() round-trips through decode_jwt_payload() AND produces a
    cryptographically valid HS256 signature (independently recomputed);
  * build_credential() every recipe kind, incl. truncate_token drop_chars=0
    (must return the FULL token) and the revoked_token logout-failure path
    (must fail closed, NOT report success);
  * SSRF containment: _assert_local() accepts loopback/private, rejects
    public + link-local; _request() rejects base_url=None and non-local hosts,
    caps body reads, and closes the HTTPError fp.

No real network calls are made — login_token / _request / urlopen are stubbed.

Run: agent-foundry/.venv/bin/python \
     agent-foundry/tests/unit/agents/common/test_auth_spec.py
"""
from __future__ import annotations

import base64
import hashlib
import hmac
import importlib
import io
import json
import sys
from pathlib import Path

WS = Path(__file__).resolve().parents[4]          # agent-foundry
sys.path.insert(0, str(WS / "agents" / "common"))
import auth_spec as a  # noqa: E402

importlib.reload(a)

HDR = a.SCHEME["header_name"]
PREFIX = a.SCHEME["prefix"]
LOCAL = "http://localhost:8899"


# --- canonical_plan ---------------------------------------------------------
def test_canonical_plan_shape():
    p = a.canonical_plan()
    assert p["protected_endpoint"] == dict(a.PROTECTED_ENDPOINT)
    assert len(p["schemes"]) == 1
    sch = p["schemes"][0]
    assert sch["scheme"] == "bearerJWT" and sch["implemented"] is True
    assert len(sch["subtests"]) == 5
    assert [s["label"] for s in sch["subtests"]] == \
        ["valid", "missing", "malformed", "expired", "revoked"]
    assert len(p["not_applicable"]) == len(a.NOT_APPLICABLE)


def test_canonical_plan_is_deep_copy():
    p = a.canonical_plan()
    p["schemes"][0]["subtests"][0]["credential"]["kind"] = "MUTATED"
    # module constant untouched
    assert a.SUBTESTS[0][1]["kind"] == "valid_token"


# --- SUBTESTS_ITER ----------------------------------------------------------
def test_subtests_iter_count_and_structure():
    rows = list(a.SUBTESTS_ITER())
    assert len(rows) == 5
    for row in rows:
        assert len(row) == 4
        sname, label, recipe, exp = row
        assert sname == "bearerJWT"
        assert isinstance(label, str) and isinstance(recipe, dict)
        assert exp in ("2xx", "401")
    # yielded recipe is a copy, not the shared constant
    rows[0][2]["kind"] = "X"
    assert a.SUBTESTS[0][1]["kind"] == "valid_token"


# --- classify ---------------------------------------------------------------
def test_classify_every_branch():
    assert a.classify(None) == "none"
    assert a.classify(200) == "2xx"
    assert a.classify(204) == "2xx"
    assert a.classify(401) == "401"
    assert a.classify(403) == "4xx_403"
    assert a.classify(404) == "4xx_404"
    assert a.classify(500) == "other_500"
    assert a.classify(302) == "other_302"


# --- decode_jwt_payload -----------------------------------------------------
def test_decode_jwt_payload_valid():
    tok = a.mint_hs256({"sub": 42, "name": "e"}, "secret", 9999999999)
    got = a.decode_jwt_payload(tok)
    assert got["sub"] == 42 and got["name"] == "e"


def test_decode_jwt_payload_malformed_returns_empty():
    assert a.decode_jwt_payload("not-a-jwt") == {}
    assert a.decode_jwt_payload("only.two") == {}          # payload not base64/json
    assert a.decode_jwt_payload("") == {}
    assert a.decode_jwt_payload("a.$$$.c") == {}           # bad base64


def test_decode_jwt_payload_truncated_returns_empty():
    tok = a.mint_hs256({"sub": 1}, "s", 9999999999)
    header, payload_seg, sig = tok.split(".")
    # Corrupting the PAYLOAD segment (drop its last 3 chars) must yield {} —
    # a real, non-tautological assertion that decode rejects a broken payload.
    broken = f"{header}.{payload_seg[:-3]}.{sig}"
    assert a.decode_jwt_payload(broken) == {}
    # Truncating anywhere else must never raise and must return a dict.
    assert isinstance(a.decode_jwt_payload(tok[:5]), dict)
    assert isinstance(a.decode_jwt_payload(tok[:-8]), dict)


def test_decode_jwt_payload_non_str():
    assert a.decode_jwt_payload(None) == {}          # type: ignore[arg-type]
    assert a.decode_jwt_payload(12345) == {}          # type: ignore[arg-type]


def test_decode_jwt_payload_invalid_base64_alphabet_returns_empty():
    """Exact adversarial-input case: a JWT whose payload segment contains
    characters outside the base64url alphabet must NOT raise binascii.Error —
    decode_jwt_payload catches it and returns {}."""
    for bad in ("header.!!!invalid_base64!!!.sig",
                "aaa.@@@@@@@@.bbb",
                "x.aGVsbG8=extra$$.y",
                "x.\x00\x01\x02.y"):
        assert a.decode_jwt_payload(bad) == {}, bad


def test_b64url_decode_rejects_bad_alphabet():
    """The source-level guard: _b64url_decode(validate=True) raises binascii.Error
    on a non-alphabet char, so callers' `except binascii.Error` is guaranteed to
    fire (rather than base64 silently discarding stray bytes)."""
    import binascii as _b
    try:
        a._b64url_decode("!!!invalid!!!")
        assert False, "expected binascii.Error for non-alphabet input"
    except _b.Error:
        pass
    # a clean segment still decodes
    assert a._b64url_decode(a._b64url(b"hello")) == b"hello"


# --- mint_hs256 -------------------------------------------------------------
def _hs256_signature_valid(token: str, secret: str) -> bool:
    """Independently recompute the HS256 signature and compare, so the test
    catches a wrong/empty key, a wrong algorithm, or a corrupted signature —
    not merely that the payload round-trips."""
    header_seg, payload_seg, sig_seg = token.split(".")
    signing_input = f"{header_seg}.{payload_seg}".encode()
    expected = hmac.new(secret.encode(), signing_input, hashlib.sha256).digest()
    pad = "=" * (-len(sig_seg) % 4)
    actual = base64.urlsafe_b64decode(sig_seg + pad)
    return hmac.compare_digest(expected, actual)


def test_mint_hs256_roundtrips():
    tok = a.mint_hs256({"sub": 7}, "sekret", 1700000000)
    parts = tok.split(".")
    assert len(parts) == 3
    payload = a.decode_jwt_payload(tok)
    assert payload["sub"] == 7 and payload["exp"] == 1700000000
    assert payload["iat"] == 1700000000 - 60


def test_mint_hs256_signature_is_cryptographically_valid():
    tok = a.mint_hs256({"sub": 7}, "sekret", 1700000000)
    assert _hs256_signature_valid(tok, "sekret"), "signature must verify with the real secret"
    # A different secret must NOT verify — proves the sig binds to the key.
    assert not _hs256_signature_valid(tok, "wrong-secret")
    # Header must declare HS256.
    header_seg = tok.split(".")[0]
    header = json.loads(a._b64url_decode(header_seg))
    assert header["alg"] == "HS256" and header["typ"] == "JWT"


# --- _assert_local ----------------------------------------------------------
def test_assert_local_accepts_loopback_and_private():
    for url in ("http://localhost:8899", "http://127.0.0.1", "http://[::1]:80",
                "http://10.0.0.5", "http://192.168.1.9", "http://172.16.0.1"):
        a._assert_local(url)   # must not raise


def test_assert_local_rejects_public_and_linklocal():
    for url in ("http://8.8.8.8", "http://169.254.169.254", "http://example.com",
                "http://"):
        try:
            a._assert_local(url)
            assert False, f"expected PermissionError for {url}"
        except PermissionError:
            pass


# --- _request boundary validation + SSRF ------------------------------------
def test_request_rejects_none_base_url():
    for bad in (None, "", 123):
        try:
            a._request(bad, "GET", "/x")   # type: ignore[arg-type]
            assert False, f"expected ValueError for base_url={bad!r}"
        except ValueError:
            pass


def test_request_rejects_non_local_host():
    try:
        a._request("http://8.8.8.8", "GET", "/x")
        assert False, "expected PermissionError for public host"
    except PermissionError:
        pass


def test_request_rejects_non_str_path():
    try:
        a._request(LOCAL, "GET", None)   # type: ignore[arg-type]
        assert False, "expected ValueError for non-str path"
    except ValueError:
        pass


class _FakeResp:
    """Minimal urlopen context-manager stand-in."""
    def __init__(self, code: int, body: bytes):
        self._code = code
        self._buf = io.BytesIO(body)

    def __enter__(self):
        return self

    def __exit__(self, *exc):
        return False

    def getcode(self):
        return self._code

    def read(self, n=-1):
        return self._buf.read(n)


def test_request_caps_body_read(monkeypatch=None):
    huge = b"x" * (a.MAX_RESPONSE_BYTES + 5000)
    orig = a.urllib.request.urlopen
    a.urllib.request.urlopen = lambda req, timeout=0: _FakeResp(200, huge)
    try:
        code, text = a._request(LOCAL, "GET", "/big")
    finally:
        a.urllib.request.urlopen = orig
    assert code == 200
    assert len(text) <= a.MAX_RESPONSE_BYTES   # capped, not the full huge body


class _FakeHTTPError(Exception):
    """Stand-in for urllib.error.HTTPError with a closable .fp."""
    def __init__(self, code):
        self.code = code
        self.closed = False
        self.fp = self
        self._buf = io.BytesIO(b'{"err":1}')

    def read(self, n=-1):
        return self._buf.read(n)

    def close(self):
        self.closed = True


def test_request_closes_httperror_fp():
    err = _FakeHTTPError(401)
    orig_open, orig_err = a.urllib.request.urlopen, a.urllib.error.HTTPError

    def _raise(req, timeout=0):
        raise err

    a.urllib.request.urlopen = _raise
    a.urllib.error.HTTPError = _FakeHTTPError   # so the except clause matches
    try:
        code, text = a._request(LOCAL, "GET", "/protected")
    finally:
        a.urllib.request.urlopen = orig_open
        a.urllib.error.HTTPError = orig_err
    assert code == 401 and '"err"' in text
    assert err.closed is True                   # fp closed -> no FD leak


class _TimeoutFP(_FakeHTTPError):
    """HTTPError whose body read TIMES OUT (device-stack: slow-network read)."""
    def read(self, n=-1):
        raise TimeoutError("read timed out")


def test_request_error_body_read_timeout_does_not_propagate():
    err = _TimeoutFP(500)
    orig_open, orig_err = a.urllib.request.urlopen, a.urllib.error.HTTPError

    def _raise(req, timeout=0):
        raise err

    a.urllib.request.urlopen = _raise
    a.urllib.error.HTTPError = _TimeoutFP
    try:
        code, text = a._request(LOCAL, "GET", "/slow")   # must NOT raise
    finally:
        a.urllib.request.urlopen = orig_open
        a.urllib.error.HTTPError = orig_err
    assert code == 500 and text == ""          # status kept, body empty
    assert err.closed is True                   # fp still closed on the timeout path


class _CloseFailFP(_FakeHTTPError):
    """HTTPError whose fp.close() raises (observability: must be logged)."""
    def close(self):
        raise OSError("close failed")


def test_close_error_fp_logs_on_failure(caplog=None):
    err = _CloseFailFP(401)
    records = []
    orig_warn = a.logger.warning
    a.logger.warning = lambda msg, *args: records.append(msg % args if args else msg)
    try:
        a._close_error_fp(err)                  # must not raise
    finally:
        a.logger.warning = orig_warn
    assert any("Failed to close HTTPError fp" in r for r in records)


def test_request_does_not_retry_post_on_transient_failure():
    """A lost POST must NOT be replayed (data-integrity: no duplicate token)."""
    calls = {"n": 0}
    orig = a.urllib.request.urlopen

    def _boom(req, timeout=0):
        calls["n"] += 1
        raise ConnectionError("reset")

    a.urllib.request.urlopen = _boom
    try:
        code, text = a._request(LOCAL, "POST", "/auth/login", body={"u": 1})
    finally:
        a.urllib.request.urlopen = orig
    assert code == a.TRANSIENT_STATUS and text == ""
    assert calls["n"] == 1                       # exactly one attempt, no replay


def test_request_retries_idempotent_get_on_transient_failure():
    """A GET (idempotent) IS retried up to MAX_ATTEMPTS (network resilience)."""
    calls = {"n": 0}
    orig_open, orig_sleep = a.urllib.request.urlopen, a.time.sleep

    def _boom(req, timeout=0):
        calls["n"] += 1
        raise TimeoutError("slow")

    a.urllib.request.urlopen = _boom
    a.time.sleep = lambda s: None                # don't actually wait in tests
    try:
        code, text = a._request(LOCAL, "GET", "/protected")
    finally:
        a.urllib.request.urlopen = orig_open
        a.time.sleep = orig_sleep
    assert code == a.TRANSIENT_STATUS
    assert calls["n"] == a.MAX_ATTEMPTS          # retried the full budget


# --- _coerce_int ------------------------------------------------------------
def test_coerce_int_valid_and_default():
    assert a._coerce_int(None, 8) == 8
    assert a._coerce_int(5, 8) == 5
    assert a._coerce_int(0, 8) == 0
    assert a._coerce_int("12", 8) == 12
    assert a._coerce_int("  -3 ", 8) == -3


def test_coerce_int_garbage_returns_none():
    for bad in ("abc", "1.5", "", "0x10", [1], {"a": 1}, 3.14, True, False):
        assert a._coerce_int(bad, 8) is None, bad


def test_coerce_int_rejects_oversized_string_without_parsing():
    """adversarial-input DoS guard: a million-digit string must be rejected in
    O(1) by the length cap, NEVER handed to int(). We assert it returns None
    fast (bounded time) — a huge-int parse would hang."""
    import time as _t
    bomb = "9" * 1_000_000
    start = _t.perf_counter()
    assert a._coerce_int(bomb, 8) is None
    assert _t.perf_counter() - start < 0.05          # rejected pre-parse, not parsed
    # a signed bomb too
    assert a._coerce_int("-" + "1" * 500_000, 8) is None


def test_coerce_int_boundary_length():
    max_len = a.MAX_INT_FIELD_CHARS
    ok = "9" * max_len                                # exactly at the digit cap
    assert a._coerce_int(ok, 0) == int(ok)
    assert a._coerce_int("-" + ok, 0) == -int(ok)     # sign doesn't count against digits
    too_long = "9" * (max_len + 2)                    # beyond sign+digits budget
    assert a._coerce_int(too_long, 0) is None


def test_coerce_int_rejects_oversized_int_literal():
    """An already-int recipe value is magnitude-bounded so downstream slicing /
    arithmetic stays cheap."""
    assert a._coerce_int(10 ** a.MAX_INT_FIELD_CHARS, 0) is None
    assert a._coerce_int(-(10 ** a.MAX_INT_FIELD_CHARS), 0) is None
    assert a._coerce_int(10 ** a.MAX_INT_FIELD_CHARS - 1, 0) == 10 ** a.MAX_INT_FIELD_CHARS - 1


def test_build_credential_rejects_oversized_numeric_fields():
    """The DoS string bomb through the real recipe path fails closed with a
    clear note, no hang."""
    orig = a.login_token
    _stub_login("abcdefgh")
    try:
        h, note = a.build_credential(
            {"kind": "truncate_token", "drop_chars": "9" * 1_000_000}, LOCAL, "s")
        assert h is None and "invalid drop_chars" in note
        h, note = a.build_credential(
            {"kind": "expired_token", "exp_delta_sec": "9" * 1_000_000}, LOCAL, "s")
        assert h is None and "invalid exp_delta_sec" in note
    finally:
        a.login_token = orig


# --- adversarial non-numeric recipe fields fail closed (no crash) -----------
def test_build_credential_truncate_non_numeric_drop_fails_closed():
    orig = a.login_token
    _stub_login("abcdefgh")
    try:
        h, note = a.build_credential(
            {"kind": "truncate_token", "drop_chars": "abc"}, LOCAL, "s")
    finally:
        a.login_token = orig
    assert h is None and "invalid drop_chars" in note   # no ValueError raised


def test_build_credential_expired_non_numeric_delta_fails_closed():
    orig = a.login_token
    _stub_login(a.mint_hs256({"sub": 1}, "s", 2000000000))
    try:
        h, note = a.build_credential(
            {"kind": "expired_token", "exp_delta_sec": "soon"}, LOCAL, "s")
    finally:
        a.login_token = orig
    assert h is None and "invalid exp_delta_sec" in note   # no ValueError raised


# --- build_credential each recipe -------------------------------------------
def _stub_login(token):
    a.login_token = lambda base_url: token


def test_build_credential_invalid_base_url():
    h, note = a.build_credential({"kind": "valid_token"}, None, "s")  # type: ignore[arg-type]
    assert h is None and "invalid base_url" in note


def test_build_credential_no_auth():
    h, note = a.build_credential({"kind": "no_auth"}, LOCAL, "s")
    assert h is None and "no Authorization" in note


def test_build_credential_unknown_kind():
    h, note = a.build_credential({"kind": "bogus"}, LOCAL, "s")
    assert h is None and "unknown recipe kind" in note
    h, note = a.build_credential(None, LOCAL, "s")   # type: ignore[arg-type]
    assert h is None


def test_build_credential_valid_token():
    orig = a.login_token
    _stub_login("TOK123")
    try:
        h, note = a.build_credential({"kind": "valid_token"}, LOCAL, "s")
    finally:
        a.login_token = orig
    assert h == {HDR: PREFIX + "TOK123"}


def test_build_credential_valid_token_login_fail():
    orig = a.login_token
    _stub_login(None)
    try:
        h, note = a.build_credential({"kind": "valid_token"}, LOCAL, "s")
    finally:
        a.login_token = orig
    assert h is None and "login failed" in note


def test_build_credential_truncate_drop_zero_returns_full_token():
    orig = a.login_token
    _stub_login("abcdefgh")
    try:
        h, note = a.build_credential({"kind": "truncate_token", "drop_chars": 0}, LOCAL, "s")
    finally:
        a.login_token = orig
    assert h == {HDR: PREFIX + "abcdefgh"}, "drop_chars=0 must keep the FULL token"


def test_build_credential_truncate_drops_chars():
    orig = a.login_token
    _stub_login("abcdefgh")
    try:
        h, _ = a.build_credential({"kind": "truncate_token", "drop_chars": 3}, LOCAL, "s")
    finally:
        a.login_token = orig
    assert h == {HDR: PREFIX + "abcde"}


def test_build_credential_truncate_overlong_drop_clamps_empty():
    orig = a.login_token
    _stub_login("abc")
    try:
        h, _ = a.build_credential({"kind": "truncate_token", "drop_chars": 99}, LOCAL, "s")
    finally:
        a.login_token = orig
    assert h == {HDR: PREFIX + ""}          # clamped, no crash / negative index


def test_build_credential_expired_token():
    orig_login = a.login_token
    real_tok = a.mint_hs256({"sub": 9}, "s", 2000000000)
    _stub_login(real_tok)
    try:
        h, note = a.build_credential(
            {"kind": "expired_token", "exp_delta_sec": -3600}, LOCAL, "s")
    finally:
        a.login_token = orig_login
    assert h is not None
    minted = h[HDR][len(PREFIX):]
    payload = a.decode_jwt_payload(minted)
    assert payload["sub"] == 9                     # re-signed the real payload
    assert payload["exp"] < a._server_now(LOCAL)   # exp is in the past
    # The re-signed expired token must carry a VALID signature under the secret
    # passed to build_credential — else the server would say 'invalid signature'
    # instead of 'jwt expired', defeating the expired sub-test.
    assert _hs256_signature_valid(minted, "s")


def test_build_credential_expired_clamps_past_backward_clock(monkeypatch=None):
    """device-stack: even with a TINY negative delta, an expired recipe is
    clamped a full margin into the past (exp <= mint_now - margin)."""
    mint_now = 2_000_000_000
    orig_login, orig_now = a.login_token, a._server_now
    _stub_login(a.mint_hs256({"sub": 1}, "s", mint_now + 10_000))
    a._server_now = lambda base_url: mint_now
    try:
        # delta=-1 would land exp barely in the past; the clamp must still push
        # it EXPIRY_SKEW_MARGIN_SEC back.
        h, _ = a.build_credential(
            {"kind": "expired_token", "exp_delta_sec": -1}, LOCAL, "s")
    finally:
        a.login_token, a._server_now = orig_login, orig_now
    payload = a.decode_jwt_payload(h[HDR][len(PREFIX):])
    exp = payload["exp"]
    assert exp <= mint_now - a.EXPIRY_SKEW_MARGIN_SEC
    # iat is set below exp by mint_hs256 -> structurally, unambiguously stale.
    assert payload["iat"] <= exp


def test_expired_token_survives_backward_clock_jump():
    """device-stack: mint at T, then the SERVER clock jumps backward by nearly
    the whole margin — the token must STILL be expired against that earlier
    clock (exp < jumped-back server-now)."""
    mint_now = 2_000_000_000
    orig_login, orig_now = a.login_token, a._server_now
    _stub_login(a.mint_hs256({"sub": 1}, "s", mint_now + 10_000))
    a._server_now = lambda base_url: mint_now
    try:
        h, _ = a.build_credential(
            {"kind": "expired_token", "exp_delta_sec": -5}, LOCAL, "s")
    finally:
        a.login_token, a._server_now = orig_login, orig_now
    exp = a.decode_jwt_payload(h[HDR][len(PREFIX):])["exp"]
    # Server clock jumps backward by (margin - 1) seconds after minting.
    server_now_after_jump = mint_now - (a.EXPIRY_SKEW_MARGIN_SEC - 1)
    assert exp < server_now_after_jump, "token must remain expired after the jump"


def test_build_credential_expired_tolerates_malformed_login_token():
    """adversarial-input: if login returns a token whose payload segment is
    invalid base64, decode_jwt_payload must degrade to {} and the expired path
    must still mint a (valid-signature) token, not crash."""
    orig_login, orig_now = a.login_token, a._server_now
    a.login_token = lambda base_url: "header.!!!invalid_base64!!!.sig"
    a._server_now = lambda base_url: 2_000_000_000
    try:
        h, note = a.build_credential(
            {"kind": "expired_token", "exp_delta_sec": -3600}, LOCAL, "s")
    finally:
        a.login_token, a._server_now = orig_login, orig_now
    assert h is not None                      # did not crash on binascii.Error
    minted = h[HDR][len(PREFIX):]
    assert _hs256_signature_valid(minted, "s")
    assert a.decode_jwt_payload(minted)["exp"] <= 2_000_000_000 - a.EXPIRY_SKEW_MARGIN_SEC


def test_build_credential_revoked_logout_success():
    orig_login, orig_req = a.login_token, a._request
    _stub_login("TOKREV")
    a._request = lambda base, method, path, **kw: (200, "{}")   # logout OK
    try:
        h, note = a.build_credential({"kind": "revoked_token"}, LOCAL, "s")
    finally:
        a.login_token, a._request = orig_login, orig_req
    assert h == {HDR: PREFIX + "TOKREV"}
    assert "reused after POST /auth/logout" in note


def test_build_credential_revoked_logout_failure_fails_closed():
    orig_login, orig_req = a.login_token, a._request
    _stub_login("TOKREV")
    a._request = lambda base, method, path, **kw: (500, "boom")   # logout FAILED
    try:
        h, note = a.build_credential({"kind": "revoked_token"}, LOCAL, "s")
    finally:
        a.login_token, a._request = orig_login, orig_req
    assert h is None, "failed logout must NOT report success with a live token"
    assert "logout failed" in note and "not revoked" in note


def test_build_credential_revoked_transient_logout_fails_closed():
    orig_login, orig_req = a.login_token, a._request
    _stub_login("TOKREV")
    a._request = lambda base, method, path, **kw: (a.TRANSIENT_STATUS, "")
    try:
        h, note = a.build_credential({"kind": "revoked_token"}, LOCAL, "s")
    finally:
        a.login_token, a._request = orig_login, orig_req
    assert h is None and "not revoked" in note


# --- login_token ------------------------------------------------------------
def test_login_token_success():
    orig = a._request
    a._request = lambda base, method, path, **kw: (200, '{"accessToken": "JWT"}')
    try:
        assert a.login_token(LOCAL) == "JWT"
    finally:
        a._request = orig


def test_login_token_non_200_returns_none():
    orig = a._request
    a._request = lambda base, method, path, **kw: (401, "nope")
    try:
        assert a.login_token(LOCAL) is None
    finally:
        a._request = orig


def test_login_token_bad_json_returns_none():
    orig = a._request
    a._request = lambda base, method, path, **kw: (200, "not-json")
    try:
        assert a.login_token(LOCAL) is None
    finally:
        a._request = orig


def test_login_token_missing_token_returns_none():
    orig = a._request
    a._request = lambda base, method, path, **kw: (200, '{"other": 1}')
    try:
        assert a.login_token(LOCAL) is None
    finally:
        a._request = orig


# --- iter_subtests / iter_not_applicable ------------------------------------
def test_iter_subtests_canonical():
    rows = list(a.iter_subtests(a.canonical_plan()))
    assert len(rows) == 5
    labels = [r[1] for r in rows]
    assert labels == ["valid", "missing", "malformed", "expired", "revoked"]


def test_iter_subtests_skips_unimplemented_and_labelless():
    plan = {"schemes": [
        {"scheme": "x", "implemented": False, "subtests": [{"label": "a"}]},
        {"scheme": "y", "subtests": [{"label": ""}, {"label": "ok"}]},
    ]}
    rows = list(a.iter_subtests(plan))
    assert rows == [("y", "ok", {}, "401")]     # default expected for non-valid


def test_iter_subtests_default_expected_for_valid():
    plan = {"schemes": [{"scheme": "y", "subtests": [{"label": "valid"}]}]}
    assert list(a.iter_subtests(plan)) == [("y", "valid", {}, "2xx")]


def test_iter_subtests_tolerates_none_and_empty():
    assert list(a.iter_subtests(None)) == []      # type: ignore[arg-type]
    assert list(a.iter_subtests({})) == []


def test_iter_subtests_tolerates_non_dict_plan_and_entries():
    # non-dict plan -> no crash, empty (adversarial-input)
    for bad in (["schemes"], "a string", 42):
        assert list(a.iter_subtests(bad)) == []   # type: ignore[arg-type]
    # non-dict scheme / sub-test entries are skipped, valid ones still yielded
    plan = {"schemes": ["bad", {"scheme": "y", "subtests": ["bad", {"label": "valid"}]}]}
    assert list(a.iter_subtests(plan)) == [("y", "valid", {}, "2xx")]


def test_iter_not_applicable_canonical():
    rows = list(a.iter_not_applicable(a.canonical_plan()))
    assert len(rows) == len(a.NOT_APPLICABLE)
    ids = [r[0] for r in rows]
    assert "apiKey" in ids and "dedicated_revoke_endpoint" in ids
    assert all(s == "needs_to_be_built_and_tested" for _, s in rows)


def test_iter_not_applicable_tolerates_empty():
    assert list(a.iter_not_applicable(None)) == []   # type: ignore[arg-type]
    assert list(a.iter_not_applicable({})) == []


def test_iter_not_applicable_tolerates_non_dict():
    for bad in (["x"], "str", 7):
        assert list(a.iter_not_applicable(bad)) == []   # type: ignore[arg-type]
    plan = {"not_applicable": ["bad", {"item": "apiKey", "status": "s"}]}
    assert list(a.iter_not_applicable(plan)) == [("apiKey", "s")]


def test_build_credential_non_dict_recipe_fails_closed():
    for bad in (["kind"], "valid_token", 5):
        h, note = a.build_credential(bad, LOCAL, "s")   # type: ignore[arg-type]
        assert h is None and "invalid recipe" in note   # no AttributeError


def test_default_expected():
    assert a._default_expected("valid") == "2xx"
    assert a._default_expected("missing") == "401"
    assert a._default_expected("anything-else") == "401"


def main() -> int:
    tests = [v for k, v in sorted(globals().items())
             if k.startswith("test_") and callable(v)]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001 — surface unexpected errors as failures
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
