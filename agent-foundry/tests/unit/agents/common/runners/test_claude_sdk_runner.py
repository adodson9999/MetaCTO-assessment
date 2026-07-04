#!/usr/bin/env python3
"""Unit tests for agents/common/runners/claude_sdk_runner.py — the Claude Agent SDK runner.

Covers the whole invoke WORKFLOW and every guard, with NO real network or model
calls (the native SDK and the HTTP layer are monkeypatched):

  * build_invoker returns a callable and preserves the public signature;
  * _guard_message rejects non-str renders and oversized briefs (adversarial-input);
  * _http_post_once parses a good response and raises a typed ValueError on a
    malformed one (short/garbled JSON);
  * _openai_compat retries transient faults with backoff, does NOT retry a
    malformed response, and raises after exhausting attempts (network / resilience);
  * invoke dispatch: native success on kind=anthropic, native-unavailable
    (ImportError / timeout / connection down / malformed) falls back to the local
    endpoint, and a total (native + fallback) failure is RAISED not silently
    returned as empty (chaos / error-handling / api-contract);
  * a non-anthropic backend skips the native path entirely;
  * event-loop REUSE across invoke() calls (one Runner, not one per call);
  * the exact OpenAI request-body schema is emitted (system+user, temp 0, json);
  * the HTTP response is byte-capped (device-stack);
  * the native circuit breaker trips after N consecutive failures and skips the
    native path (chaos), and resets on a native success;
  * _NativeChannel is thread-safe (one Runner under concurrent call) and closes
    its loop on finalize (memory-resource / concurrency);
  * the SSRF guard refuses a non-local base_url before any request (security);
  * per-(backend,status) metrics count native/fallback success+failure, the
    snapshot is an immutable copy, incr is thread-safe, and _span emits a timed
    trace line + records the outcome and re-raises (observability);
  * exact-boundary coverage of both size caps: a message / response of EXACTLY the
    cap is accepted and one byte over is rejected, pinning the strict '>' threshold
    against an off-by-one slip to '>=' (adversarial-input / device-stack).

Run: agent-foundry/.venv/bin/python \
     agent-foundry/tests/unit/agents/common/runners/test_claude_sdk_runner.py
"""
from __future__ import annotations

import asyncio
import inspect
import json
import sys
import weakref
from pathlib import Path
from time import sleep as _sleep  # real sleep, immune to module-level time.sleep patching

WS = Path(__file__).resolve().parents[5]  # agent-foundry
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

from runners import claude_sdk_runner as r  # noqa: E402


# --- test doubles -----------------------------------------------------------
_ANTHROPIC_SPEC = {
    "provider": "claude-haiku",
    "openai_compatible": True,
    "base_url": "http://127.0.0.1:4000/v1",
    "model": "claude-haiku-4-5",
    "api_key_env": "ANTHROPIC_API_KEY",
    "native": {"kind": "anthropic", "model": "claude-haiku-4-5"},
    "air_gapped": False,
}
_OLLAMA_SPEC = {
    "provider": "ollama",
    "openai_compatible": True,
    "base_url": "http://127.0.0.1:11434/v1",
    "model": "qwen2.5:14b-instruct",
    "api_key_env": "OLLAMA_API_KEY",
    "native": {"kind": "ollama", "model": "qwen2.5:14b-instruct"},
    "air_gapped": True,
}


def _patch_spec(spec: dict):
    """Force resolve_backend to return *spec* (no real backend resolution)."""
    orig = r.resolve_backend
    r.resolve_backend = lambda ws: dict(spec)
    return orig


def _completion_bytes(content: str) -> bytes:
    return json.dumps({"choices": [{"message": {"content": content}}]}).encode()


class _FakeResp:
    """Minimal urlopen context-manager stand-in (no real socket)."""

    def __init__(self, payload: bytes):
        self._payload = payload

    def __enter__(self):
        return self

    def __exit__(self, *a):
        return False

    def read(self, amt=None):
        # urlopen response.read(n) is called with a byte cap; honor it so the
        # runner's device-stack size guard can be exercised.
        return self._payload if amt is None else self._payload[:amt]


