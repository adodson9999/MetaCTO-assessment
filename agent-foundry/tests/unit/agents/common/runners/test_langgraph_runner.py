#!/usr/bin/env python3
"""Unit tests for agents/common/runners/langgraph_runner.py — the LangGraph adapter.

Covers every function plus the compiled-graph run WORKFLOW and its hardening
properties, with the backend + every LLM/model client fully STUBBED (no real
network or model calls ever happen):

  * _validate_brief: accepts a normal str, rejects non-str and over-cap payloads
    (adversarial-input);
  * _coerce_content: str passthrough, Anthropic list-of-dicts flattening, None->"",
    other->str (logic-error / math-correctness);
  * _with_retry: returns on first success, retries then succeeds, exhausts the
    bounded budget and re-raises the LAST error (chaos / error-handling / network);
  * _openai_caller: happy path, empty-choices -> ("", None) instead of IndexError
    (math-correctness), timeout wired onto the client + request (network);
  * _anthropic_caller / _ollama_caller: content coercion + usage surfacing gated by
    use_usage, timeout wired (network);
  * _build_call / _build_standard_call / _build_multicaller: correct kind dispatch
    for all three backends, max_tokens + usage plumbing, multicaller anthropic 1024
    default (system-design / maintainability / minimalist);
  * build_invoker: end-to-end run through the real compiled StateGraph with a stub
    call, on_usage callback firing, standard vs multicaller selection, brief-length
    rejection, and a failing call propagating (not silently succeeding).

Run: agent-foundry/.venv/bin/python \
        agent-foundry/tests/unit/agents/common/runners/test_langgraph_runner.py
"""
from __future__ import annotations

import sys
from pathlib import Path
from typing import Any, Optional, Tuple

WS = Path(__file__).resolve().parents[5]  # agent-foundry
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

from runners import langgraph_runner as lr  # noqa: E402

# ---- stub backend specs (no real backend_config / network involved) --------
_OPENAI_SPEC = {
    "provider": "claude-cli", "base_url": "http://127.0.0.1:8787/v1",
    "native": {"kind": "openai-cli", "model": "claude-haiku-4-5"},
}
_ANTHROPIC_SPEC = {
    "provider": "claude-haiku", "base_url": "http://127.0.0.1:4000/v1",
    "native": {"kind": "anthropic", "model": "claude-haiku-4-5"},
}
_OLLAMA_SPEC = {
    "provider": "ollama", "base_url": "http://127.0.0.1:11434/v1",
    "native": {"kind": "ollama", "model": "qwen2.5:14b-instruct"},
}
# Attacker-tampered spec: a public/internal base_url the SSRF guard must refuse.
_EVIL_OPENAI_SPEC = {
    "provider": "claude-cli", "base_url": "http://169.254.169.254.attacker.com/v1",
    "native": {"kind": "openai-cli", "model": "claude-haiku-4-5"},
}
_EVIL_OLLAMA_SPEC = {
    "provider": "ollama", "base_url": "http://8.8.8.8:11434/v1",
    "native": {"kind": "ollama", "model": "qwen2.5:14b-instruct"},
}


class _StubMsg:
    """Minimal stand-in for a langchain AIMessage / chat result."""

    def __init__(self, content: Any, usage: Optional[dict] = None) -> None:
        self.content = content
        self.usage_metadata = usage


# --- _validate_brief --------------------------------------------------------
def test_validate_brief_accepts_normal():
    assert lr._validate_brief("hello") == "hello"


def test_validate_brief_rejects_non_str():
    try:
        lr._validate_brief(12345)  # type: ignore[arg-type]
        assert False, "expected ValueError for non-str brief"
    except ValueError:
        pass


def test_validate_brief_rejects_oversize():
    try:
        lr._validate_brief("a" * (lr._MAX_BRIEF_CHARS + 1))
        assert False, "expected ValueError for oversize brief"
    except ValueError:
        pass


def test_validate_brief_accepts_at_cap():
    big = "a" * lr._MAX_BRIEF_CHARS
    assert lr._validate_brief(big) == big  # boundary: exactly at cap is allowed


# --- _coerce_content --------------------------------------------------------
def test_coerce_content_str_passthrough():
    assert lr._coerce_content("plain") == "plain"


