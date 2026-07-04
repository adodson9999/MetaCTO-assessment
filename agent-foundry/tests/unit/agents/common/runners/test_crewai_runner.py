#!/usr/bin/env python3
"""Unit tests for agents/common/runners/crewai_runner.py — the CrewAI adapter.

Covers the whole build_invoker WORKFLOW plus every hardening property, with the
backend fully stubbed (NO real network / model / litellm calls):

  * build_invoker returns a callable and invoke() returns str on every path;
  * _validate_spec extracts (kind, model, base_url) and rejects partial/abusive
    specs (missing native, non-string base_url) with ValueError;
  * _llm_kwargs branches correctly on kind — anthropic -> 'anthropic/<m>',
    openai-cli -> 'openai/<m>' + base_url (NOT ollama), ollama -> 'ollama/<m>'
    with /v1 trimmed and json response_format; unknown kind raises;
  * every kind carries a bounded timeout;
  * graceful degradation: resolve/LLM failure, kickoff exhaustion, and a
    pre-kickoff (user_message_fn) fault all yield a parseable error-JSON string,
    never raise;
  * bounded retry: a transient kickoff error is retried then succeeds; a fresh
    crew is built per attempt (no shared/re-run state);
  * adversarial input: oversized brief is truncated to the byte cap; non-str
    brief is coerced;
  * backoff sleep is capped and jittered.

Run: agent-foundry/.venv/bin/python \
     agent-foundry/tests/unit/agents/common/runners/test_crewai_runner.py
"""
from __future__ import annotations

import json
import logging
import sys
import types
from pathlib import Path
from typing import Any

WS = Path(__file__).resolve().parents[5]  # agent-foundry
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))


class _ListHandler(logging.Handler):
    """Capture formatted log messages into a list for observability assertions."""

    def __init__(self, sink: list[str]) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append(record.getMessage())


class _LevelListHandler(logging.Handler):
    """Capture (levelname, message) tuples for level-aware observability assertions."""

    def __init__(self, sink: list[tuple[str, str]]) -> None:
        super().__init__()
        self._sink = sink

    def emit(self, record: logging.LogRecord) -> None:
        self._sink.append((record.levelname, record.getMessage()))


def _capture_logs(level: int = logging.DEBUG):
    """Context manager: attach a level-capturing handler to the runner logger."""
    import contextlib as _cl

    @_cl.contextmanager
    def _cm():
        records: list[tuple[str, str]] = []
        handler = _LevelListHandler(records)
        cr.log.addHandler(handler)
        old = cr.log.level
        cr.log.setLevel(level)
        try:
            yield records
        finally:
            cr.log.removeHandler(handler)
            cr.log.setLevel(old)

    return _cm()


# --- fake crewai module injected BEFORE importing the runner ----------------
class _FakeLLM:
    """Records the kwargs it was built with so tests can assert routing."""

    last_kwargs: dict[str, Any] = {}

    def __init__(self, **kwargs: Any) -> None:
        _FakeLLM.last_kwargs = kwargs
        self.kwargs = kwargs


class _FakeAgent:
    instances = 0

    def __init__(self, **kwargs: Any) -> None:
        _FakeAgent.instances += 1
        self.kwargs = kwargs


class _FakeTask:
    def __init__(self, **kwargs: Any) -> None:
        self.kwargs = kwargs


class _FakeCrew:
    """Configurable crew: kickoff returns a canned value or raises N times.

    Also records ``close()`` calls so the release-on-error contract is testable.
    """

    builds = 0
    kickoffs = 0
    closes = 0
    fail_times = 0  # number of leading kickoff calls that raise
    result = "STUB_OUTPUT"

    def __init__(self, **kwargs: Any) -> None:
        _FakeCrew.builds += 1
        self.kwargs = kwargs

    def kickoff(self) -> str:
        _FakeCrew.kickoffs += 1
        if _FakeCrew.kickoffs <= _FakeCrew.fail_times:
            raise RuntimeError(f"transient backend error #{_FakeCrew.kickoffs}")
        return _FakeCrew.result

    def close(self) -> None:
        _FakeCrew.closes += 1