# --- build_invoker / public API ---------------------------------------------
def test_build_invoker_returns_callable_and_signature():
    orig = _patch_spec(_OLLAMA_SPEC)
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        assert callable(inv)
        sig = inspect.signature(r.build_invoker)
        assert list(sig.parameters) == ["ws", "system", "user_message_fn"]
    finally:
        r.resolve_backend = orig


# --- _guard_message ---------------------------------------------------------
def test_guard_message_passes_normal():
    assert r._guard_message("hi", lambda b: f"msg:{b}") == "msg:hi"


def test_guard_message_rejects_non_str():
    try:
        r._guard_message("hi", lambda b: 123)  # type: ignore[return-value]
        assert False, "expected ValueError for non-str render"
    except ValueError:
        pass


def test_guard_message_rejects_oversized():
    big = "x" * (r._MAX_MESSAGE_BYTES + 1)
    try:
        r._guard_message("hi", lambda b: big)
        assert False, "expected ValueError for oversized message"
    except ValueError:
        pass


def test_guard_message_accepts_exactly_at_limit():
    # Boundary: the cap is a strict '>' so a message of EXACTLY _MAX_MESSAGE_BYTES
    # (single-byte ASCII => byte-len == char-len) must be accepted, not rejected.
    at_limit = "x" * r._MAX_MESSAGE_BYTES
    assert len(at_limit.encode("utf-8")) == r._MAX_MESSAGE_BYTES  # guard the premise
    assert r._guard_message("brief", lambda b: at_limit) == at_limit


def test_guard_message_rejects_one_over_limit():
    # Boundary companion: one byte over the cap must fail — pins the '>' behavior
    # from the exactly-at-limit side so an off-by-one to '>=' is caught.
    over = "x" * (r._MAX_MESSAGE_BYTES + 1)
    try:
        r._guard_message("brief", lambda b: over)
        assert False, "expected ValueError one byte over the cap"
    except ValueError:
        pass


# --- _http_post_once --------------------------------------------------------
def test_http_post_once_parses_good_response():
    orig = r.urllib.request.urlopen
    r.urllib.request.urlopen = lambda req, timeout=None: _FakeResp(_completion_bytes("OK"))
    try:
        assert r._http_post_once("http://127.0.0.1:11434/v1/chat/completions", b"{}") == "OK"
    finally:
        r.urllib.request.urlopen = orig


def test_http_post_once_raises_on_malformed():
    orig = r.urllib.request.urlopen
    r.urllib.request.urlopen = lambda req, timeout=None: _FakeResp(b"{ not json")
    try:
        r._http_post_once("http://127.0.0.1:11434/v1/chat/completions", b"{}")
        assert False, "expected ValueError on malformed JSON"
    except ValueError:
        pass
    finally:
        r.urllib.request.urlopen = orig


def test_http_post_once_raises_on_missing_keys():
    orig = r.urllib.request.urlopen
    r.urllib.request.urlopen = lambda req, timeout=None: _FakeResp(b'{"choices": []}')
    try:
        r._http_post_once("http://127.0.0.1:11434/v1/chat/completions", b"{}")
        assert False, "expected ValueError on missing choices[0]"
    except ValueError:
        pass
    finally:
        r.urllib.request.urlopen = orig


# --- _openai_compat retry/backoff -------------------------------------------
def test_openai_compat_success_first_try():
    orig = r._http_post_once
    r._http_post_once = lambda url, body: "GOOD"
    try:
        assert r._openai_compat(_OLLAMA_SPEC, "sys", "msg") == "GOOD"
    finally:
        r._http_post_once = orig


def test_openai_compat_retries_transient_then_succeeds():
    calls = {"n": 0}
    orig_post, orig_sleep = r._http_post_once, r.time.sleep

    def flaky(url, body):
        calls["n"] += 1
        if calls["n"] < 2:
            raise r.urllib.error.URLError("connection refused")
        return "RECOVERED"

    r._http_post_once = flaky
    r.time.sleep = lambda s: None  # no real backoff wait
    try:
        assert r._openai_compat(_OLLAMA_SPEC, "sys", "msg") == "RECOVERED"
        assert calls["n"] == 2
    finally:
        r._http_post_once, r.time.sleep = orig_post, orig_sleep