def test_coerce_content_list_of_dicts_flattened():
    blocks = [{"text": "foo"}, {"text": "bar"}, {"type": "image"}]
    assert lr._coerce_content(blocks) == "foobar"  # missing text -> ""


def test_coerce_content_list_mixed_non_dict():
    assert lr._coerce_content([{"text": "a"}, "b", 3]) == "ab3"


def test_coerce_content_none_is_empty():
    assert lr._coerce_content(None) == ""


def test_coerce_content_other_stringified():
    assert lr._coerce_content(42) == "42"


# --- _with_retry ------------------------------------------------------------
def test_with_retry_success_first_try():
    calls = {"n": 0}

    def fn() -> Tuple[str, Optional[dict]]:
        calls["n"] += 1
        return "ok", None

    assert lr._with_retry(fn, "lbl") == ("ok", None)
    assert calls["n"] == 1  # no needless retries on success


def test_with_retry_retries_then_succeeds(monkeypatch=None):
    calls = {"n": 0}
    _no_sleep()

    def fn() -> Tuple[str, Optional[dict]]:
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("transient")
        return "recovered", None

    try:
        assert lr._with_retry(fn, "lbl") == ("recovered", None)
        assert calls["n"] == 2
    finally:
        _restore_sleep()


def test_with_retry_exhausts_and_reraises_last():
    _no_sleep()
    calls = {"n": 0}

    def fn() -> Tuple[str, Optional[dict]]:
        calls["n"] += 1
        raise TimeoutError(f"down-{calls['n']}")

    try:
        lr._with_retry(fn, "lbl")
        assert False, "expected the last error to propagate after budget exhausted"
    except TimeoutError as e:
        assert str(e) == f"down-{lr._MAX_ATTEMPTS}"  # LAST error re-raised
        assert calls["n"] == lr._MAX_ATTEMPTS         # bounded, not infinite
    finally:
        _restore_sleep()


# --- _openai_caller ---------------------------------------------------------
class _StubOpenAIClient:
    """Records ctor + request kwargs, returns a scripted response, counts close()."""

    last_ctor: dict = {}
    last_request: dict = {}

    def __init__(self, response: Any) -> None:
        self._response = response
        self.closed = 0

        class _Completions:
            def create(_self, **kwargs):
                _StubOpenAIClient.last_request = kwargs
                return self._response

        class _Chat:
            completions = _Completions()

        self.chat = _Chat()

    def close(self) -> None:
        self.closed += 1


class _OAChoice:
    def __init__(self, content: Any) -> None:
        self.message = type("M", (), {"content": content})()


class _OAResp:
    def __init__(self, choices) -> None:
        self.choices = choices


_LAST_OPENAI_CLIENT: dict = {"client": None}


def _patch_openai(response: Any):
    """Install a stub ``openai.OpenAI`` returning *response*; return the restore fn.

    The created client instance is stashed in ``_LAST_OPENAI_CLIENT`` so cleanup
    tests can assert ``close()`` fired on it.
    """
    import openai

    orig = openai.OpenAI

    def factory(base_url, api_key, timeout):  # signature the runner uses
        _StubOpenAIClient.last_ctor = {"base_url": base_url, "api_key": api_key, "timeout": timeout}
        client = _StubOpenAIClient(response)
        _LAST_OPENAI_CLIENT["client"] = client
        return client

    openai.OpenAI = factory  # type: ignore[assignment]
    return lambda: setattr(openai, "OpenAI", orig)


def test_openai_caller_happy_path():
    restore = _patch_openai(_OAResp([_OAChoice("hi there")]))
    try:
        call = lr._openai_caller(_OPENAI_SPEC, max_tokens=None)
        assert call("prompt") == ("hi there", None)
        # timeout wired onto the client and the request (network lens).
        assert _StubOpenAIClient.last_ctor["timeout"] == lr._CALL_TIMEOUT_S
        assert _StubOpenAIClient.last_request["timeout"] == lr._CALL_TIMEOUT_S
    finally:
        restore()


def test_openai_caller_passes_max_tokens():
    restore = _patch_openai(_OAResp([_OAChoice("x")]))
    try:
        call = lr._openai_caller(_OPENAI_SPEC, max_tokens=256)
        call("p")
        assert _StubOpenAIClient.last_request["max_tokens"] == 256
    finally:
        restore()


