#!/usr/bin/env python3
"""Unit tests for the hardened langgraph auth-flow dispatcher (run.py).

Covers the dispatcher's helper functions AND the full
load-prompt -> resolve-backend -> build-invoker -> run -> handoff workflow,
including every failure/degradation path the hardening added:
  * happy path: _prepare wires prompt+backend+invoker; main() prints the exact
    headline line and hands a real plan to the harness;
  * missing / empty / non-str prompt and non-dict backend: _prepare raises;
  * transient model fault / parse fault / unparseable / empty-dict / non-dict /
    oversized response: generate() degrades to an empty plan, never raises;
  * malformed summary + pathological field value + broken __str__: _emit_summary
    tolerates and still emits, and logs structured metrics;
  * scheme_brief failure: degrades to empty brief, run still emits a headline;
  * run_auth_test failure: retried, then degrades to a still-emitted headline;
  * workspace validation: rejects missing root, missing subdir, over-long path;
  * _run_step: deadline + jittered retry + start/success/fail logging;
  * _run_step exhaustion and single-attempt recovery.

NO real network/model calls: load_system_prompt, resolve_backend, build_invoker,
and the auth_harness surface are all stubbed before the dispatcher is imported.
Retry backoff is zeroed in tests that exercise exhaustion so they stay fast.
Style mirrors tests/unit/scripts/test_backend_config.py: plain asserts, a main()
that runs every test_*, prints PASS/FAIL, and exits non-zero on any failure.

Run: agent-foundry/.venv/bin/python \
     agent-foundry/tests/unit/agents/api-tester/test-authentication-flows/langgraph/test_run.py
"""
from __future__ import annotations

import importlib.util
import io
import os
import sys
import types
from contextlib import redirect_stdout
from pathlib import Path

FRAMEWORK = "langgraph"
EXPECTED_AGENT = "langgraph"

# agent-foundry root: tests/unit/agents/api-tester/test-authentication-flows/<fw>/ -> up 6.
WS = Path(__file__).resolve().parents[6]
RUN_PY = (WS / "agents" / "api-tester" / "test-authentication-flows"
          / FRAMEWORK / "run.py")

_SUMMARY = {
    "auth_flow_pass_rate_pct": 80.0,
    "false_acceptance_rate_pct": 0.0,
    "false_rejection_rate_pct": 20.0,
    "executed_cases": 5,
}
_EXPECTED_LINE = f"[{EXPECTED_AGENT}] pass_rate=80.0% FAR=0.0% FRR=20.0% executed=5"


# --------------------------------------------------------------------------- #
# Test doubles for the dispatcher's imported dependencies
# --------------------------------------------------------------------------- #
class _FakeHarness:
    """Stub of ``auth_harness`` recording the plan the dispatcher hands over."""

    def __init__(self) -> None:
        self.extract_return = {"schemes": [{"scheme": "bearer"}]}
        self.extract_side = None
        self.summary_return = dict(_SUMMARY)
        self.brief_side = None
        self.run_side = None
        self.run_fail_times = 0            # transient: fail N calls, then succeed
        self.captured_plan = None
        self.brief_calls = 0
        self.run_calls = 0

    def scheme_brief(self) -> str:
        self.brief_calls += 1
        if self.brief_side is not None:
            raise self.brief_side
        return "protected_endpoint: GET /auth/me"

    def extract_json(self, text):
        if self.extract_side is not None:
            raise self.extract_side
        return self.extract_return

    def run_auth_test(self, agent, generate):
        self.run_calls += 1
        if self.run_side is not None:
            raise self.run_side
        if self.run_calls <= self.run_fail_times:
            raise ConnectionError("transient harness blip")
        # Invoke generate() exactly as the real harness does so the wrapping /
        # degradation logic under test actually executes.
        self.captured_plan = generate()
        return self.summary_return