def _install_fake_crewai() -> None:
    mod = types.ModuleType("crewai")
    mod.LLM = _FakeLLM
    mod.Agent = _FakeAgent
    mod.Task = _FakeTask
    mod.Crew = _FakeCrew
    sys.modules["crewai"] = mod


_install_fake_crewai()

from runners import crewai_runner as cr  # noqa: E402


# --- helpers ----------------------------------------------------------------
def _spec(kind: str = "ollama", model: str = "m", base_url: str = "http://127.0.0.1:11434/v1") -> dict:
    return {
        "provider": "p", "openai_compatible": True, "base_url": base_url,
        "model": model, "api_key_env": "X", "air_gapped": False,
        "native": {"kind": kind, "model": model},
    }


def _patch_resolve(spec: Any) -> Any:
    """Monkeypatch resolve_backend to return *spec* (or raise if spec is an exc)."""
    orig = cr.resolve_backend

    def fake(ws: Path) -> Any:
        if isinstance(spec, BaseException):
            raise spec
        return spec

    cr.resolve_backend = fake
    return orig


def _reset_crew() -> None:
    _FakeCrew.builds = 0
    _FakeCrew.kickoffs = 0
    _FakeCrew.closes = 0
    _FakeCrew.fail_times = 0
    _FakeCrew.result = "STUB_OUTPUT"
    _FakeAgent.instances = 0


# --- _validate_spec ---------------------------------------------------------
def test_validate_spec_extracts_tuple():
    assert cr._validate_spec(_spec("ollama", "llama3", "http://h/v1")) == (
        "ollama", "llama3", "http://h/v1",
    )


def test_validate_spec_missing_native_raises():
    try:
        cr._validate_spec({})
        assert False, "expected ValueError for missing native"
    except ValueError:
        pass


def test_validate_spec_non_string_base_url_raises():
    bad = _spec()
    bad["base_url"] = 123
    try:
        cr._validate_spec(bad)
        assert False, "expected ValueError for non-string base_url"
    except ValueError:
        pass


def test_validate_spec_empty_kind_raises():
    bad = _spec()
    bad["native"]["kind"] = ""
    try:
        cr._validate_spec(bad)
        assert False, "expected ValueError for empty kind"
    except ValueError:
        pass


def test_validate_spec_missing_model_raises():
    bad = _spec()
    del bad["native"]["model"]
    try:
        cr._validate_spec(bad)
        assert False, "expected ValueError for missing model"
    except ValueError:
        pass


def test_validate_spec_non_string_model_raises():
    bad = _spec()
    bad["native"]["model"] = 42
    try:
        cr._validate_spec(bad)
        assert False, "expected ValueError for non-string model"
    except ValueError:
        pass


def test_validate_spec_empty_model_raises():
    bad = _spec()
    bad["native"]["model"] = ""
    try:
        cr._validate_spec(bad)
        assert False, "expected ValueError for empty model"
    except ValueError:
        pass


# --- _llm_kwargs branching (logic-error lens) -------------------------------
def test_llm_kwargs_anthropic_prefix_and_timeout():
    kw = cr._llm_kwargs("anthropic", "claude-x", "")
    assert kw["model"] == "anthropic/claude-x"
    assert kw["timeout"] == cr._REQUEST_TIMEOUT_S
    assert kw["temperature"] == 0          # deterministic decoding


def test_llm_kwargs_openai_cli_not_ollama():
    kw = cr._llm_kwargs("openai-cli", "shim-m", "http://127.0.0.1:8787/v1")
    assert kw["model"] == "openai/shim-m"          # NOT ollama/
    assert kw["base_url"] == "http://127.0.0.1:8787/v1"
    assert kw["timeout"] == cr._REQUEST_TIMEOUT_S
    assert kw["temperature"] == 0


def test_llm_kwargs_ollama_trims_v1_and_json():
    kw = cr._llm_kwargs("ollama", "llama3", "http://127.0.0.1:11434/v1")
    assert kw["model"] == "ollama/llama3"
    assert kw["base_url"] == "http://127.0.0.1:11434"   # /v1 trimmed
    assert kw["response_format"] == {"type": "json_object"}
    assert kw["timeout"] == cr._REQUEST_TIMEOUT_S
    assert kw["temperature"] == 0