def test_openai_compat_does_not_retry_malformed():
    calls = {"n": 0}
    orig = r._http_post_once

    def bad(url, body):
        calls["n"] += 1
        raise ValueError("malformed completion response")

    r._http_post_once = bad
    try:
        try:
            r._openai_compat(_OLLAMA_SPEC, "sys", "msg")
            assert False, "expected ValueError to propagate"
        except ValueError:
            pass
        assert calls["n"] == 1  # NOT retried
    finally:
        r._http_post_once = orig


def test_openai_compat_raises_after_exhausting_retries():
    orig_post, orig_sleep = r._http_post_once, r.time.sleep

    def always_down(url, body):
        raise r.urllib.error.URLError("down")

    r._http_post_once = always_down
    r.time.sleep = lambda s: None
    try:
        try:
            r._openai_compat(_OLLAMA_SPEC, "sys", "msg")
            assert False, "expected RuntimeError after retries exhausted"
        except RuntimeError:
            pass
    finally:
        r._http_post_once, r.time.sleep = orig_post, orig_sleep


# --- invoke dispatch: native success ----------------------------------------
def test_invoke_native_success():
    orig_spec = _patch_spec(_ANTHROPIC_SPEC)
    orig_native = r._native_call

    async def fake_native(system, model, message):
        return f"NATIVE:{message}"

    r._native_call = fake_native
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        assert inv("brief") == "NATIVE:brief"
    finally:
        r.resolve_backend = orig_spec
        r._native_call = orig_native


# --- invoke dispatch: fallback paths ----------------------------------------
def _run_fallback_case(native_exc: BaseException) -> str:
    """Drive invoke() with a native path that raises *native_exc*, and a stubbed
    HTTP fallback returning a sentinel. Returns the invoke() result."""
    orig_spec = _patch_spec(_ANTHROPIC_SPEC)
    orig_native, orig_post = r._native_call, r._http_post_once

    async def boom(system, model, message):
        raise native_exc

    r._native_call = boom
    r._http_post_once = lambda url, body: "FALLBACK"
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        return inv("brief")
    finally:
        r.resolve_backend = orig_spec
        r._native_call, r._http_post_once = orig_native, orig_post


def test_invoke_falls_back_on_sdk_missing():
    assert _run_fallback_case(ImportError("no claude_agent_sdk")) == "FALLBACK"


def test_invoke_falls_back_on_native_timeout():
    # A hung backend surfaces as asyncio.TimeoutError inside the loop -> fallback.
    assert _run_fallback_case(asyncio.TimeoutError()) == "FALLBACK"


def test_invoke_falls_back_on_connection_down():
    assert _run_fallback_case(ConnectionError("refused")) == "FALLBACK"


def test_invoke_propagates_programming_error():
    # A non-availability error (bug) must NOT be masked as a fallback — it
    # propagates so the defect is visible (error-handling / api-contract lens).
    orig_spec = _patch_spec(_ANTHROPIC_SPEC)
    orig_native = r._native_call

    async def boom(system, model, message):
        raise KeyError("spec bug")

    r._native_call = boom
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        try:
            inv("brief")
            assert False, "expected KeyError to propagate (not fall back)"
        except KeyError:
            pass
    finally:
        r.resolve_backend = orig_spec
        r._native_call = orig_native


def test_invoke_total_failure_raises_not_silent():
    # Native unavailable AND fallback down -> invoke RAISES (reported failure),
    # never returns an empty string as a fake success (chaos lens).
    orig_spec = _patch_spec(_ANTHROPIC_SPEC)
    orig_native, orig_post, orig_sleep = r._native_call, r._http_post_once, r.time.sleep

    async def boom(system, model, message):
        raise ConnectionError("cloud down")

    def down(url, body):
        raise r.urllib.error.URLError("local down")

    r._native_call = boom
    r._http_post_once = down
    r.time.sleep = lambda s: None
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        try:
            inv("brief")
            assert False, "expected RuntimeError when both paths fail"
        except RuntimeError:
            pass
    finally:
        r.resolve_backend = orig_spec
        r._native_call, r._http_post_once, r.time.sleep = orig_native, orig_post, orig_sleep


