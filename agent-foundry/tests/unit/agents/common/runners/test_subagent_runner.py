#!/usr/bin/env python3
"""Unit tests for agents/common/runners/subagent_runner.py — the Claude Code
subagent framework adapter.

Covers the whole build_invoker -> invoke WORKFLOW and every hardening property,
with NO real network / model / subprocess calls (all three I/O boundaries are
stubbed):

  * backend selection: the CLI path is taken only for an ``anthropic`` backend
    with ``claude`` on PATH; otherwise the local endpoint is used;
  * fallback logic: a FAILED CLI (None) falls through to local, but a SUCCESSFUL
    empty CLI reply ("") is returned verbatim (the logic/math-correctness bug);
  * CLI failure paths: wrong backend, missing binary, non-zero exit, timeout, and
    spawn OSError all degrade to None without raising;
  * KeyboardInterrupt / SystemExit propagate (never swallowed into a fallback);
  * local endpoint: correct request construction, JSON parse, bounded retry on
    transient faults, no-retry on malformed body / 4xx, response byte cap, and the
    non-http base_url guard;
  * total-outage: when both backends fail, invoke raises BackendUnavailable;
  * adversarial-input: oversize system/brief AND a non-UTF-8 response body are
    handled without crashing;
  * performance: user_message_fn is evaluated exactly once per invoke, even when
    the CLI fails and the local endpoint retries;
  * network: retry backoff is jittered (randomized), not lockstep;
  * subprocess contract: run() is called with the correct timeout/cwd/capture
    flags so a dropped safety kwarg is caught;
  * observability: a per-invoke correlation id appears in the emitted log lines.

Run: agent-foundry/.venv/bin/python \
       agent-foundry/tests/unit/agents/common/runners/test_subagent_runner.py
"""
from __future__ import annotations

import io
import logging
import subprocess
import sys
import urllib.error
from pathlib import Path
from typing import Optional, Union

WS = Path(__file__).resolve().parents[5]  # agent-foundry
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

from runners import subagent_runner as sr  # noqa: E402
from runners.subagent_runner import BackendUnavailable, build_invoker  # noqa: E402

_OLLAMA_SPEC = {
    "provider": "ollama", "openai_compatible": True,
    "base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5:14b-instruct",
    "api_key_env": "OLLAMA_API_KEY", "native": {"kind": "ollama", "model": "qwen2.5:14b-instruct"},
    "air_gapped": True,
}
_ANTHROPIC_SPEC = {
    "provider": "claude-haiku", "openai_compatible": True,
    "base_url": "http://127.0.0.1:4000/v1", "model": "claude-haiku-4-5",
    "api_key_env": "ANTHROPIC_API_KEY", "native": {"kind": "anthropic", "model": "claude-haiku-4-5"},
    "air_gapped": False,
}


class _FakeTime:
    """Deterministic stand-in for the ``time`` module: no real sleeping, and a monotonic() that
    advances by a fixed step per call so latency spans compute finite, positive values."""

    def __init__(self) -> None:
        self._t = 0.0

    def sleep(self, seconds: float) -> None:  # never actually sleep in tests
        return None

    def monotonic(self) -> float:
        self._t += 0.001  # 1 ms per read -> spans report ~1 ms, never zero/negative
        return self._t


class _Restore:
    """Snapshot + restore the module attributes each test stubs (no real I/O)."""

    _NAMES = ("resolve_backend", "shutil", "subprocess", "time", "random")

    def __enter__(self) -> "_Restore":
        self._saved = {n: getattr(sr, n) for n in self._NAMES}
        self._saved["urlopen"] = sr.urllib.request.urlopen
        # Neutralize real sleeping + randomness for every test by default; tests that assert on
        # jitter re-stub sr.random / sr.time explicitly.
        sr.time = _FakeTime()
        return self

    def __exit__(self, *exc) -> None:
        for n, v in self._saved.items():
            if n == "urlopen":
                sr.urllib.request.urlopen = v
            else:
                setattr(sr, n, v)


def _stub_backend(spec: dict) -> None:
    sr.resolve_backend = lambda ws: spec