def _install_stubs(*, prompt_side=None, prompt_return="SYSTEM PROMPT BODY",
                   backend_side=None, backend_return=None,
                   invoke_side=None, invoke_return='{"schemes": []}', harness=None):
    """Inject stub modules for every dependency the dispatcher imports at load.

    Rationale: run.py imports auth_harness / auth_prompt / runners.utils /
    runners.<fw>_runner at module scope, so the doubles must live in sys.modules
    BEFORE import. Each stub is a tiny in-memory module — no network, no model.
    Returns the (harness, calls) recording surface.
    """
    calls = {"backend": 0, "invoker_built": 0}
    harness = harness or _FakeHarness()

    def _load_system_prompt(subagent_md, primary_fn=None):
        if prompt_side is not None:
            raise prompt_side
        return prompt_return

    def _resolve_backend(ws):
        calls["backend"] += 1
        if backend_side is not None:
            raise backend_side
        if backend_return is not None:
            return backend_return
        return {"provider": "ollama", "model": "test-model"}

    def _build_invoker(ws, system, user_message_fn):
        calls["invoker_built"] += 1

        def invoke(brief):
            if invoke_side is not None:
                raise invoke_side
            return invoke_return
        return invoke

    utils_mod = types.ModuleType("runners.utils")
    utils_mod.load_system_prompt = _load_system_prompt
    utils_mod.resolve_backend = _resolve_backend

    runners_pkg = types.ModuleType("runners")
    runners_pkg.__path__ = []  # mark as package so submodule imports resolve

    runner_mod = types.ModuleType(f"runners.{FRAMEWORK}_runner")
    runner_mod.build_invoker = _build_invoker

    prompt_mod = types.ModuleType("auth_prompt")
    prompt_mod.user_message = lambda brief: f"user: {brief}"

    for name in list(sys.modules):
        if name == "run" or name.startswith("runners") or name in ("auth_harness", "auth_prompt"):
            del sys.modules[name]

    sys.modules["auth_harness"] = harness  # module-like object is fine for attr access
    sys.modules["auth_prompt"] = prompt_mod
    sys.modules["runners"] = runners_pkg
    sys.modules["runners.utils"] = utils_mod
    sys.modules[f"runners.{FRAMEWORK}_runner"] = runner_mod
    return harness, calls


def _load_run_module(*, fast_retry: bool = True):
    """Import the dispatcher fresh under the current stubs; zero backoff by default.

    fast_retry zeroes the retry backoff/jitter so tests that drive retry
    exhaustion don't actually sleep — behaviour is identical, just instant.
    """
    if "run" in sys.modules:
        del sys.modules["run"]
    spec = importlib.util.spec_from_file_location("run", RUN_PY)
    assert spec and spec.loader, "could not build import spec for run.py"
    mod = importlib.util.module_from_spec(spec)
    sys.modules["run"] = mod
    spec.loader.exec_module(mod)
    if fast_retry:
        mod._BACKOFF_BASE_S = 0.0
        mod._JITTER_S = 0.0
    return mod


# --------------------------------------------------------------------------- #
# Tests
# --------------------------------------------------------------------------- #
def test_module_constants_preserved():
    _install_stubs()
    run = _load_run_module()
    assert run.AGENT == EXPECTED_AGENT
    # Behaviour-preserving: prompt pointer is THIS framework's own subagent doc.
    assert run.SUBAGENT_MD.name == "test-authentication-flows.md"
    assert run.SUBAGENT_MD.parent.name == "subagent"


def test_prompt_pointer_unchanged():
    _install_stubs()
    run = _load_run_module()
    expected = (RUN_PY.resolve().parents[1] / "subagent" / "test-authentication-flows.md")
    assert run.SUBAGENT_MD == expected


def test_public_api_surface_preserved():
    _install_stubs()
    run = _load_run_module()
    for name in ("_build_invoker", "_prepare", "_make_generate", "main"):
        assert callable(getattr(run, name)), name