def test_llm_kwargs_every_kind_sets_temperature_zero_and_timeout():
    # The shared invariants (temperature + timeout) must hold for ALL kinds.
    for kind, base_url in (("anthropic", ""), ("openai-cli", "http://h/v1"), ("ollama", "http://h/v1")):
        kw = cr._llm_kwargs(kind, "m", base_url)
        assert kw["temperature"] == 0, kind
        assert kw["timeout"] == cr._REQUEST_TIMEOUT_S, kind


def test_llm_kwargs_unknown_kind_raises():
    try:
        cr._llm_kwargs("mystery", "m", "")
        assert False, "expected ValueError for unknown kind"
    except ValueError:
        pass


# --- build_invoker happy path -----------------------------------------------
def test_build_invoker_returns_callable_and_str():
    _reset_crew()
    orig = _patch_resolve(_spec("ollama"))
    try:
        invoke = cr.build_invoker(WS, "SYSTEM", lambda b: f"MSG:{b}")
        assert callable(invoke)
        out = invoke("hello")
        assert isinstance(out, str) and out == "STUB_OUTPUT"
    finally:
        cr.resolve_backend = orig


def test_build_invoker_selects_anthropic_llm():
    _reset_crew()
    orig = _patch_resolve(_spec("anthropic", "claude-haiku"))
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        invoke("x")   # LLM is now constructed per-invocation (concurrency fix)
        assert _FakeLLM.last_kwargs["model"] == "anthropic/claude-haiku"
    finally:
        cr.resolve_backend = orig


def test_invoke_builds_fresh_crew_each_call():
    _reset_crew()
    orig = _patch_resolve(_spec("ollama"))
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        invoke("a")
        invoke("b")
        assert _FakeCrew.builds == 2          # one crew per invocation, not reused
        assert _FakeAgent.instances == 2      # fresh Agent per invocation (no shared singleton)
    finally:
        cr.resolve_backend = orig


# --- retry / resilience -----------------------------------------------------
def test_kickoff_retries_then_succeeds():
    _reset_crew()
    _FakeCrew.fail_times = 2      # fail twice, succeed on the 3rd (== _MAX_ATTEMPTS)
    orig = _patch_resolve(_spec("ollama"))
    orig_sleep = cr._sleep_backoff
    cr._sleep_backoff = lambda attempt: None   # no real sleeping in tests
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        out = invoke("x")
        assert out == "STUB_OUTPUT"
        assert _FakeCrew.builds == 3           # fresh crew per attempt
    finally:
        cr.resolve_backend = orig
        cr._sleep_backoff = orig_sleep


def test_kickoff_exhaustion_degrades_to_error_json():
    _reset_crew()
    _FakeCrew.fail_times = 99      # always fails
    orig = _patch_resolve(_spec("ollama"))
    orig_sleep = cr._sleep_backoff
    cr._sleep_backoff = lambda attempt: None
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        out = invoke("x")
        payload = json.loads(out)              # must be parseable, never a crash
        assert payload["error"] == "crewai_runner_unavailable"
        assert _FakeCrew.kickoffs == cr._MAX_ATTEMPTS
    finally:
        cr.resolve_backend = orig
        cr._sleep_backoff = orig_sleep


def test_resolve_failure_degrades_to_error_json():
    _reset_crew()
    orig = _patch_resolve(RuntimeError("backend down"))
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        out = invoke("x")
        payload = json.loads(out)
        assert payload["error"] == "crewai_runner_unavailable"
    finally:
        cr.resolve_backend = orig


def test_llm_construction_failure_degrades():
    _reset_crew()
    orig = _patch_resolve(_spec("ollama"))
    orig_sleep = cr._sleep_backoff
    cr._sleep_backoff = lambda attempt: None
    # Force per-invocation LLM(...) to blow up inside make_crew.
    fake_mod = sys.modules["crewai"]
    orig_llm = fake_mod.LLM

    class Boom:
        def __init__(self, **kw: Any) -> None:
            raise RuntimeError("litellm import error")

    fake_mod.LLM = Boom
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        payload = json.loads(invoke("x"))
        assert payload["error"] == "crewai_runner_unavailable"
    finally:
        fake_mod.LLM = orig_llm
        cr._sleep_backoff = orig_sleep
        cr.resolve_backend = orig