class _FakeShutil:
    def __init__(self, present: bool) -> None:
        self._present = present

    def which(self, name: str) -> Optional[str]:
        return "/usr/bin/claude" if self._present else None


class _FakeCompleted:
    def __init__(self, returncode: int, stdout: str = "", stderr: str = "") -> None:
        self.returncode, self.stdout, self.stderr = returncode, stdout, stderr


class _FakeSubprocess:
    """Stand-in for the ``subprocess`` module used inside the runner."""

    TimeoutExpired = subprocess.TimeoutExpired

    def __init__(self, result=None, raises: Optional[BaseException] = None) -> None:
        self._result, self._raises = result, raises
        self.calls: list = []

    def run(self, argv, **kwargs):
        self.calls.append((argv, kwargs))
        if self._raises is not None:
            raise self._raises
        return self._result


def _http_response(text: Union[str, bytes]):
    raw = text.encode("utf-8") if isinstance(text, str) else text

    class _Resp:
        def __enter__(self_):
            return self_

        def __exit__(self_, *a):
            return False

        def read(self_, n: int = -1) -> bytes:
            # Honor the runner's capped read(n) so the byte-cap path is exercised realistically.
            return raw if n is None or n < 0 else raw[:n]

    return _Resp()


def _ok_body(content: str = "LOCAL OK") -> str:
    import json
    return json.dumps({"choices": [{"message": {"content": content}}]})


def _user_message(brief: str) -> str:
    return f"USER::{brief}"


class _capture_logs:
    """Context manager capturing sr.log messages at DEBUG for observability assertions."""

    def __enter__(self):
        self.messages: list = []

        class _Cap(logging.Handler):
            def emit(handler_self, record):
                self.messages.append(record.getMessage())

        self._handler = _Cap()
        self._old_level = sr.log.level
        sr.log.addHandler(self._handler)
        sr.log.setLevel(logging.DEBUG)
        return self

    def __exit__(self, *exc):
        sr.log.removeHandler(self._handler)
        sr.log.setLevel(self._old_level)
        return False


# --- backend selection ------------------------------------------------------
def test_local_used_when_not_anthropic():
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=True)  # even with claude present...
        captured = {}

        def fake_urlopen(req, timeout=None):
            captured["url"] = req.full_url
            captured["timeout"] = timeout
            return _http_response(_ok_body("FROM LOCAL"))

        sr.urllib.request.urlopen = fake_urlopen
        invoke = build_invoker(WS, "SYS", _user_message)
        assert invoke("b1") == "FROM LOCAL"                       # ...ollama backend -> local path
        assert captured["url"] == "http://127.0.0.1:11434/v1/chat/completions"
        assert captured["timeout"] == sr._HTTP_TIMEOUT_S


def test_cli_used_when_anthropic_and_claude_present():
    with _Restore():
        _stub_backend(_ANTHROPIC_SPEC)
        sr.shutil = _FakeShutil(present=True)
        fake = _FakeSubprocess(result=_FakeCompleted(0, stdout="FROM CLI"))
        sr.subprocess = fake
        invoke = build_invoker(WS, "SYS", _user_message)
        assert invoke("b2") == "FROM CLI"
        argv, kwargs = fake.calls[0]
        assert argv[0] == "claude" and "--output-format" in argv and "text" in argv
        assert "SYS" in argv[2] and "USER::b2" in argv[2]         # system + user message embedded
        # subprocess safety contract: a dropped timeout / capture / cwd / text kwarg is a real
        # regression, so assert each explicitly (unit-test lens).
        assert kwargs["timeout"] == sr._CLI_TIMEOUT_S
        assert kwargs["capture_output"] is True and kwargs["text"] is True
        assert kwargs["cwd"] == str(WS)


def test_cli_skipped_when_claude_missing():
    with _Restore():
        _stub_backend(_ANTHROPIC_SPEC)
        sr.shutil = _FakeShutil(present=False)                    # binary absent -> skip CLI
        sr.urllib.request.urlopen = lambda req, timeout=None: _http_response(_ok_body("LOCAL FALLBACK"))
        invoke = build_invoker(WS, "SYS", _user_message)
        assert invoke("b3") == "LOCAL FALLBACK"