def test_openai_caller_empty_choices_raises_not_silent():
    # error-handling-resilience: empty choices on a 200 is a BACKEND ERROR, raised as
    # _EmptyResponseError — never a silent ("", None) success. (Still no IndexError.)
    restore = _patch_openai(_OAResp([]))
    try:
        call = lr._openai_caller(_OPENAI_SPEC, max_tokens=None)
        try:
            call("p")
            assert False, "expected _EmptyResponseError for empty choices"
        except lr._EmptyResponseError:
            pass
    finally:
        restore()


def test_build_call_empty_choices_retries_then_propagates():
    # Wrapped in _with_retry: an always-empty backend is retried the full budget and
    # then the failure PROPAGATES (never a silent empty success).
    _no_sleep()
    restore_res = _patch_resolve(_OPENAI_SPEC)
    restore_oa = _patch_openai(_OAResp([]))
    try:
        call = lr._build_call(WS, max_tokens=None, use_usage=True)
        try:
            call("p")
            assert False, "expected empty-response failure to propagate"
        except lr._EmptyResponseError:
            pass
    finally:
        restore_oa()
        restore_res()
        _restore_sleep()


def test_openai_caller_none_content_coerced_empty():
    restore = _patch_openai(_OAResp([_OAChoice(None)]))
    try:
        call = lr._openai_caller(_OPENAI_SPEC, max_tokens=None)
        assert call("p") == ("", None)
    finally:
        restore()


# --- _anthropic_caller ------------------------------------------------------
def _patch_anthropic(msg: _StubMsg):
    import langchain_anthropic

    orig = langchain_anthropic.ChatAnthropic
    captured: dict = {}

    class _StubChat:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def invoke(self, prompt):
            captured["prompt"] = prompt
            return msg

    langchain_anthropic.ChatAnthropic = _StubChat  # type: ignore[assignment]
    return captured, lambda: setattr(langchain_anthropic, "ChatAnthropic", orig)


def test_anthropic_caller_list_content_and_usage():
    msg = _StubMsg([{"text": "a"}, {"text": "b"}], usage={"input_tokens": 5})
    captured, restore = _patch_anthropic(msg)
    try:
        call = lr._anthropic_caller(_ANTHROPIC_SPEC, max_tokens=99, use_usage=True)
        content, usage = call("p")
        assert content == "ab" and usage == {"input_tokens": 5}
        assert captured["timeout"] == lr._CALL_TIMEOUT_S  # network lens
        assert captured["max_tokens"] == 99
    finally:
        restore()


def test_anthropic_caller_usage_suppressed_when_disabled():
    msg = _StubMsg("txt", usage={"input_tokens": 5})
    _captured, restore = _patch_anthropic(msg)
    try:
        call = lr._anthropic_caller(_ANTHROPIC_SPEC, max_tokens=None, use_usage=False)
        content, usage = call("p")
        assert content == "txt" and usage is None
    finally:
        restore()


# --- _ollama_caller ---------------------------------------------------------
def _patch_ollama(msg: _StubMsg):
    import langchain_ollama

    orig = langchain_ollama.ChatOllama
    captured: dict = {}

    class _StubChat:
        def __init__(self, **kwargs):
            captured.update(kwargs)

        def invoke(self, prompt):
            return msg

    langchain_ollama.ChatOllama = _StubChat  # type: ignore[assignment]
    return captured, lambda: setattr(langchain_ollama, "ChatOllama", orig)


def test_ollama_caller_strips_v1_and_bounds_timeout():
    msg = _StubMsg("out", usage={"input_tokens": 1})
    captured, restore = _patch_ollama(msg)
    try:
        call = lr._ollama_caller(_OLLAMA_SPEC, use_usage=True)
        content, usage = call("p")
        assert content == "out" and usage == {"input_tokens": 1}
        assert captured["base_url"] == "http://127.0.0.1:11434"  # /v1 stripped
        assert captured["timeout"] == lr._CALL_TIMEOUT_S
        assert captured["format"] == "json"
    finally:
        restore()


def test_ollama_caller_usage_gated_off():
    msg = _StubMsg("out", usage={"input_tokens": 1})
    _captured, restore = _patch_ollama(msg)
    try:
        call = lr._ollama_caller(_OLLAMA_SPEC, use_usage=False)
        assert call("p") == ("out", None)
    finally:
        restore()