def test_pre_kickoff_user_message_fault_degrades():
    _reset_crew()
    orig = _patch_resolve(_spec("ollama"))
    orig_sleep = cr._sleep_backoff
    cr._sleep_backoff = lambda attempt: None

    def boom(_b: str) -> str:
        raise ValueError("bad user_message")

    try:
        invoke = cr.build_invoker(WS, "SYS", boom)
        payload = json.loads(invoke("x"))
        assert payload["error"] == "crewai_runner_unavailable"
    finally:
        cr._sleep_backoff = orig_sleep
        cr.resolve_backend = orig


# --- adversarial input ------------------------------------------------------
def test_oversized_brief_truncated():
    _reset_crew()
    captured: dict[str, str] = {}

    def capture(msg: str) -> str:
        captured["desc"] = msg
        return msg

    orig = _patch_resolve(_spec("ollama"))
    try:
        invoke = cr.build_invoker(WS, "SYS", capture)
        big = "A" * (cr._MAX_BRIEF_BYTES + 1000)
        invoke(big)
        assert len(captured["desc"].encode("utf-8")) <= cr._MAX_BRIEF_BYTES
    finally:
        cr.resolve_backend = orig


def test_non_str_brief_coerced_not_crash():
    _reset_crew()
    orig = _patch_resolve(_spec("ollama"))
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        out = invoke(12345)  # type: ignore[arg-type]
        assert isinstance(out, str) and out == "STUB_OUTPUT"
    finally:
        cr.resolve_backend = orig


def test_bounded_brief_under_cap_unchanged():
    assert cr._bounded_brief("small") == "small"


def test_bounded_brief_char_pregate_slices_before_encode():
    # A string longer than the byte cap (in chars) must be char-sliced to the cap
    # length BEFORE encoding (adversarial-input): the returned value never exceeds
    # the byte cap, and its char length is clamped — proving no full-input encode.
    huge = "A" * (cr._MAX_BRIEF_BYTES + 5000)
    out = cr._bounded_brief(huge)
    assert len(out) <= cr._MAX_BRIEF_BYTES
    assert len(out.encode("utf-8")) <= cr._MAX_BRIEF_BYTES


def test_bounded_brief_multibyte_byte_cap_no_raise():
    # Multibyte chars: char count == cap but byte count > cap forces the byte
    # path, which must truncate without raising on a split codepoint.
    s = "é" * cr._MAX_BRIEF_BYTES  # 2 bytes each -> exceeds byte cap
    out = cr._bounded_brief(s)
    assert len(out.encode("utf-8")) <= cr._MAX_BRIEF_BYTES


def test_bounded_brief_4byte_emoji_encode_is_bounded():
    # adversarial-input [round-3]: a string whose CHAR count is within an older
    # gate but made of 4-byte emoji must NOT be fully encoded. We assert the
    # returned bytes are within the cap, which is only possible if the input was
    # char-sliced to <= _MAX_BRIEF_BYTES chars before the (bounded) encode.
    emoji = "\U0001F600" * cr._MAX_BRIEF_BYTES  # 4 bytes/char
    out = cr._bounded_brief(emoji)
    assert len(out) <= cr._MAX_BRIEF_BYTES          # char-sliced first
    assert len(out.encode("utf-8")) <= cr._MAX_BRIEF_BYTES


# --- backoff: cap, jitter isolation, observability --------------------------
def test_sleep_backoff_capped():
    recorded: list[float] = []
    orig_sleep = cr.time.sleep
    orig_uniform = cr._JITTER_RNG.uniform
    cr.time.sleep = lambda s: recorded.append(s)
    cr._JITTER_RNG.uniform = lambda a, b: b        # take the max of the jitter window
    try:
        cr._sleep_backoff(10)                       # huge attempt -> must clamp to cap
        assert recorded and recorded[0] == cr._BACKOFF_CAP_S
    finally:
        cr.time.sleep = orig_sleep
        cr._JITTER_RNG.uniform = orig_uniform