# --- fallback / empty-string logic (the flagged bug) ------------------------
def test_empty_cli_output_returned_not_fallback():
    # Successful CLI with EMPTY stdout must be returned verbatim, NOT treated as failure.
    with _Restore():
        _stub_backend(_ANTHROPIC_SPEC)
        sr.shutil = _FakeShutil(present=True)
        sr.subprocess = _FakeSubprocess(result=_FakeCompleted(0, stdout=""))

        def _boom(req, timeout=None):
            raise AssertionError("local path must NOT be reached on empty-but-successful CLI")

        sr.urllib.request.urlopen = _boom
        invoke = build_invoker(WS, "SYS", _user_message)
        assert invoke("b4") == ""


def test_cli_nonzero_exit_falls_back_to_local():
    with _Restore():
        _stub_backend(_ANTHROPIC_SPEC)
        sr.shutil = _FakeShutil(present=True)
        sr.subprocess = _FakeSubprocess(result=_FakeCompleted(1, stdout="", stderr="explode"))
        sr.urllib.request.urlopen = lambda req, timeout=None: _http_response(_ok_body("AFTER CLI FAIL"))
        invoke = build_invoker(WS, "SYS", _user_message)
        assert invoke("b5") == "AFTER CLI FAIL"


def test_cli_timeout_falls_back_to_local():
    with _Restore():
        _stub_backend(_ANTHROPIC_SPEC)
        sr.shutil = _FakeShutil(present=True)
        sr.subprocess = _FakeSubprocess(raises=subprocess.TimeoutExpired(cmd="claude", timeout=1))
        sr.urllib.request.urlopen = lambda req, timeout=None: _http_response(_ok_body("AFTER TIMEOUT"))
        invoke = build_invoker(WS, "SYS", _user_message)
        assert invoke("b6") == "AFTER TIMEOUT"


def test_cli_spawn_oserror_falls_back_to_local():
    with _Restore():
        _stub_backend(_ANTHROPIC_SPEC)
        sr.shutil = _FakeShutil(present=True)
        sr.subprocess = _FakeSubprocess(raises=OSError("no such binary"))
        sr.urllib.request.urlopen = lambda req, timeout=None: _http_response(_ok_body("AFTER OSERROR"))
        invoke = build_invoker(WS, "SYS", _user_message)
        assert invoke("b7") == "AFTER OSERROR"


def test_keyboard_interrupt_from_cli_propagates():
    # A user Ctrl-C during the subprocess must propagate, NOT be masked into a fallback.
    with _Restore():
        _stub_backend(_ANTHROPIC_SPEC)
        sr.shutil = _FakeShutil(present=True)
        sr.subprocess = _FakeSubprocess(raises=KeyboardInterrupt())
        sr.urllib.request.urlopen = lambda req, timeout=None: _http_response(_ok_body("SHOULD NOT RUN"))
        invoke = build_invoker(WS, "SYS", _user_message)
        try:
            invoke("b8")
            assert False, "expected KeyboardInterrupt to propagate"
        except KeyboardInterrupt:
            pass


# --- local endpoint: request construction + parsing -------------------------
def test_local_request_payload_shape():
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        seen = {}

        def fake_urlopen(req, timeout=None):
            import json
            seen["payload"] = json.loads(req.data.decode("utf-8"))
            seen["ctype"] = req.headers.get("Content-type")
            return _http_response(_ok_body("OK"))

        sr.urllib.request.urlopen = fake_urlopen
        invoke = build_invoker(WS, "SYSPROMPT", _user_message)
        assert invoke("bb") == "OK"
        p = seen["payload"]
        assert p["model"] == "qwen2.5:14b-instruct" and p["temperature"] == 0 and p["stream"] is False
        assert p["messages"][0] == {"role": "system", "content": "SYSPROMPT"}
        assert p["messages"][1] == {"role": "user", "content": "USER::bb"}
        assert p["response_format"] == {"type": "json_object"}    # default
        assert seen["ctype"] == "application/json"