# --- _build_call dispatch (backend stubbed via resolve_backend) -------------
def _patch_resolve(spec: dict):
    orig = lr.resolve_backend
    lr.resolve_backend = lambda ws: spec  # type: ignore[assignment]
    return lambda: setattr(lr, "resolve_backend", orig)


def test_build_call_dispatches_openai():
    restore_res = _patch_resolve(_OPENAI_SPEC)
    restore_oa = _patch_openai(_OAResp([_OAChoice("R")]))
    try:
        call = lr._build_call(WS, max_tokens=None, use_usage=True)
        assert call("p") == ("R", None)
    finally:
        restore_oa()
        restore_res()


def test_build_call_dispatches_anthropic():
    restore_res = _patch_resolve(_ANTHROPIC_SPEC)
    _captured, restore_a = _patch_anthropic(_StubMsg("A", usage={"t": 1}))
    try:
        call = lr._build_call(WS, max_tokens=None, use_usage=True)
        assert call("p") == ("A", {"t": 1})
    finally:
        restore_a()
        restore_res()


def test_build_call_dispatches_ollama_for_unknown_kind():
    # Any non openai-cli / non anthropic kind falls through to the ollama caller.
    restore_res = _patch_resolve(_OLLAMA_SPEC)
    _captured, restore_o = _patch_ollama(_StubMsg("O"))
    try:
        call = lr._build_call(WS, max_tokens=None, use_usage=True)
        assert call("p") == ("O", None)
    finally:
        restore_o()
        restore_res()


def test_build_call_retries_wrap_inner():
    # A transient failure on the inner caller is absorbed by _with_retry.
    lr_no_sleep = _no_sleep()  # noqa: F841
    restore_res = _patch_resolve(_ANTHROPIC_SPEC)
    import langchain_ollama  # not used; ensure anthropic path

    orig = None
    try:
        import langchain_anthropic
        orig = langchain_anthropic.ChatAnthropic
        state = {"n": 0}

        class _Flaky:
            def __init__(self, **kwargs):
                pass

            def invoke(self, prompt):
                state["n"] += 1
                if state["n"] < 2:
                    raise ConnectionError("blip")
                return _StubMsg("finally")

        langchain_anthropic.ChatAnthropic = _Flaky  # type: ignore[assignment]
        call = lr._build_call(WS, max_tokens=None, use_usage=True)
        assert call("p") == ("finally", None)
        assert state["n"] == 2
    finally:
        if orig is not None:
            langchain_anthropic.ChatAnthropic = orig  # type: ignore[assignment]
        restore_res()
        _restore_sleep()


# --- _build_standard_call / _build_multicaller ------------------------------
def test_build_standard_call_uses_usage_and_max_tokens():
    restore_res = _patch_resolve(_ANTHROPIC_SPEC)
    captured, restore_a = _patch_anthropic(_StubMsg("S", usage={"t": 2}))
    try:
        call = lr._build_standard_call(WS, max_tokens=321)
        assert call("p") == ("S", {"t": 2})       # usage surfaced (on_usage support)
        assert captured["max_tokens"] == 321
    finally:
        restore_a()
        restore_res()


def test_build_multicaller_anthropic_default_1024():
    restore_res = _patch_resolve(_ANTHROPIC_SPEC)
    captured, restore_a = _patch_anthropic(_StubMsg("M", usage={"t": 3}))
    try:
        call = lr._build_multicaller(WS)
        assert call("p") == ("M", {"t": 3})
        # historical hardcoded 1024 preserved via the named constant.
        assert captured["max_tokens"] == lr._MULTICALLER_ANTHROPIC_MAX_TOKENS == 1024
    finally:
        restore_a()
        restore_res()


def test_build_multicaller_openai_path():
    restore_res = _patch_resolve(_OPENAI_SPEC)
    restore_oa = _patch_openai(_OAResp([_OAChoice("MC")]))
    try:
        call = lr._build_multicaller(WS)
        assert call("p") == ("MC", None)
    finally:
        restore_oa()
        restore_res()


# --- build_invoker end-to-end (real compiled StateGraph, stubbed call) ------
_LAST_BUILD_CALL_KW: dict = {}