# --- invoke dispatch: non-anthropic skips native ----------------------------
def test_invoke_non_anthropic_uses_http_directly():
    orig_spec = _patch_spec(_OLLAMA_SPEC)
    orig_post = r._http_post_once
    # If native were (wrongly) attempted, it would import the SDK; assert we go
    # straight to HTTP by only stubbing the HTTP layer.
    r._http_post_once = lambda url, body: "OLLAMA_OUT"
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        assert inv("brief") == "OLLAMA_OUT"
    finally:
        r.resolve_backend = orig_spec
        r._http_post_once = orig_post


def test_invoke_guards_oversized_brief_before_any_io():
    # The size guard fires before native/HTTP, so a stub that would explode if
    # called proves no I/O was attempted.
    orig_spec = _patch_spec(_OLLAMA_SPEC)
    orig_post = r._http_post_once

    def must_not_run(url, body):
        raise AssertionError("HTTP called despite oversized guard")

    r._http_post_once = must_not_run
    try:
        inv = r.build_invoker(WS, "sys", lambda b: "x" * (r._MAX_MESSAGE_BYTES + 1))
        try:
            inv("brief")
            assert False, "expected ValueError from oversized guard"
        except ValueError:
            pass
    finally:
        r.resolve_backend = orig_spec
        r._http_post_once = orig_post


# --- native loop reuse ------------------------------------------------------
def test_native_call_collects_chunks():
    # _native_call joins the streamed chunks' .content; drive it on a real loop
    # with a fake async query, no SDK import.
    import types

    class _Msg:
        def __init__(self, c):
            self.content = c

    async def _fake_query(prompt, options):
        for c in ("a", "b", "c"):
            yield _Msg(c)

    fake_sdk = types.ModuleType("claude_agent_sdk")
    fake_sdk.query = _fake_query
    fake_sdk.ClaudeAgentOptions = lambda **kw: kw
    sys.modules["claude_agent_sdk"] = fake_sdk
    try:
        out = asyncio.run(r._native_call("sys", "model", "msg"))
        assert out == "abc"
    finally:
        sys.modules.pop("claude_agent_sdk", None)


# --- request body schema (api-contract / unit-test) -------------------------
def test_openai_compat_emits_expected_request_body():
    captured = {}
    orig = r.urllib.request.urlopen

    def spy(req, timeout=None):
        captured["url"] = req.full_url
        captured["body"] = json.loads(req.data)
        return _FakeResp(_completion_bytes("OK"))

    r.urllib.request.urlopen = spy
    try:
        assert r._openai_compat(_OLLAMA_SPEC, "SYS", "USER") == "OK"
    finally:
        r.urllib.request.urlopen = orig
    body = captured["body"]
    assert captured["url"].endswith("/chat/completions")
    assert body["model"] == _OLLAMA_SPEC["model"]
    assert body["temperature"] == 0 and body["stream"] is False
    assert body["response_format"] == {"type": "json_object"}
    assert body["messages"] == [
        {"role": "system", "content": "SYS"},
        {"role": "user", "content": "USER"},
    ]


# --- device-stack: response byte cap ----------------------------------------
def test_http_post_once_rejects_oversized_response():
    oversized = b"a" * (r._MAX_RESPONSE_BYTES + 10)
    orig = r.urllib.request.urlopen
    r.urllib.request.urlopen = lambda req, timeout=None: _FakeResp(oversized)
    try:
        r._http_post_once("http://127.0.0.1:11434/v1/chat/completions", b"{}")
        assert False, "expected ValueError for oversized response body"
    except ValueError:
        pass
    finally:
        r.urllib.request.urlopen = orig


def _completion_bytes_of_len(total: int) -> bytes:
    """A VALID completion JSON whose encoded length is exactly *total* bytes,
    achieved by padding the message content (all single-byte ASCII)."""
    envelope = _completion_bytes("")            # valid, empty content
    pad = total - len(envelope)
    assert pad >= 0, "requested length smaller than the minimal envelope"
    return _completion_bytes("x" * pad)