def test_response_format_none_omits_key():
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        seen = {}

        def fake_urlopen(req, timeout=None):
            import json
            seen["payload"] = json.loads(req.data.decode("utf-8"))
            return _http_response(_ok_body("OK"))

        sr.urllib.request.urlopen = fake_urlopen
        invoke = build_invoker(WS, "SYS", _user_message, response_format=None)
        assert invoke("cc") == "OK"
        assert "response_format" not in seen["payload"]           # array agents must not constrain


# --- local endpoint: resilience --------------------------------------------
def test_local_retries_transient_then_succeeds():
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        state = {"n": 0}

        def flaky_urlopen(req, timeout=None):
            state["n"] += 1
            if state["n"] < 3:
                raise urllib.error.URLError("connection refused")
            return _http_response(_ok_body("EVENTUALLY OK"))

        sr.urllib.request.urlopen = flaky_urlopen
        invoke = build_invoker(WS, "SYS", _user_message)
        assert invoke("dd") == "EVENTUALLY OK"
        assert state["n"] == 3                                    # two transient fails, then success


def test_local_transient_exhausts_then_raises_backend_unavailable():
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        state = {"n": 0}

        def always_down(req, timeout=None):
            state["n"] += 1
            raise TimeoutError("read timed out")

        sr.urllib.request.urlopen = always_down
        invoke = build_invoker(WS, "SYS", _user_message)
        try:
            invoke("ee")
            assert False, "expected BackendUnavailable when local exhausts retries"
        except BackendUnavailable:
            pass
        assert state["n"] == sr._LOCAL_ATTEMPTS                   # bounded, not infinite


def test_local_4xx_not_retried():
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        state = {"n": 0}

        def bad_request(req, timeout=None):
            state["n"] += 1
            raise urllib.error.HTTPError(req.full_url, 400, "Bad Request", {}, io.BytesIO(b""))

        sr.urllib.request.urlopen = bad_request
        invoke = build_invoker(WS, "SYS", _user_message)
        try:
            invoke("ff")
            assert False, "expected BackendUnavailable on 4xx"
        except BackendUnavailable:
            pass
        assert state["n"] == 1                                    # permanent -> exactly one attempt


def test_local_5xx_is_retried():
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        state = {"n": 0}

        def server_error(req, timeout=None):
            state["n"] += 1
            raise urllib.error.HTTPError(req.full_url, 503, "Unavailable", {}, io.BytesIO(b""))

        sr.urllib.request.urlopen = server_error
        invoke = build_invoker(WS, "SYS", _user_message)
        try:
            invoke("gg")
            assert False
        except BackendUnavailable:
            pass
        assert state["n"] == sr._LOCAL_ATTEMPTS                   # 5xx is transient -> retried


def test_local_malformed_json_not_retried_and_raises():
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        state = {"n": 0}

        def garbage(req, timeout=None):
            state["n"] += 1
            return _http_response("{ this is not json")

        sr.urllib.request.urlopen = garbage
        invoke = build_invoker(WS, "SYS", _user_message)
        try:
            invoke("hh")
            assert False, "expected BackendUnavailable on unparseable body"
        except BackendUnavailable:
            pass
        assert state["n"] == 1                                    # deterministic -> no retry


def test_local_missing_keys_not_retried_and_raises():
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        sr.urllib.request.urlopen = lambda req, timeout=None: _http_response('{"unexpected": true}')
        invoke = build_invoker(WS, "SYS", _user_message)
        try:
            invoke("ii")
            assert False, "expected BackendUnavailable on missing choices/message keys"
        except BackendUnavailable:
            pass


def test_local_response_byte_cap_enforced():
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        oversize = "x" * (sr._MAX_RESPONSE_BYTES + 100)

        def huge(req, timeout=None):
            return _http_response(_ok_body(oversize))

        sr.urllib.request.urlopen = huge
        invoke = build_invoker(WS, "SYS", _user_message)
        try:
            invoke("jj")
            assert False, "expected BackendUnavailable when body exceeds the byte cap"
        except BackendUnavailable:
            pass