def _patch_build_call(call_fn):
    """Force build_invoker to use *call_fn* by stubbing the shared _build_call.

    build_invoker routes through _build_call directly (so the correlation id threads
    into the retry labels), so this stubs that single entry point and records the
    kwargs it was invoked with for assertions (e.g. request_id propagation).
    """
    orig = lr._build_call
    _LAST_BUILD_CALL_KW.clear()

    def stub(ws, max_tokens=None, use_usage=True, request_id=None):
        _LAST_BUILD_CALL_KW.update(
            {"ws": ws, "max_tokens": max_tokens, "use_usage": use_usage, "request_id": request_id})
        return call_fn

    lr._build_call = stub  # type: ignore[assignment]
    return lambda: setattr(lr, "_build_call", orig)


def test_build_invoker_runs_graph_and_returns_output():
    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        assert "SYS" in prompt and "brief-x" in prompt  # system + user_message composed
        return "GRAPH-OUT", None

    restore = _patch_build_call(call)
    try:
        invoke = lr.build_invoker(WS, "SYS", lambda b: f"user:{b}")
        assert invoke("brief-x") == "GRAPH-OUT"
    finally:
        restore()


def test_build_invoker_fires_on_usage():
    seen: list = []

    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        return "out", {"input_tokens": 7}

    restore = _patch_build_call(call)
    try:
        invoke = lr.build_invoker(WS, "SYS", lambda b: b, on_usage=seen.append)
        invoke("b")
        assert seen == [{"input_tokens": 7}]
    finally:
        restore()


def test_build_invoker_multicaller_uses_anthropic_cap():
    # multicaller=True must feed _build_call the historical anthropic-only 1024 cap;
    # multicaller=False must pass the caller's max_tokens through unchanged.
    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        return "M", None

    restore = _patch_build_call(call)
    try:
        lr.build_invoker(WS, "SYS", lambda b: b, multicaller=True)("b")
        assert _LAST_BUILD_CALL_KW["max_tokens"] == lr._MULTICALLER_ANTHROPIC_MAX_TOKENS
        lr.build_invoker(WS, "SYS", lambda b: b, max_tokens=42)("b")
        assert _LAST_BUILD_CALL_KW["max_tokens"] == 42
    finally:
        restore()


def test_build_invoker_rejects_oversize_brief():
    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        assert False, "call must not run for an oversize brief"

    restore = _patch_build_call(call)
    try:
        invoke = lr.build_invoker(WS, "SYS", lambda b: b)
        try:
            invoke("a" * (lr._MAX_BRIEF_CHARS + 1))
            assert False, "expected ValueError for oversize brief"
        except ValueError:
            pass
    finally:
        restore()


def test_build_invoker_propagates_call_failure():
    # error-handling-resilience: a failing call must PROPAGATE, not return "".
    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        raise RuntimeError("backend down")

    restore = _patch_build_call(call)
    try:
        invoke = lr.build_invoker(WS, "SYS", lambda b: b)
        try:
            invoke("b")
            assert False, "expected the call failure to propagate"
        except RuntimeError as e:
            assert "backend down" in str(e)
    finally:
        restore()


# --- ROUND 2: SSRF containment (_assert_local_base_url / vulnerability lens) --
def test_assert_local_base_url_allows_loopback_and_private():
    for url in ("http://127.0.0.1:8787/v1", "http://localhost:4000/v1",
                "http://10.0.0.5:11434/v1", "http://192.168.1.9:11434"):
        assert lr._assert_local_base_url(url) == url


def test_assert_local_base_url_refuses_public():
    for url in ("http://8.8.8.8:80", "http://169.254.169.254.attacker.com/v1",
                "http://internal.corp.example.com/v1"):
        try:
            lr._assert_local_base_url(url)
            assert False, f"expected refusal of non-local base_url {url!r}"
        except ValueError:
            pass


def test_openai_caller_refuses_non_local_base_url():
    # The client must NOT be constructed for a public/attacker base_url.
    restore = _patch_openai(_OAResp([_OAChoice("x")]))
    _LAST_OPENAI_CLIENT["client"] = None
    try:
        try:
            lr._openai_caller(_EVIL_OPENAI_SPEC, max_tokens=None)
            assert False, "expected ValueError for non-local openai base_url"
        except ValueError:
            pass
        assert _LAST_OPENAI_CLIENT["client"] is None  # never built a client
    finally:
        restore()