def test_http_post_once_accepts_response_exactly_at_limit():
    # Boundary: the cap is a strict '>' (code reads _MAX+1 then rejects len>_MAX),
    # so a body of EXACTLY _MAX_RESPONSE_BYTES must be accepted AND parsed, not
    # rejected — pins the off-by-one from the accept side (device-stack lens).
    at_limit = _completion_bytes_of_len(r._MAX_RESPONSE_BYTES)
    assert len(at_limit) == r._MAX_RESPONSE_BYTES  # guard the premise
    orig = r.urllib.request.urlopen
    r.urllib.request.urlopen = lambda req, timeout=None: _FakeResp(at_limit)
    try:
        out = r._http_post_once("http://127.0.0.1:11434/v1/chat/completions", b"{}")
        assert out == "x" * (r._MAX_RESPONSE_BYTES - len(_completion_bytes("")))
    finally:
        r.urllib.request.urlopen = orig


def test_http_post_once_rejects_one_over_limit_response():
    # Boundary companion: one byte over the cap must fail — with the accept case
    # above this brackets the exact '>' threshold so a slip to '>=' is caught.
    over = b"a" * (r._MAX_RESPONSE_BYTES + 1)
    orig = r.urllib.request.urlopen
    r.urllib.request.urlopen = lambda req, timeout=None: _FakeResp(over)
    try:
        r._http_post_once("http://127.0.0.1:11434/v1/chat/completions", b"{}")
        assert False, "expected ValueError one byte over the response cap"
    except ValueError:
        pass
    finally:
        r.urllib.request.urlopen = orig


# --- security: SSRF guard ---------------------------------------------------
def test_assert_local_url_accepts_loopback():
    r._assert_local_url("http://127.0.0.1:11434/v1/chat/completions")  # must not raise


def test_assert_local_url_rejects_public_host():
    try:
        r._assert_local_url("http://8.8.8.8:80/chat/completions")
        assert False, "expected ValueError refusing non-local host"
    except ValueError:
        pass


def test_openai_compat_refuses_non_local_spec():
    evil = dict(_OLLAMA_SPEC, base_url="http://8.8.8.8:80/v1")
    orig = r._http_post_once
    r._http_post_once = lambda url, body: (_ for _ in ()).throw(AssertionError("dialed non-local host"))
    try:
        try:
            r._openai_compat(evil, "sys", "msg")
            assert False, "expected ValueError before any request"
        except ValueError:
            pass
    finally:
        r._http_post_once = orig


# --- concurrency / memory-resource: _NativeChannel --------------------------
def test_native_channel_reuses_single_runner():
    ch = r._NativeChannel("sys", "model")
    orig = r._run_native
    seen = []
    r._run_native = lambda runner, coro_fn: (seen.append(id(runner)), "OUT")[1]
    try:
        ch.call("m1")
        ch.call("m2")
        assert len(set(seen)) == 1  # SAME runner reused across calls
        assert ch._runner is not None
    finally:
        r._run_native = orig
        ch.close()


def test_native_channel_close_is_idempotent_and_clears():
    ch = r._NativeChannel("sys", "model")
    orig = r._run_native
    r._run_native = lambda runner, coro_fn: "OUT"
    try:
        ch.call("m")
        assert ch._runner is not None
    finally:
        r._run_native = orig
    ch.close()
    assert ch._runner is None
    ch.close()  # second close must not raise


def test_invoke_reuses_loop_across_calls():
    orig_spec = _patch_spec(_ANTHROPIC_SPEC)
    orig_run = r._run_native
    seen = []
    r._run_native = lambda runner, coro_fn: (seen.append(id(runner)), "NATIVE")[1]
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        assert inv("a") == "NATIVE"
        assert inv("b") == "NATIVE"
        assert len(set(seen)) == 1  # one loop reused, not one per invoke()
    finally:
        r.resolve_backend = orig_spec
        r._run_native = orig_run


def test_native_channel_thread_safe_single_runner():
    ch = r._NativeChannel("sys", "model")
    orig = r._run_native
    barrier = __import__("threading").Barrier(8)
    runner_ids = []
    lock = __import__("threading").Lock()

    def slow_run(runner, coro_fn):
        with lock:
            runner_ids.append(id(runner))
        return "OUT"

    r._run_native = slow_run

    def worker():
        barrier.wait()  # maximize the chance both threads hit the check-then-act
        ch.call("m")

    import threading as _t
    threads = [_t.Thread(target=worker) for _ in range(8)]
    try:
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert len(set(runner_ids)) == 1  # exactly one Runner despite the race
    finally:
        r._run_native = orig
        ch.close()