def test_validated_workspace_rejects_missing_dir():
    _install_stubs()
    run = _load_run_module()
    old = os.environ.get("FORGE_WORKSPACE")
    os.environ["FORGE_WORKSPACE"] = "/no/such/dir/xyzzy-forge"
    try:
        run._validated_workspace()
        assert False, "expected RuntimeError for non-existent workspace"
    except RuntimeError:
        pass
    finally:
        if old is None:
            os.environ.pop("FORGE_WORKSPACE", None)
        else:
            os.environ["FORGE_WORKSPACE"] = old


def test_validated_workspace_rejects_missing_subdir():
    # A dir that exists but lacks agents/common + scripts must be refused.
    import tempfile
    _install_stubs()
    run = _load_run_module()
    old = os.environ.get("FORGE_WORKSPACE")
    with tempfile.TemporaryDirectory() as td:
        os.environ["FORGE_WORKSPACE"] = td
        try:
            run._validated_workspace()
            assert False, "expected RuntimeError for missing required subdir"
        except RuntimeError:
            pass
        finally:
            if old is None:
                os.environ.pop("FORGE_WORKSPACE", None)
            else:
                os.environ["FORGE_WORKSPACE"] = old


def test_validated_workspace_rejects_overlong_path():
    # An over-long path triggers OSError in is_dir(); must degrade to RuntimeError.
    _install_stubs()
    run = _load_run_module()
    old = os.environ.get("FORGE_WORKSPACE")
    os.environ["FORGE_WORKSPACE"] = "/" + ("a" * 5000)
    try:
        run._validated_workspace()
        assert False, "expected RuntimeError for over-long workspace path"
    except RuntimeError:
        pass
    finally:
        if old is None:
            os.environ.pop("FORGE_WORKSPACE", None)
        else:
            os.environ["FORGE_WORKSPACE"] = old


def test_validated_workspace_accepts_real_tree():
    _install_stubs()
    run = _load_run_module()
    assert run._validated_workspace() == WS.resolve()


def test_ensure_import_paths_idempotent():
    _install_stubs()
    run = _load_run_module()
    common = str((WS / "agents" / "common").resolve())
    before = sys.path.count(common)     # already present from import
    run._ensure_import_paths(WS)
    run._ensure_import_paths(WS)
    assert sys.path.count(common) == before  # no duplicates added


def test_call_with_deadline_returns_value():
    _install_stubs()
    run = _load_run_module()
    assert run._call_with_deadline(lambda: 42, 5.0, "x") == 42


def test_call_with_deadline_propagates_error():
    _install_stubs()
    run = _load_run_module()

    def boom():
        raise ValueError("inner")

    try:
        run._call_with_deadline(boom, 5.0, "x")
        assert False, "expected inner error to propagate"
    except ValueError:
        pass


def test_call_with_deadline_times_out():
    import time as _t
    _install_stubs()
    run = _load_run_module()
    try:
        run._call_with_deadline(lambda: _t.sleep(2), 0.05, "slow")
        assert False, "expected TimeoutError"
    except TimeoutError:
        pass


def test_call_with_deadline_shuts_down_executor_on_timeout():
    # On timeout the executor must be shut down (bounded cleanup, no orphan pool).
    import concurrent.futures as _cf
    import time as _t
    _install_stubs()
    run = _load_run_module()
    created = []
    orig = _cf.ThreadPoolExecutor

    class _TrackedExecutor(orig):  # type: ignore[misc,valid-type]
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.shutdown_called = False
            created.append(self)

        def shutdown(self, *a, **k):
            self.shutdown_called = True
            return super().shutdown(*a, **k)

    run.concurrent.futures.ThreadPoolExecutor = _TrackedExecutor
    try:
        try:
            run._call_with_deadline(lambda: _t.sleep(2), 0.05, "slow")
            assert False, "expected TimeoutError"
        except TimeoutError:
            pass
    finally:
        run.concurrent.futures.ThreadPoolExecutor = orig
    assert created and all(e.shutdown_called for e in created)   # cleanup enforced