def test_non_http_base_url_refused():
    with _Restore():
        spec = dict(_OLLAMA_SPEC, base_url="file:///etc/passwd")   # SSRF/scheme smuggling guard
        _stub_backend(spec)
        sr.shutil = _FakeShutil(present=False)

        def _boom(req, timeout=None):
            raise AssertionError("urlopen must not be called for a non-http base_url")

        sr.urllib.request.urlopen = _boom
        invoke = build_invoker(WS, "SYS", _user_message)
        try:
            invoke("kk")
            assert False, "expected BackendUnavailable for non-http base_url"
        except BackendUnavailable:
            pass


# --- total outage -----------------------------------------------------------
def test_both_backends_fail_raises_backend_unavailable():
    with _Restore():
        _stub_backend(_ANTHROPIC_SPEC)
        sr.shutil = _FakeShutil(present=True)
        sr.subprocess = _FakeSubprocess(result=_FakeCompleted(1, stderr="cli down"))

        def down(req, timeout=None):
            raise urllib.error.URLError("refused")

        sr.urllib.request.urlopen = down
        invoke = build_invoker(WS, "SYS", _user_message)
        try:
            invoke("ll")
            assert False, "expected BackendUnavailable when CLI and local both fail"
        except BackendUnavailable:
            pass


# --- adversarial input ------------------------------------------------------
def test_oversize_system_and_brief_truncated():
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        seen = {}

        def fake_urlopen(req, timeout=None):
            import json
            seen["payload"] = json.loads(req.data.decode("utf-8"))
            return _http_response(_ok_body("OK"))

        sr.urllib.request.urlopen = fake_urlopen
        big_system = "s" * (sr._MAX_FIELD_BYTES + 10_000)
        invoke = build_invoker(WS, big_system, lambda b: "u" * (sr._MAX_FIELD_BYTES + 10_000))
        assert invoke("mm") == "OK"
        sys_content = seen["payload"]["messages"][0]["content"]
        usr_content = seen["payload"]["messages"][1]["content"]
        assert len(sys_content.encode("utf-8")) <= sr._MAX_FIELD_BYTES
        assert len(usr_content.encode("utf-8")) <= sr._MAX_FIELD_BYTES


def test_bounded_slices_before_encoding_oversize_input():
    # ROOT of the adversarial-input guard: an oversize string must be char-sliced BEFORE encode(),
    # so the full input is NEVER materialized as bytes. A str subclass records every encode() call
    # on the ORIGINAL object; slicing a str returns a plain str, so if the guard slices first the
    # tracked encode() is never invoked with the full length.
    encoded_lengths: list = []

    class _TrackedStr(str):
        def encode(self, *a, **k):
            encoded_lengths.append(len(self))
            return str.encode(self, *a, **k)

    oversize = _TrackedStr("z" * (sr._MAX_FIELD_CHARS + 500_000))
    out = sr._bounded("brief", oversize)
    # The full 1GB-class input's encode() was never called — it was sliced away first.
    assert len(oversize) not in encoded_lengths
    assert all(n <= sr._MAX_FIELD_CHARS for n in encoded_lengths)
    assert len(out) <= sr._MAX_FIELD_CHARS                     # returned the bounded slice
    assert len(out.encode("utf-8")) <= sr._MAX_FIELD_BYTES     # final result honors the byte cap


def test_bounded_multibyte_input_honors_byte_cap():
    # A field made of 3-byte code points at exactly the char ceiling would exceed the BYTE cap
    # after encode; the final byte-level trim must still enforce _MAX_FIELD_BYTES exactly.
    multibyte = "中" * sr._MAX_FIELD_CHARS                  # 'zhong', 3 bytes each in UTF-8
    out = sr._bounded("system", multibyte)
    assert len(out.encode("utf-8")) <= sr._MAX_FIELD_BYTES