def test_sleep_backoff_uses_private_prng_not_module_global():
    # Concurrency guard: jitter must be drawn from the private _JITTER_RNG, never
    # the shared module-global random, so it can't corrupt others' PRNG state.
    orig_sleep = cr.time.sleep
    cr.time.sleep = lambda s: None
    called = {"private": 0, "global": 0}
    orig_priv = cr._JITTER_RNG.uniform
    orig_glob = cr.random.uniform
    cr._JITTER_RNG.uniform = lambda a, b: called.__setitem__("private", called["private"] + 1) or 0.0
    cr.random.uniform = lambda a, b: called.__setitem__("global", called["global"] + 1) or 0.0
    try:
        cr._sleep_backoff(1)
        assert called["private"] == 1 and called["global"] == 0
    finally:
        cr.time.sleep = orig_sleep
        cr._JITTER_RNG.uniform = orig_priv
        cr.random.uniform = orig_glob


def test_sleep_backoff_logs_delay():
    # Observability: the chosen delay is emitted at DEBUG so backoff is diagnosable.
    orig_sleep = cr.time.sleep
    cr.time.sleep = lambda s: None
    records: list[str] = []
    handler = _ListHandler(records)
    cr.log.addHandler(handler)
    old_level = cr.log.level
    cr.log.setLevel(cr.logging.DEBUG)
    try:
        cr._sleep_backoff(1)
        assert any("backoff sleep" in m for m in records)
    finally:
        cr.log.removeHandler(handler)
        cr.log.setLevel(old_level)
        cr.time.sleep = orig_sleep


# --- resource release on error paths (error-handling-resilience) ------------
def test_crew_released_on_success():
    _reset_crew()
    orig = _patch_resolve(_spec("ollama"))
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        invoke("x")
        assert _FakeCrew.closes == 1          # released after a successful kickoff
    finally:
        cr.resolve_backend = orig


def test_crew_released_on_every_failed_attempt():
    _reset_crew()
    _FakeCrew.fail_times = 99                  # every kickoff raises
    orig = _patch_resolve(_spec("ollama"))
    orig_sleep = cr._sleep_backoff
    cr._sleep_backoff = lambda attempt: None
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        invoke("x")
        # One crew built and released per attempt, even though each kickoff failed.
        assert _FakeCrew.builds == cr._MAX_ATTEMPTS
        assert _FakeCrew.closes == cr._MAX_ATTEMPTS
    finally:
        cr.resolve_backend = orig
        cr._sleep_backoff = orig_sleep


def test_released_crew_without_close_is_noop():
    # A crew lacking close/reset must not raise on release (version tolerance).
    class Bare:
        def kickoff(self) -> str:
            return "ok"

    with cr._released_crew(lambda: Bare()) as crew:
        assert crew.kickoff() == "ok"          # no AttributeError on exit


def test_error_json_is_parseable_and_generic():
    payload = json.loads(cr._error_json("some reason"))
    assert payload["error"] == "crewai_runner_unavailable"
    assert payload["reason"] == "some reason"


# --- round-3: concurrency (per-thread LLM), observability, error-handling ----
def test_build_llm_returns_frozen_kwargs_not_instance():
    # concurrency: _build_llm must hand back immutable kwargs, never a live LLM,
    # so nothing mutable is shared across invoke threads.
    orig = _patch_resolve(_spec("ollama", "llama3"))
    try:
        kwargs = cr._build_llm(WS)
        assert isinstance(kwargs, cr.MappingProxyType)   # frozen; read-only view
        assert kwargs["model"] == "ollama/llama3"
        try:
            kwargs["model"] = "tampered"                 # must be immutable
            assert False, "frozen kwargs mutated"
        except TypeError:
            pass
    finally:
        cr.resolve_backend = orig


def test_build_llm_none_on_resolve_failure():
    orig = _patch_resolve(RuntimeError("down"))
    try:
        assert cr._build_llm(WS) is None
    finally:
        cr.resolve_backend = orig