def test_call_with_deadline_shuts_down_executor_on_success():
    # The executor must also be shut down on the normal (success) path.
    import concurrent.futures as _cf
    _install_stubs()
    run = _load_run_module()
    created = []
    orig = _cf.ThreadPoolExecutor

    class _TrackedExecutor(orig):  # type: ignore[misc,valid-type]
        def __init__(self, *a, **k):
            super().__init__(*a, **k)
            self.shutdown_called = False
            created.append(self)

        def shutdown(self, *a, **k):
            self.shutdown_called = True
            return super().shutdown(*a, **k)

    run.concurrent.futures.ThreadPoolExecutor = _TrackedExecutor
    try:
        assert run._call_with_deadline(lambda: 7, 5.0, "ok") == 7
    finally:
        run.concurrent.futures.ThreadPoolExecutor = orig
    assert created and all(e.shutdown_called for e in created)


def test_run_step_returns_value_no_retry():
    _install_stubs()
    run = _load_run_module()
    calls = {"n": 0}

    def once():
        calls["n"] += 1
        return "ok"

    assert run._run_step(once, label="x", deadline=5.0, request_id="rid") == "ok"
    assert calls["n"] == 1


def test_run_step_recovers_after_transient_fault():
    _install_stubs()
    run = _load_run_module()
    state = {"n": 0}

    def flaky():
        state["n"] += 1
        if state["n"] < 2:
            raise ConnectionError("blip")
        return "ok"

    assert run._run_step(flaky, label="x", deadline=5.0, request_id="rid",
                         retries=run._RETRIES) == "ok"
    assert state["n"] == 2


def test_run_step_exhausts_and_raises():
    # _run_step must re-raise after exhausting the retry budget (retries+1 calls).
    _install_stubs()
    run = _load_run_module()
    state = {"n": 0}

    def always_fail():
        state["n"] += 1
        raise ConnectionError("down")

    try:
        run._run_step(always_fail, label="x", deadline=5.0, request_id="rid",
                      retries=run._RETRIES)
        assert False, "expected ConnectionError after exhausting retries"
    except ConnectionError:
        pass
    assert state["n"] == run._RETRIES + 1     # one initial + _RETRIES retries


def test_retry_backoff_has_jitter():
    # The jitter constant must be a positive, additive component of the backoff.
    _install_stubs()
    run = _load_run_module(fast_retry=False)
    assert run._JITTER_S > 0 and run._BACKOFF_BASE_S > 0


def test_prepare_wires_prompt_backend_invoker():
    harness, calls = _install_stubs()
    run = _load_run_module()
    invoke = run._prepare("rid")
    assert callable(invoke)
    assert calls["backend"] == 1          # backend resolved for observability
    assert calls["invoker_built"] == 1    # invoker built from the loaded prompt


def test_prepare_retries_transient_backend_fault():
    # A transient resolve_backend fault must be retried, not fail the run.
    calls = {"n": 0}
    harness = _FakeHarness()

    def _load_system_prompt(subagent_md, primary_fn=None):
        return "SYSTEM PROMPT BODY"

    def _resolve_backend(ws):
        calls["n"] += 1
        if calls["n"] < 2:
            raise ConnectionError("backend starting")
        return {"provider": "ollama", "model": "m"}

    utils_mod = types.ModuleType("runners.utils")
    utils_mod.load_system_prompt = _load_system_prompt
    utils_mod.resolve_backend = _resolve_backend
    runners_pkg = types.ModuleType("runners")
    runners_pkg.__path__ = []
    runner_mod = types.ModuleType(f"runners.{FRAMEWORK}_runner")
    runner_mod.build_invoker = lambda ws, system, umf: (lambda brief: "{}")
    prompt_mod = types.ModuleType("auth_prompt")
    prompt_mod.user_message = lambda brief: brief
    for name in list(sys.modules):
        if name == "run" or name.startswith("runners") or name in ("auth_harness", "auth_prompt"):
            del sys.modules[name]
    sys.modules["auth_harness"] = harness
    sys.modules["auth_prompt"] = prompt_mod
    sys.modules["runners"] = runners_pkg
    sys.modules["runners.utils"] = utils_mod
    sys.modules[f"runners.{FRAMEWORK}_runner"] = runner_mod

    run = _load_run_module()
    invoke = run._prepare("rid")
    assert callable(invoke)
    assert calls["n"] == 2               # first failed, retry succeeded