def test_non_utf8_response_body_not_retried_and_raises():
    # A backend returning invalid UTF-8 bytes must degrade cleanly (UnicodeDecodeError is
    # deterministic -> no retry -> BackendUnavailable), never crash the caller (adversarial-input).
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        state = {"n": 0}

        def bad_bytes(req, timeout=None):
            state["n"] += 1
            return _http_response(b"\xff\xfe not valid utf-8 \x80")

        sr.urllib.request.urlopen = bad_bytes
        invoke = build_invoker(WS, "SYS", _user_message)
        try:
            invoke("uu")
            assert False, "expected BackendUnavailable on non-UTF-8 body"
        except BackendUnavailable:
            pass
        assert state["n"] == 1                                    # deterministic -> no retry


def test_user_message_fn_called_once_even_on_fallback():
    # Performance: the expensive user_message_fn must be evaluated ONCE per invoke and reused
    # across the CLI attempt and every local retry (not 3-4x).
    with _Restore():
        _stub_backend(_ANTHROPIC_SPEC)                            # CLI path attempted first
        sr.shutil = _FakeShutil(present=True)
        sr.subprocess = _FakeSubprocess(result=_FakeCompleted(1, stderr="cli down"))  # CLI fails
        calls = {"n": 0}

        def counting_um(brief: str) -> str:
            calls["n"] += 1
            return f"UM::{brief}"

        attempts = {"n": 0}

        def flaky(req, timeout=None):
            attempts["n"] += 1
            if attempts["n"] < 2:
                raise urllib.error.URLError("refused")            # force a local retry
            return _http_response(_ok_body("OK"))

        sr.urllib.request.urlopen = flaky
        invoke = build_invoker(WS, "SYS", counting_um)
        assert invoke("zz") == "OK"
        assert attempts["n"] == 2                                 # CLI failed, local retried once
        assert calls["n"] == 1                                    # ...but user_message_fn ran ONCE


def test_backoff_is_jittered_not_lockstep():
    # Network: the retry delay must be randomized (full-jitter), so concurrent callers don't
    # stampede. Assert sr.random is consulted and the slept delay is below the un-jittered base.
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        sr.random = type("R", (), {"random": staticmethod(lambda: 1.0)})()  # max jitter
        slept: list = []
        recording_time = _FakeTime()                              # keep monotonic() for spans...
        recording_time.sleep = lambda s: slept.append(s)          # ...but record backoff sleeps
        sr.time = recording_time
        state = {"n": 0}

        def flaky(req, timeout=None):
            state["n"] += 1
            if state["n"] < 2:
                raise urllib.error.URLError("refused")
            return _http_response(_ok_body("OK"))

        sr.urllib.request.urlopen = flaky
        invoke = build_invoker(WS, "SYS", _user_message)
        assert invoke("jt") == "OK"
        assert len(slept) == 1
        base = sr._LOCAL_BACKOFF_S * 1                            # attempt 1 base
        # random()==1.0 -> delay = base*(1 - jitter*1) = base*(1-0.5) = base/2 < base
        assert 0.0 < slept[0] < base


def test_correlation_id_in_logs():
    # Observability: every log line for one invoke must share a correlation id so a fallback
    # chain is traceable. Capture WARNING logs across a CLI-fail -> local-fail sequence.
    with _Restore():
        _stub_backend(_ANTHROPIC_SPEC)
        sr.shutil = _FakeShutil(present=True)
        sr.subprocess = _FakeSubprocess(result=_FakeCompleted(1, stderr="cli down"))
        sr.urllib.request.urlopen = lambda req, timeout=None: (_ for _ in ()).throw(
            urllib.error.URLError("refused"))

        records: list = []

        class _Cap(logging.Handler):
            def emit(self_, record):
                records.append(record.getMessage())

        handler = _Cap()
        sr.log.addHandler(handler)
        old_level = sr.log.level
        sr.log.setLevel(logging.DEBUG)
        try:
            invoke = build_invoker(WS, "SYS", _user_message)
            try:
                invoke("cidtest")
            except BackendUnavailable:
                pass
        finally:
            sr.log.removeHandler(handler)
            sr.log.setLevel(old_level)

        # Extract the 8-hex correlation id from the first bracketed message and assert every
        # request-scoped line carries the SAME id.
        tagged = [m for m in records if m.startswith("[") and "]" in m[:11]]
        assert tagged, "expected correlation-id-tagged log lines"
        cids = {m[1:m.index("]")] for m in tagged}
        assert len(cids) == 1                                     # one id ties the whole request
        only = next(iter(cids))
        assert len(only) == 8 and all(c in "0123456789abcdef" for c in only)