def test_ollama_caller_refuses_non_local_base_url():
    built = {"n": 0}
    import langchain_ollama
    orig = langchain_ollama.ChatOllama

    class _NeverBuilt:
        def __init__(self, **kwargs):
            built["n"] += 1

    langchain_ollama.ChatOllama = _NeverBuilt  # type: ignore[assignment]
    try:
        try:
            lr._ollama_caller(_EVIL_OLLAMA_SPEC, use_usage=True)
            assert False, "expected ValueError for non-local ollama base_url"
        except ValueError:
            pass
        assert built["n"] == 0
    finally:
        langchain_ollama.ChatOllama = orig  # type: ignore[assignment]


# --- ROUND 2: client cleanup (_safe_close / _register_cleanup / memory lens) --
def test_safe_close_calls_close():
    client = _StubOpenAIClient(_OAResp([]))
    lr._safe_close(client)
    assert client.closed == 1


def test_safe_close_swallows_missing_and_raising_close():
    lr._safe_close(object())  # no close() attr -> no error

    class _Boom:
        def close(self):
            raise RuntimeError("close failed")

    lr._safe_close(_Boom())  # must not propagate


def test_register_cleanup_closes_client_when_call_collected():
    import gc

    client = _StubOpenAIClient(_OAResp([]))

    def call(prompt):
        return "x", None

    lr._register_cleanup(call, client)
    assert client.closed == 0
    del call                 # drop the only strong ref to the closure
    gc.collect()
    assert client.closed == 1  # finalizer fired exactly once on collection


def test_openai_caller_registers_cleanup():
    import gc
    restore = _patch_openai(_OAResp([_OAChoice("x")]))
    try:
        call = lr._openai_caller(_OPENAI_SPEC, max_tokens=None)
        client = _LAST_OPENAI_CLIENT["client"]
        assert client.closed == 0
        del call
        gc.collect()
        assert client.closed == 1
    finally:
        restore()


# --- ROUND 2: logic-error — anthropic-only max_tokens not leaked to openai ----
def test_build_call_openai_does_not_receive_max_tokens():
    # The multicaller passes 1024, but openai-cli must NOT receive a max_tokens.
    restore_res = _patch_resolve(_OPENAI_SPEC)
    restore_oa = _patch_openai(_OAResp([_OAChoice("R")]))
    try:
        call = lr._build_call(WS, max_tokens=lr._MULTICALLER_ANTHROPIC_MAX_TOKENS, use_usage=True)
        call("p")
        assert "max_tokens" not in _StubOpenAIClient.last_request  # not truncated
    finally:
        restore_oa()
        restore_res()


def test_multicaller_openai_ignores_anthropic_cap():
    restore_res = _patch_resolve(_OPENAI_SPEC)
    restore_oa = _patch_openai(_OAResp([_OAChoice("MC")]))
    try:
        call = lr._build_multicaller(WS)
        call("p")
        assert "max_tokens" not in _StubOpenAIClient.last_request
    finally:
        restore_oa()
        restore_res()


def test_build_call_anthropic_still_receives_max_tokens():
    restore_res = _patch_resolve(_ANTHROPIC_SPEC)
    captured, restore_a = _patch_anthropic(_StubMsg("A"))
    try:
        call = lr._build_call(WS, max_tokens=777, use_usage=True)
        call("p")
        assert captured["max_tokens"] == 777  # anthropic keeps the cap
    finally:
        restore_a()
        restore_res()


# --- ROUND 2: network — jittered backoff (thundering-herd mitigation) ---------
def test_backoff_uses_jitter():
    _no_sleep()
    slept: list = []
    orig_sleep = lr.time.sleep
    orig_random = lr.random.random
    lr.time.sleep = slept.append  # type: ignore[assignment]
    lr.random.random = lambda: 0.0  # full-jitter low bound -> 0.5x base
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        raise ConnectionError("x")

    try:
        try:
            lr._with_retry(fn, "lbl")
        except ConnectionError:
            pass
        # attempt 1 backoff = base*2^0*(0.5+0.0) = _BACKOFF_BASE_S*0.5
        assert slept and abs(slept[0] - lr._BACKOFF_BASE_S * 0.5) < 1e-9
    finally:
        lr.time.sleep = orig_sleep  # type: ignore[assignment]
        lr.random.random = orig_random  # type: ignore[assignment]
        _restore_sleep()