def test_prepare_rejects_empty_prompt():
    _install_stubs(prompt_return="   ")   # blank prompt -> hard config error
    run = _load_run_module()
    try:
        run._prepare("rid")
        assert False, "expected RuntimeError for empty prompt"
    except RuntimeError:
        pass


def test_prepare_rejects_non_str_prompt():
    _install_stubs(prompt_return=12345)   # non-string prompt -> hard config error
    run = _load_run_module()
    try:
        run._prepare("rid")
        assert False, "expected RuntimeError for non-string prompt"
    except RuntimeError:
        pass


def test_prepare_rejects_non_dict_backend():
    _install_stubs(backend_return="not-a-dict")
    run = _load_run_module()
    try:
        run._prepare("rid")
        assert False, "expected RuntimeError for non-dict backend spec"
    except RuntimeError:
        pass


def test_build_invoker_returns_callable():
    _install_stubs()
    run = _load_run_module()
    assert callable(run._build_invoker("SYSTEM"))


def test_generate_returns_extracted_plan():
    harness, _ = _install_stubs()
    run = _load_run_module()
    gen = run._make_generate(lambda brief: "raw", "brief", "rid")
    assert gen() == harness.extract_return   # parsed plan handed through unchanged


def test_generate_degrades_on_invoke_fault():
    # Transient model/network fault must degrade to an empty plan, not raise.
    _install_stubs()
    run = _load_run_module()

    def boom(brief):
        raise ConnectionError("backend reset")

    gen = run._make_generate(boom, "brief", "rid")
    assert gen() == {}                       # never a silent success


def test_generate_degrades_on_parse_fault():
    # extract_json raising on pathological output must be caught, not propagate.
    harness, _ = _install_stubs()
    harness.extract_side = MemoryError("pathological body")
    run = _load_run_module()
    gen = run._make_generate(lambda brief: "x" * 100, "brief", "rid")
    assert gen() == {}


def test_generate_caps_oversized_response():
    # A multi-MB response must be truncated before parsing and still yield a plan.
    harness, _ = _install_stubs()
    seen = {"len": None}

    def _capture(text):
        seen["len"] = len(text)
        return harness.extract_return

    harness.extract_json = _capture
    run = _load_run_module()
    big = "{" + "a" * (2 << 20) + "}"
    gen = run._make_generate(lambda brief: big, "brief", "rid")
    assert gen() == harness.extract_return
    assert seen["len"] == run._MAX_RAW_BYTES   # parser saw EXACTLY the cap, no more


def test_generate_degrades_on_unparseable_output():
    harness, _ = _install_stubs()
    harness.extract_return = None            # extract_json -> None (no JSON found)
    run = _load_run_module()
    gen = run._make_generate(lambda brief: "not json", "brief", "rid")
    assert gen() == {}


def test_generate_degrades_on_empty_dict_output():
    # extract_json -> {} (falsy dict) must degrade via the `not plan` branch.
    harness, _ = _install_stubs()
    harness.extract_return = {}
    run = _load_run_module()
    gen = run._make_generate(lambda brief: "{}", "brief", "rid")
    assert gen() == {}


def test_generate_degrades_on_non_dict_output():
    harness, _ = _install_stubs()
    harness.extract_return = ["not", "a", "dict"]
    run = _load_run_module()
    gen = run._make_generate(lambda brief: "[]", "brief", "rid")
    assert gen() == {}


def test_field_handles_broken_str():
    # A value whose __str__ raises must degrade to a safe placeholder, not throw.
    _install_stubs()
    run = _load_run_module()

    class _Bad:
        def __str__(self):
            raise RuntimeError("boom")

    assert run._field(_Bad()) == "<unrenderable>"