def test_success_logs_which_backend_answered_with_latency():
    # Observability: a successful invoke must close its span naming the backend that answered AND
    # a total latency, so a healthy request is a complete timed trace (not just failures).
    with _Restore(), _capture_logs() as cap:
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        sr.urllib.request.urlopen = lambda req, timeout=None: _http_response(_ok_body("OK"))
        invoke = build_invoker(WS, "SYS", _user_message)
        assert invoke("ok") == "OK"
    assert any("invoke ok via=local" in m and "total=" in m and "ms" in m for m in cap.messages)
    assert any("local-endpoint ok" in m and "ms" in m for m in cap.messages)   # per-backend latency


def test_total_outage_logs_named_fallback_chain():
    # Observability: the total-outage path must emit a WARNING naming the whole chain that was
    # tried, so the outage is diagnosable from telemetry even if the caller swallows the raise.
    with _Restore(), _capture_logs() as cap:
        _stub_backend(_ANTHROPIC_SPEC)
        sr.shutil = _FakeShutil(present=True)
        sr.subprocess = _FakeSubprocess(result=_FakeCompleted(1, stderr="cli down"))
        sr.urllib.request.urlopen = lambda req, timeout=None: (_ for _ in ()).throw(
            urllib.error.URLError("refused"))
        invoke = build_invoker(WS, "SYS", _user_message)
        try:
            invoke("out")
        except BackendUnavailable:
            pass
    assert any("invoke failed" in m and "via=claude-cli,local" in m and "total=" in m
               for m in cap.messages)


def test_cli_stdout_capped_to_response_limit():
    # adversarial-input ROOT: a runaway/compromised claude CLI writing gigabytes to stdout must be
    # bounded to the shared output cap before being forwarded downstream (memory-resource).
    with _Restore():
        _stub_backend(_ANTHROPIC_SPEC)
        sr.shutil = _FakeShutil(present=True)
        oversize = "z" * (sr._MAX_RESPONSE_BYTES + 100_000)
        sr.subprocess = _FakeSubprocess(result=_FakeCompleted(0, stdout=oversize))
        invoke = build_invoker(WS, "SYS", _user_message)
        out = invoke("big")
        assert len(out.encode("utf-8")) <= sr._MAX_RESPONSE_BYTES   # forwarded output is bounded


def test_cli_success_logs_latency():
    # Observability: a successful CLI call must log a per-backend latency span.
    with _Restore(), _capture_logs() as cap:
        _stub_backend(_ANTHROPIC_SPEC)
        sr.shutil = _FakeShutil(present=True)
        sr.subprocess = _FakeSubprocess(result=_FakeCompleted(0, stdout="HELLO"))
        invoke = build_invoker(WS, "SYS", _user_message)
        assert invoke("x") == "HELLO"
    assert any("claude-cli ok" in m and "ms" in m for m in cap.messages)
    assert any("invoke ok via=claude-cli" in m and "total=" in m for m in cap.messages)


def test_elapsed_ms_uses_monotonic_and_is_nonnegative():
    # Latency helper must be monotonic-based (clock-skew immune) and never negative.
    start = sr.time.monotonic()
    assert sr._elapsed_ms(start) >= 0.0


def test_cap_output_short_value_unchanged():
    assert sr._cap_output("stdout", "cid1234", "tiny") == "tiny"


def test_bounded_returns_short_value_unchanged():
    assert sr._bounded("system", "small") == "small"


def test_default_response_format_uses_immutable_sentinel():
    # api-contract: the default must NOT be a shared mutable dict. Verify the signature default
    # is the module sentinel and that omitting the arg still yields json_object on the wire.
    import inspect
    assert inspect.signature(build_invoker).parameters["response_format"].default is sr._UNSET