# --- ROUND 2: error-handling — on_usage failure must not lose the result ------
def test_build_invoker_bad_on_usage_preserves_output():
    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        return "GOOD", {"input_tokens": 1}

    def boom(_meta):
        raise RuntimeError("callback exploded")

    restore = _patch_build_call(call)
    try:
        invoke = lr.build_invoker(WS, "SYS", lambda b: b, on_usage=boom)
        assert invoke("b") == "GOOD"  # output preserved despite callback failure
    finally:
        restore()


# --- ROUND 2: observability — success path is logged --------------------------
def test_generate_node_logs_success(monkeypatch=None):
    import logging

    records: list = []

    class _Cap(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Cap()
    handler.setLevel(logging.DEBUG)
    lr.log.addHandler(handler)
    prev_level = lr.log.level
    lr.log.setLevel(logging.DEBUG)

    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        return "hello", None

    restore = _patch_build_call(call)
    try:
        invoke = lr.build_invoker(WS, "SYS", lambda b: b)
        invoke("b")
        msgs = [r.getMessage() for r in records]
        assert any("completed" in m and "output_chars=5" in m for m in msgs)
    finally:
        restore()
        lr.log.removeHandler(handler)
        lr.log.setLevel(prev_level)


# --- ROUND 3: observability — request/correlation id propagation --------------
def _capture_logs():
    """Attach a capturing handler at DEBUG; return (records, restore)."""
    import logging

    records: list = []

    class _Cap(logging.Handler):
        def emit(self, record):
            records.append(record)

    handler = _Cap()
    handler.setLevel(logging.DEBUG)
    lr.log.addHandler(handler)
    prev = lr.log.level
    lr.log.setLevel(logging.DEBUG)

    def restore():
        lr.log.removeHandler(handler)
        lr.log.setLevel(prev)

    return records, restore


def test_new_request_id_is_short_hex_and_unique():
    a, b = lr._new_request_id(), lr._new_request_id()
    assert a != b and len(a) == 8
    int(a, 16)  # valid hex, else ValueError


def test_build_invoker_uses_supplied_request_id():
    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        return "x", None

    restore = _patch_build_call(call)
    try:
        lr.build_invoker(WS, "SYS", lambda b: b, request_id="trace-123")("b")
        assert _LAST_BUILD_CALL_KW["request_id"] == "trace-123"  # threaded to _build_call
    finally:
        restore()


def test_build_invoker_autogenerates_request_id_when_absent():
    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        return "x", None

    restore = _patch_build_call(call)
    try:
        lr.build_invoker(WS, "SYS", lambda b: b)("b")
        rid = _LAST_BUILD_CALL_KW["request_id"]
        assert isinstance(rid, str) and len(rid) == 8  # auto-minted correlation id
    finally:
        restore()


def test_success_log_includes_request_id():
    records, restore_log = _capture_logs()

    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        return "hi", None

    restore = _patch_build_call(call)
    try:
        lr.build_invoker(WS, "SYS", lambda b: b, request_id="rid-xyz")("b")
        assert any("rid=rid-xyz" in r.getMessage() and "completed" in r.getMessage()
                   for r in records)
    finally:
        restore()
        restore_log()


def test_retry_labels_include_request_id():
    # Every retry/attempt log line carries the rid so a distributed trace can join
    # them. Drive a real _build_call so the rid flows into the _with_retry label.
    _no_sleep()
    records, restore_log = _capture_logs()
    restore_res = _patch_resolve(_OPENAI_SPEC)
    restore_oa = _patch_openai(_OAResp([]))  # empty -> _EmptyResponseError each attempt
    try:
        call = lr._build_call(WS, max_tokens=None, use_usage=True, request_id="rid-777")
        try:
            call("p")
        except lr._EmptyResponseError:
            pass
        attempt_lines = [r.getMessage() for r in records if "attempt" in r.getMessage()]
        assert attempt_lines and all("rid=rid-777" in m for m in attempt_lines)
    finally:
        restore_oa()
        restore_res()
        restore_log()
        _restore_sleep()


# --- ROUND 4: error-handling — rollback closes client if setup fails ----------
def test_guard_build_closes_client_on_failure():
    client = _StubOpenAIClient(_OAResp([]))

    def finish():
        raise RuntimeError("post-construction setup exploded")

    try:
        lr._guard_build(client, finish)
        assert False, "expected the setup error to propagate"
    except RuntimeError:
        pass
    assert client.closed == 1  # half-built client released deterministically


def test_guard_build_returns_and_leaves_client_open_on_success():
    client = _StubOpenAIClient(_OAResp([]))

    def call(prompt):
        return "x", None

    got = lr._guard_build(client, lambda: call)
    assert got is call and client.closed == 0  # success path does not close


def test_openai_caller_rolls_back_client_on_setup_failure():
    # If reading spec["native"]["model"] raises AFTER the client is built, the client
    # must be closed (not leaked to GC). Use a spec whose ["native"] raises on lookup.
    class _BoomNative(dict):
        def __getitem__(self, k):
            if k == "model":
                raise KeyError("model missing")
            return super().__getitem__(k)

    bad_spec = {"base_url": "http://127.0.0.1:8787/v1", "native": _BoomNative(kind="openai-cli")}
    restore = _patch_openai(_OAResp([_OAChoice("x")]))
    _LAST_OPENAI_CLIENT["client"] = None
    try:
        try:
            lr._openai_caller(bad_spec, max_tokens=None)
            assert False, "expected KeyError from model lookup"
        except KeyError:
            pass
        client = _LAST_OPENAI_CLIENT["client"]
        assert client is not None and client.closed == 1  # built then rolled back
    finally:
        restore()


# --- ROUND 4: observability — INFO-level success + metrics counters -----------
def _reset_metrics():
    with lr._METRICS_LOCK:
        for k in lr._METRICS:
            lr._METRICS[k] = 0


def test_get_metrics_returns_independent_copy():
    _reset_metrics()
    snap = lr.get_metrics()
    snap["calls_succeeded"] = 999          # mutate the copy
    assert lr.get_metrics()["calls_succeeded"] == 0  # live counters untouched


def test_with_retry_success_logs_info_and_counts():
    _reset_metrics()
    records, restore_log = _capture_logs()
    try:
        out = lr._with_retry(lambda: ("ok", None), "lbl")
        assert out == ("ok", None)
        info_msgs = [r.getMessage() for r in records if r.levelname == "INFO"]
        assert any("succeeded" in m for m in info_msgs)  # visible at INFO in prod
        assert lr.get_metrics()["calls_succeeded"] == 1
        assert lr.get_metrics()["call_retries"] == 0
    finally:
        restore_log()


def test_with_retry_counts_retries_then_success():
    _reset_metrics()
    _no_sleep()
    calls = {"n": 0}

    def fn():
        calls["n"] += 1
        if calls["n"] < 3:
            raise ConnectionError("blip")
        return "ok", None

    try:
        assert lr._with_retry(fn, "lbl") == ("ok", None)
        m = lr.get_metrics()
        assert m["call_retries"] == 2 and m["calls_succeeded"] == 1 and m["calls_failed"] == 0
    finally:
        _restore_sleep()


def test_with_retry_counts_terminal_failure():
    _reset_metrics()
    _no_sleep()

    def fn():
        raise TimeoutError("down")

    try:
        try:
            lr._with_retry(fn, "lbl")
            assert False, "expected terminal failure"
        except TimeoutError:
            pass
        m = lr.get_metrics()
        assert m["calls_failed"] == 1
        assert m["call_retries"] == lr._MAX_ATTEMPTS  # every attempt counted
        assert m["calls_succeeded"] == 0
    finally:
        _restore_sleep()


def test_generate_node_success_logs_at_info_level():
    _reset_metrics()
    records, restore_log = _capture_logs()

    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        return "hello", None

    restore = _patch_build_call(call)
    try:
        lr.build_invoker(WS, "SYS", lambda b: b)("b")
        completed = [r for r in records
                     if "completed" in r.getMessage() and r.levelname == "INFO"]
        assert completed and "output_chars=5" in completed[0].getMessage()
    finally:
        restore()
        restore_log()


# --- sleep patching helper (keep retry tests instant) -----------------------
_ORIG_SLEEP = lr.time.sleep


def _no_sleep():
    lr.time.sleep = lambda s: None  # type: ignore[assignment]
    return None


def _restore_sleep():
    lr.time.sleep = _ORIG_SLEEP  # type: ignore[assignment]


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