def test_fresh_llm_constructed_per_invocation():
    # concurrency: each invoke builds its OWN LLM (no shared mutable instance).
    _reset_crew()
    _FakeLLM.builds = 0
    orig_init = _FakeLLM.__init__

    def counting_init(self: Any, **kw: Any) -> None:
        _FakeLLM.builds += 1
        orig_init(self, **kw)

    _FakeLLM.__init__ = counting_init  # type: ignore[method-assign]
    orig = _patch_resolve(_spec("ollama"))
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        invoke("a")
        invoke("b")
        assert _FakeLLM.builds == 2       # one fresh LLM per invocation, not shared
    finally:
        _FakeLLM.__init__ = orig_init  # type: ignore[method-assign]
        cr.resolve_backend = orig


def test_metrics_record_success_and_failure():
    # observability: attempts/successes/failures are counted per invocation.
    _reset_crew()
    before = cr.get_metrics()
    orig = _patch_resolve(_spec("ollama"))
    orig_sleep = cr._sleep_backoff
    cr._sleep_backoff = lambda attempt: None
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        invoke("ok")                       # success
        _FakeCrew.fail_times = 99
        invoke("bad")                      # failure (exhausted)
        after = cr.get_metrics()
        assert after["successes"] - before["successes"] == 1
        assert after["failures"] - before["failures"] == 1
        assert after["attempts"] - before["attempts"] == 2
        assert after["latency_s_total"] >= before["latency_s_total"]
    finally:
        cr.resolve_backend = orig
        cr._sleep_backoff = orig_sleep


def test_metrics_snapshot_is_consistent_shape():
    snap = cr.get_metrics()
    assert set(snap) == {"attempts", "successes", "failures", "latency_s_total"}


def test_invocation_id_is_logged_and_monotonic():
    # observability: every invoke stamps a unique, increasing id into its logs.
    _reset_crew()
    records: list[str] = []
    handler = _ListHandler(records)
    cr.log.addHandler(handler)
    old_level = cr.log.level
    cr.log.setLevel(cr.logging.INFO)
    orig = _patch_resolve(_spec("ollama"))
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        invoke("x")
        invoke("y")
        stamped = [m for m in records if m.startswith("[inv ")]
        assert len(stamped) >= 2           # each call emits at least start + result
    finally:
        cr.log.removeHandler(handler)
        cr.log.setLevel(old_level)
        cr.resolve_backend = orig


def test_pathological_brief_str_raises_degrades():
    # error-handling-resilience [round-3]: a brief whose str()/len() raises must
    # degrade to error-JSON, never escape uncaught.
    _reset_crew()

    class Nasty:
        def __str__(self) -> str:
            raise RuntimeError("str() exploded")

    orig = _patch_resolve(_spec("ollama"))
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        payload = json.loads(invoke(Nasty()))  # type: ignore[arg-type]
        assert payload["error"] == "crewai_runner_unavailable"
    finally:
        cr.resolve_backend = orig


# --- round-4: observability (teardown), adversarial coerce, metrics safety ---
def test_release_crew_logs_warning_on_teardown_failure():
    # observability [round-4]: a failing close() must be logged at WARNING (leak
    # signal), not silently suppressed.
    class LeakyCrew:
        def close(self) -> None:
            raise OSError("socket close failed")

    with _capture_logs() as records:
        cr._release_crew_resources(LeakyCrew())
    warnings = [m for lvl, m in records if lvl == "WARNING"]
    assert any("close() failed" in m and "leak" in m for m in warnings)


def test_release_crew_logs_debug_when_no_teardown():
    # observability [round-4]: a crew with no close/reset is logged at DEBUG so the
    # absence of cleanup is answerable from logs.
    class Bare:
        pass

    with _capture_logs() as records:
        cr._release_crew_resources(Bare())
    assert any(lvl == "DEBUG" and "no close/reset" in m for lvl, m in records)


def test_release_crew_teardown_failure_does_not_propagate():
    # A raising teardown must never escape (it can't mask the real kickoff result).
    class LeakyCrew:
        def reset(self) -> None:
            raise RuntimeError("boom")

    cr._release_crew_resources(LeakyCrew())   # must not raise