def _payload_for(**build_kwargs) -> dict:
    """Drive one local call and capture the request payload (helper for the two contract tests)."""
    _stub_backend(_OLLAMA_SPEC)
    sr.shutil = _FakeShutil(present=False)
    seen: dict = {}

    def fake_urlopen(req, timeout=None):
        import json
        seen["payload"] = json.loads(req.data.decode("utf-8"))
        return _http_response(_ok_body("OK"))

    sr.urllib.request.urlopen = fake_urlopen
    invoke = build_invoker(WS, "SYS", _user_message, **build_kwargs)
    assert invoke("p") == "OK"
    return seen["payload"]


def test_contract_omitted_arg_sends_json_object():
    # BACKWARD-COMPAT: the ~94 dependents that call build_invoker(WS, sys, um) with the arg
    # OMITTED must still get {"type": "json_object"} exactly as before the sentinel change.
    with _Restore():
        assert _payload_for()["response_format"] == {"type": "json_object"}


def test_contract_explicit_none_omits_constraint():
    # BACKWARD-COMPAT: test-case-creator passes response_format=None to DISABLE the constraint
    # (array agent). That must still omit the key entirely, unchanged by the sentinel refactor.
    with _Restore():
        assert "response_format" not in _payload_for(response_format=None)


def test_contract_explicit_dict_sent_verbatim():
    with _Restore():
        rf = {"type": "json_schema", "json_schema": {"name": "x"}}
        assert _payload_for(response_format=rf)["response_format"] == rf


def test_raw_brief_bounded_before_user_message_fn():
    # adversarial-input: an oversize RAW brief must be truncated BEFORE it reaches
    # user_message_fn, so a hostile 1GB+ brief can't exhaust memory inside the template fn.
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        sr.urllib.request.urlopen = lambda req, timeout=None: _http_response(_ok_body("OK"))
        seen = {}

        def um(brief: str) -> str:
            seen["brief_bytes"] = len(brief.encode("utf-8"))
            return "u"

        invoke = build_invoker(WS, "SYS", um)
        assert invoke("b" * (sr._MAX_FIELD_BYTES + 50_000)) == "OK"
        assert seen["brief_bytes"] <= sr._MAX_FIELD_BYTES         # bounded before um saw it


def test_backend_unavailable_is_catchable_as_oserror():
    # api-contract: the ORIGINAL runner propagated a raw URLError (an OSError) on total outage.
    # BackendUnavailable must remain catchable by any existing ``except OSError`` site.
    assert issubclass(BackendUnavailable, OSError)
    with _Restore():
        _stub_backend(_OLLAMA_SPEC)
        sr.shutil = _FakeShutil(present=False)
        sr.urllib.request.urlopen = lambda req, timeout=None: (_ for _ in ()).throw(
            urllib.error.URLError("down"))
        invoke = build_invoker(WS, "SYS", _user_message)
        try:
            invoke("oo")
            assert False, "expected an exception on total outage"
        except OSError:                                            # catches BackendUnavailable
            pass


def test_non_http_base_url_logs_warning():
    # observability: the non-http base_url guard must WARN before raising, so the
    # misconfiguration is diagnosable from logs even if the caller swallows the exception.
    with _Restore():
        _stub_backend(dict(_OLLAMA_SPEC, base_url="file:///etc/passwd"))
        sr.shutil = _FakeShutil(present=False)
        records: list = []

        class _Cap(logging.Handler):
            def emit(self_, record):
                records.append(record.getMessage())

        handler = _Cap()
        sr.log.addHandler(handler)
        old_level = sr.log.level
        sr.log.setLevel(logging.WARNING)
        try:
            invoke = build_invoker(WS, "SYS", _user_message)
            try:
                invoke("ww")
            except BackendUnavailable:
                pass
        finally:
            sr.log.removeHandler(handler)
            sr.log.setLevel(old_level)
        assert any("non-http local base_url" in m for m in records)


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
        except Exception as e:  # noqa: BLE001 - report unexpected errors as failures
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