# --- chaos: circuit breaker -------------------------------------------------
def test_circuit_breaker_trips_and_skips_native():
    orig_spec = _patch_spec(_ANTHROPIC_SPEC)
    orig_run, orig_post = r._run_native, r._http_post_once
    native_calls = {"n": 0}

    def failing_native(runner, coro_fn):
        native_calls["n"] += 1
        raise ConnectionError("cloud down")

    r._run_native = failing_native
    r._http_post_once = lambda url, body: "FALLBACK"
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        # Drive enough failures to trip the breaker, then one more call.
        for _ in range(r._NATIVE_FAILURE_THRESHOLD):
            assert inv("x") == "FALLBACK"
        tripped_at = native_calls["n"]
        assert inv("x") == "FALLBACK"          # breaker open now
        assert native_calls["n"] == tripped_at  # native NOT attempted again
    finally:
        r.resolve_backend = orig_spec
        r._run_native, r._http_post_once = orig_run, orig_post


def test_circuit_breaker_resets_on_success():
    ch = r._NativeChannel("sys", "model")
    orig = r._run_native
    state = {"fail": True}

    def maybe_fail(runner, coro_fn):
        if state["fail"]:
            raise ConnectionError("down")
        return "OK"

    r._run_native = maybe_fail
    try:
        for _ in range(r._NATIVE_FAILURE_THRESHOLD - 1):
            try:
                ch.call("x")
            except ConnectionError:
                pass
        assert ch._consecutive_failures == r._NATIVE_FAILURE_THRESHOLD - 1
        state["fail"] = False
        assert ch.call("x") == "OK"
        assert ch._consecutive_failures == 0  # reset on success
        assert ch._open is True
    finally:
        r._run_native = orig
        ch.close()


def test_invoke_finalizer_closes_channel_loop():
    # Building an anthropic invoker registers a weakref.finalize that closes the
    # channel's loop; dropping the invoker must fire it so no FD leaks. We assert
    # a real Runner is closed by driving one native call, then dropping the invoker.
    orig_spec = _patch_spec(_ANTHROPIC_SPEC)
    orig_run = r._run_native
    closed = {"n": 0}
    real_close = r._NativeChannel.close

    def counting_close(self):
        closed["n"] += 1
        return real_close(self)

    r._run_native = lambda runner, coro_fn: "NATIVE"
    r._NativeChannel.close = counting_close
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        assert inv("a") == "NATIVE"
        assert weakref.getweakrefcount(inv) >= 1  # a finalizer holds a weakref
        del inv
        __import__("gc").collect()
        assert closed["n"] >= 1  # finalize ran channel.close()
    finally:
        r.resolve_backend = orig_spec
        r._run_native = orig_run
        r._NativeChannel.close = real_close


# --- user_message_fn faults (unit-test round-3) -----------------------------
def test_guard_message_propagates_user_fn_exception():
    # A user_message_fn that itself raises must propagate (it is caller code, not
    # an availability fault) — never be masked as an empty/fallback result.
    def boom(_b):
        raise RuntimeError("render failed")

    try:
        r._guard_message("hi", boom)
        assert False, "expected the user_message_fn error to propagate"
    except RuntimeError:
        pass


def test_invoke_propagates_user_fn_exception_no_io():
    # invoke() must surface a raising user_message_fn before any native/HTTP I/O.
    orig_spec = _patch_spec(_ANTHROPIC_SPEC)
    orig_post, orig_run = r._http_post_once, r._run_native
    r._http_post_once = lambda url, body: (_ for _ in ()).throw(AssertionError("HTTP hit"))
    r._run_native = lambda runner, coro_fn: (_ for _ in ()).throw(AssertionError("native hit"))

    def boom(_b):
        raise KeyError("bad brief field")

    try:
        inv = r.build_invoker(WS, "sys", boom)
        try:
            inv("brief")
            assert False, "expected user_message_fn KeyError to propagate"
        except KeyError:
            pass
    finally:
        r.resolve_backend = orig_spec
        r._http_post_once, r._run_native = orig_post, orig_run