def test_field_truncates_huge_value():
    _install_stubs()
    run = _load_run_module()
    out = run._field("Z" * 100000)
    assert len(out) == run._MAX_FIELD_CHARS + 1 and out.endswith("…")


def test_field_boundary_exact_max_kept_verbatim():
    # A value EXACTLY _MAX_FIELD_CHARS long must be kept verbatim (guards the
    # <= boundary: flipping to < would wrongly truncate this exact-length value).
    _install_stubs()
    run = _load_run_module()
    exact = "Z" * run._MAX_FIELD_CHARS
    out = run._field(exact)
    assert out == exact and not out.endswith("…")


def test_field_boundary_one_over_max_truncated():
    # One char over the cap must truncate to _MAX_FIELD_CHARS + ellipsis.
    _install_stubs()
    run = _load_run_module()
    over = "Z" * (run._MAX_FIELD_CHARS + 1)
    out = run._field(over)
    assert len(out) == run._MAX_FIELD_CHARS + 1 and out.endswith("…")
    assert out[:-1] == "Z" * run._MAX_FIELD_CHARS


def test_emit_summary_prints_exact_line():
    _install_stubs()
    run = _load_run_module()
    buf = io.StringIO()
    with redirect_stdout(buf):
        run._emit_summary(dict(_SUMMARY), "rid")
    assert buf.getvalue().strip() == _EXPECTED_LINE


def test_emit_summary_tolerates_malformed_summary():
    # A None/non-dict summary must not raise; fields fall back to "?".
    _install_stubs()
    run = _load_run_module()
    buf = io.StringIO()
    with redirect_stdout(buf):
        run._emit_summary(None, "rid")
    out = buf.getvalue().strip()
    assert out.startswith(f"[{EXPECTED_AGENT}] pass_rate=?%") and "executed=?" in out


def test_emit_summary_tolerates_broken_str_value():
    # A summary field with a broken __str__ must not stop the headline emitting.
    _install_stubs()
    run = _load_run_module()

    class _Bad:
        def __str__(self):
            raise RuntimeError("boom")

    bad = dict(_SUMMARY)
    bad["executed_cases"] = _Bad()
    buf = io.StringIO()
    with redirect_stdout(buf):
        run._emit_summary(bad, "rid")
    out = buf.getvalue().strip()
    assert out.startswith(f"[{EXPECTED_AGENT}]") and "executed=<unrenderable>" in out


def test_emit_summary_caps_pathological_field():
    # A pathological huge field value must be truncated, not blow up the headline.
    _install_stubs()
    run = _load_run_module()
    bad = dict(_SUMMARY)
    bad["executed_cases"] = "Z" * 10000
    buf = io.StringIO()
    with redirect_stdout(buf):
        run._emit_summary(bad, "rid")
    out = buf.getvalue().strip()
    assert len(out) < 300 and "executed=" in out   # bounded output


def test_log_swallows_broken_logging_infra():
    # A logging stack that raises must NOT propagate out of _log (telemetry != flow).
    _install_stubs()
    run = _load_run_module()
    import logging as _logging

    def _explode(*a, **k):
        raise RuntimeError("logging is down")

    orig = run.log.log
    run.log.log = _explode
    try:
        run._log(_logging.INFO, "anything %s", "x")   # must NOT raise
    finally:
        run.log.log = orig


def test_emit_summary_emits_headline_despite_broken_logging():
    # Even if every log call raises, the committed headline must still be printed.
    _install_stubs()
    run = _load_run_module()

    def _explode(*a, **k):
        raise RuntimeError("logging is down")

    orig = run.log.log
    run.log.log = _explode
    buf = io.StringIO()
    try:
        with redirect_stdout(buf):
            run._emit_summary(dict(_SUMMARY), "rid")   # must not raise
    finally:
        run.log.log = orig
    assert buf.getvalue().strip() == _EXPECTED_LINE     # headline still emitted