def test_kickoff_succeeds_even_if_teardown_raises():
    # error-handling-resilience: a teardown failure after a successful kickoff must
    # not turn success into failure — the real result is still returned.
    _reset_crew()

    class Crew:
        def kickoff(self) -> str:
            return "REAL_RESULT"

        def close(self) -> None:
            raise OSError("leak on close")

    out = cr._kickoff_with_retry(lambda: Crew())
    assert out == "REAL_RESULT"


def test_metrics_record_never_raises_on_internal_fault():
    # error-handling-resilience [round-4]: metrics recording is best-effort; an
    # internal fault (e.g. a broken lock) must be swallowed, never propagated.
    m = cr._Metrics()

    class BadLock:
        def __enter__(self):  # noqa: ANN204
            raise RuntimeError("lock acquire failed")

        def __exit__(self, *a: Any) -> bool:
            return False

    m._lock = BadLock()  # type: ignore[assignment]
    m.record(success=True, latency_s=0.1)   # must not raise
    m.record(success=False, latency_s=0.2)  # must not raise


def test_metrics_failure_does_not_break_invoke_contract():
    # If _METRICS.record raises, invoke() must STILL return a str (contract).
    _reset_crew()
    orig = _patch_resolve(_spec("ollama"))
    orig_record = cr._METRICS.record

    def boom(**_kw: Any) -> None:
        raise RuntimeError("metrics exploded")

    cr._METRICS.record = boom  # type: ignore[assignment]
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: b)
        out = invoke("x")
        assert isinstance(out, str)                 # never raises, always a str
        json.loads(out) if out.startswith("{") else out  # parseable if error-JSON
    finally:
        cr._METRICS.record = orig_record            # type: ignore[assignment]
        cr.resolve_backend = orig


def test_run_one_invocation_outer_safety_net_returns_str():
    # error-handling-resilience [round-4]: even if the inner body raises something
    # unforeseen, the outer wrapper returns a parseable error-JSON str.
    def boom_factory() -> Any:
        raise RuntimeError("unexpected")

    orig_inner = cr._run_invocation_inner

    def raising_inner(make_crew: Any, inv_id: int) -> str:
        raise RuntimeError("escaped inner degradation")

    cr._run_invocation_inner = raising_inner  # type: ignore[assignment]
    try:
        out = cr._run_one_invocation(boom_factory, 999)
        assert isinstance(out, str)
        payload = json.loads(out)
        assert payload["error"] == "crewai_runner_unavailable"
    finally:
        cr._run_invocation_inner = orig_inner  # type: ignore[assignment]


def test_coerce_brief_passes_str_through():
    assert cr._coerce_brief("hello") == "hello"


def test_coerce_brief_bounds_hostile_str_dunder():
    # adversarial-input [round-4]: a non-str whose __str__ returns a huge string
    # must be sliced to the char cap during coercion, BEFORE _bounded_brief.
    class HugeStr:
        def __str__(self) -> str:
            return "Z" * (cr._MAX_BRIEF_BYTES * 3)

    out = cr._coerce_brief(HugeStr())
    assert len(out) <= cr._MAX_BRIEF_BYTES          # bounded at coercion boundary


def test_invoke_hostile_str_dunder_bounded_and_succeeds():
    # End-to-end: a hostile __str__ brief is bounded and the Task description never
    # exceeds the byte cap.
    _reset_crew()
    captured: dict[str, str] = {}

    class HugeStr:
        def __str__(self) -> str:
            return "Q" * (cr._MAX_BRIEF_BYTES * 4)

    orig = _patch_resolve(_spec("ollama"))
    try:
        invoke = cr.build_invoker(WS, "SYS", lambda b: captured.__setitem__("d", b) or b)
        out = invoke(HugeStr())  # type: ignore[arg-type]
        assert isinstance(out, str) and out == "STUB_OUTPUT"
        assert len(captured["d"].encode("utf-8")) <= cr._MAX_BRIEF_BYTES
    finally:
        cr.resolve_backend = orig


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