def test_openai_compat_accepts_request_id_and_is_optional():
    # The correlation-id param is optional (API-preserving) and does not alter output.
    orig = r._http_post_once
    r._http_post_once = lambda url, body: "OK"
    try:
        assert r._openai_compat(_OLLAMA_SPEC, "s", "m") == "OK"                  # default rid
        assert r._openai_compat(_OLLAMA_SPEC, "s", "m", request_id="abc123") == "OK"
    finally:
        r._http_post_once = orig


def test_invoke_stamps_correlation_id_in_logs():
    # Every log line from one invoke() carries a single [rid=...] token so a
    # failed invocation is traceable end-to-end (observability lens).
    import logging as _logging

    orig_spec = _patch_spec(_ANTHROPIC_SPEC)
    orig_run, orig_post, orig_sleep = r._run_native, r._http_post_once, r.time.sleep
    r._run_native = lambda runner, coro_fn: (_ for _ in ()).throw(ConnectionError("down"))
    r._http_post_once = lambda url, body: "FALLBACK"
    r.time.sleep = lambda s: None

    records = []
    handler = _logging.Handler()
    handler.emit = lambda rec: records.append(rec.getMessage())
    r.log.addHandler(handler)
    prev_level = r.log.level
    r.log.setLevel(_logging.DEBUG)
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        assert inv("brief") == "FALLBACK"
    finally:
        r.log.removeHandler(handler)
        r.log.setLevel(prev_level)
        r.resolve_backend = orig_spec
        r._run_native, r._http_post_once, r.time.sleep = orig_run, orig_post, orig_sleep

    rid_lines = [m for m in records if "[rid=" in m]
    assert rid_lines, "expected at least one correlation-stamped log line"
    rids = {m.split("[rid=", 1)[1].split("]", 1)[0] for m in rid_lines}
    assert len(rids) == 1  # one id shared across this invocation's fallback + retry logs


def test_native_channel_run_serialized_under_lock():
    # asyncio.Runner is not thread-safe: _run_native must never execute
    # concurrently. We assert the lock is HELD for the whole call by checking no
    # two _run_native bodies overlap under contention.
    ch = r._NativeChannel("sys", "model")
    orig = r._run_native
    import threading as _t
    active = {"n": 0}
    overlap = {"seen": False}
    guard = _t.Lock()

    def busy_run(runner, coro_fn):
        with guard:
            active["n"] += 1
            if active["n"] > 1:
                overlap["seen"] = True
        _sleep(0.005)  # widen the window an unlocked impl would overlap in
        with guard:
            active["n"] -= 1
        return "OUT"

    r._run_native = busy_run
    try:
        threads = [_t.Thread(target=lambda: ch.call("m")) for _ in range(6)]
        for th in threads:
            th.start()
        for th in threads:
            th.join()
        assert overlap["seen"] is False  # never two run() bodies at once
    finally:
        r._run_native = orig
        ch.close()


# --- observability: metrics + spans (round-4) -------------------------------
def _reset_metrics():
    # Swap in a fresh counter so each test observes only its own invocations.
    r._METRICS = r._Metrics()


def test_metrics_counts_native_success():
    _reset_metrics()
    orig_spec = _patch_spec(_ANTHROPIC_SPEC)
    orig_run = r._run_native
    r._run_native = lambda runner, coro_fn: "NATIVE"
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        assert inv("brief") == "NATIVE"
        assert r.get_metrics().get((r._BACKEND_NATIVE, r._STATUS_SUCCESS)) == 1
        assert (r._BACKEND_FALLBACK, r._STATUS_SUCCESS) not in r.get_metrics()
    finally:
        r.resolve_backend = orig_spec
        r._run_native = orig_run


def test_metrics_counts_native_failure_then_fallback_success():
    _reset_metrics()
    orig_spec = _patch_spec(_ANTHROPIC_SPEC)
    orig_run, orig_post = r._run_native, r._http_post_once
    r._run_native = lambda runner, coro_fn: (_ for _ in ()).throw(ConnectionError("down"))
    r._http_post_once = lambda url, body: "FALLBACK"
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        assert inv("brief") == "FALLBACK"
        m = r.get_metrics()
        # both a native FAILURE and a fallback SUCCESS must be recorded for one call
        assert m.get((r._BACKEND_NATIVE, r._STATUS_FAILURE)) == 1
        assert m.get((r._BACKEND_FALLBACK, r._STATUS_SUCCESS)) == 1
    finally:
        r.resolve_backend = orig_spec
        r._run_native, r._http_post_once = orig_run, orig_post