def test_emit_summary_returns_when_print_stream_broken():
    # A broken stdout must be caught: _emit_summary returns normally, logs 'done'.
    _install_stubs()
    run = _load_run_module()
    records = []

    def _capture(level, msg, *args):
        records.append(msg % args if args else msg)

    orig = run._log
    run._log = _capture

    class _BrokenIO(io.StringIO):
        def write(self, s):
            raise OSError("broken pipe")

    try:
        with redirect_stdout(_BrokenIO()):
            run._emit_summary(dict(_SUMMARY), "rid")   # must not raise
    finally:
        run._log = orig
    assert any("done" in r for r in records)            # done log still ran


def test_main_runs_full_workflow_and_prints_exact_line():
    # End-to-end (stubbed): main() elicits a plan, hands it over, prints headline.
    harness, calls = _install_stubs()
    run = _load_run_module()
    buf = io.StringIO()
    with redirect_stdout(buf):
        run.main()
    assert harness.brief_calls == 1
    assert harness.captured_plan == harness.extract_return
    assert calls["invoker_built"] == 1
    assert buf.getvalue().strip() == _EXPECTED_LINE   # exact emitted contract


def test_main_missing_prompt_propagates():
    # A totally-missing prompt is a hard config error: it must surface, not hide.
    _install_stubs(prompt_side=FileNotFoundError("no prompt doc"))
    run = _load_run_module()
    try:
        run.main()
        assert False, "expected FileNotFoundError to propagate"
    except FileNotFoundError:
        pass


def test_main_down_backend_propagates():
    # A permanently-unresolvable backend (exhausts retries) surfaces (fail loud).
    _install_stubs(backend_side=RuntimeError("no backend reachable"))
    run = _load_run_module()
    try:
        run.main()
        assert False, "expected RuntimeError to propagate"
    except RuntimeError:
        pass


def test_main_transient_model_fault_still_completes():
    # If only the model call is flaky, the run must COMPLETE with an empty plan
    # recorded — the harness turns that into an explicit failing case.
    harness, _ = _install_stubs(invoke_side=TimeoutError("model timed out"))
    run = _load_run_module()
    buf = io.StringIO()
    with redirect_stdout(buf):
        run.main()
    assert harness.captured_plan == {}       # degraded, run still finished
    assert buf.getvalue().strip() == _EXPECTED_LINE


def test_main_scheme_brief_failure_degrades_and_emits():
    # scheme_brief failure now DEGRADES (empty brief) — run continues + emits.
    harness, _ = _install_stubs()
    harness.brief_side = RuntimeError("brief failed")
    run = _load_run_module()
    buf = io.StringIO()
    with redirect_stdout(buf):
        run.main()
    # Harness still ran with the empty brief and returned the summary -> headline.
    assert buf.getvalue().strip() == _EXPECTED_LINE


def test_main_harness_not_retried_on_success():
    # run_auth_test persists results + calls generate -> non-idempotent -> called
    # EXACTLY once on the happy path (no accidental duplicate persist).
    harness, _ = _install_stubs()
    run = _load_run_module()
    buf = io.StringIO()
    with redirect_stdout(buf):
        run.main()
    assert harness.run_calls == 1
    assert buf.getvalue().strip() == _EXPECTED_LINE


def test_main_harness_failure_not_retried_no_duplicate_persist():
    # If run_auth_test fails, it must NOT be retried (retrying a non-idempotent
    # persist risks duplicate/corrupt records) — called exactly once, then the
    # run degrades to a still-emitted headline (data-integrity lens).
    harness, _ = _install_stubs()
    harness.run_side = RuntimeError("harness exploded")
    run = _load_run_module()
    buf = io.StringIO()
    with redirect_stdout(buf):
        run.main()
    out = buf.getvalue().strip()
    assert out.startswith(f"[{EXPECTED_AGENT}] pass_rate=?%")   # degraded headline
    assert harness.run_calls == 1                               # NOT retried


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
        except Exception as e:  # noqa: BLE001 -- report unexpected errors as failures
            failed += 1
            print(f"ERROR {t.__name__}: {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