def test_metrics_counts_fallback_failure_when_both_down():
    _reset_metrics()
    orig_spec = _patch_spec(_ANTHROPIC_SPEC)
    orig_run, orig_post, orig_sleep = r._run_native, r._http_post_once, r.time.sleep
    r._run_native = lambda runner, coro_fn: (_ for _ in ()).throw(ConnectionError("cloud down"))
    r._http_post_once = lambda url, body: (_ for _ in ()).throw(r.urllib.error.URLError("local down"))
    r.time.sleep = lambda s: None
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        try:
            inv("brief")
            assert False, "expected RuntimeError when both paths fail"
        except RuntimeError:
            pass
        m = r.get_metrics()
        assert m.get((r._BACKEND_NATIVE, r._STATUS_FAILURE)) == 1
        assert m.get((r._BACKEND_FALLBACK, r._STATUS_FAILURE)) == 1
    finally:
        r.resolve_backend = orig_spec
        r._run_native, r._http_post_once, r.time.sleep = orig_run, orig_post, orig_sleep


def test_metrics_counts_ollama_fallback_success():
    _reset_metrics()
    orig_spec = _patch_spec(_OLLAMA_SPEC)
    orig_post = r._http_post_once
    r._http_post_once = lambda url, body: "OLLAMA"
    try:
        inv = r.build_invoker(WS, "sys", lambda b: b)
        assert inv("brief") == "OLLAMA"
        # non-anthropic goes straight through the fallback span
        assert r.get_metrics().get((r._BACKEND_FALLBACK, r._STATUS_SUCCESS)) == 1
    finally:
        r.resolve_backend = orig_spec
        r._http_post_once = orig_post


def test_get_metrics_snapshot_is_immutable_copy():
    _reset_metrics()
    r._METRICS.incr(r._BACKEND_NATIVE, r._STATUS_SUCCESS)
    snap = r.get_metrics()
    snap[("tampered", "x")] = 999  # mutating the copy must not affect the store
    assert ("tampered", "x") not in r.get_metrics()


def test_metrics_incr_is_thread_safe():
    _reset_metrics()
    import threading as _t
    n_threads, per = 8, 200

    def worker():
        for _ in range(per):
            r._METRICS.incr(r._BACKEND_NATIVE, r._STATUS_SUCCESS)

    threads = [_t.Thread(target=worker) for _ in range(n_threads)]
    for th in threads:
        th.start()
    for th in threads:
        th.join()
    assert r.get_metrics()[(r._BACKEND_NATIVE, r._STATUS_SUCCESS)] == n_threads * per


def test_span_emits_timed_success_and_records_metric():
    _reset_metrics()
    import logging as _logging
    records = []
    handler = _logging.Handler()
    handler.emit = lambda rec: records.append(rec.getMessage())
    r.log.addHandler(handler)
    prev = r.log.level
    r.log.setLevel(_logging.DEBUG)
    try:
        with r._span("unit_span", "rid123", r._BACKEND_NATIVE):
            pass
    finally:
        r.log.removeHandler(handler)
        r.log.setLevel(prev)
    end_lines = [m for m in records if "span end: unit_span" in m and "status=success" in m]
    assert end_lines and "ms=" in end_lines[0] and "rid=rid123" in end_lines[0]
    assert r.get_metrics().get((r._BACKEND_NATIVE, r._STATUS_SUCCESS)) == 1


def test_span_records_failure_and_reraises():
    _reset_metrics()
    try:
        with r._span("unit_span", "rid9", r._BACKEND_FALLBACK):
            raise ValueError("boom")
        assert False, "span must re-raise, not swallow"
    except ValueError:
        pass
    assert r.get_metrics().get((r._BACKEND_FALLBACK, r._STATUS_FAILURE)) == 1


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t()
            print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1
            print(f"FAIL  {t.__name__}: {e}")
        except Exception as e:  # noqa: BLE001 - surface unexpected errors as failures
            failed += 1
            print(f"FAIL  {t.__name__}: unexpected {e.__class__.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
