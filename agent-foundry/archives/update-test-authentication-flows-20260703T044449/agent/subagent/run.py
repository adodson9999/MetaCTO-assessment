#!/usr/bin/env python3
"""Hardened thin dispatcher: subagent runner for api-tester-test-authentication-flows.

Behaviour (unchanged, per the agent contract):
    load system prompt  ->  resolve backend  ->  build framework invoker  ->
    hand the generated auth PLAN to the shared deterministic ``auth_harness``.

The agent stays purely generative: this module NEVER sends an HTTP auth request
and NEVER alters the plan/contract the model emits. The system prompt is loaded
from THIS framework's own ``subagent/api-tester-test-authentication-flows.md`` so the emitted
plan is byte-for-byte identical to the pre-hardening dispatcher; only the CODE
around it is hardened.

The four sibling framework dispatchers apply this SAME structure so they stay
consistent — the only per-framework differences are AGENT, the runner import,
and _build_invoker. Resilience/observability design:
  * The workspace root that seeds sys.path is validated (real dir containing the
    foundry's import dirs) with every fs probe wrapped, so a hostile/over-long
    FORGE_WORKSPACE degrades to a clear error, never an uncaught OSError.
  * ALL logging goes through ``_log``, which swallows any failure of the logging
    infrastructure itself — a broken handler can never derail control flow, skip
    the headline, or drop the ``done`` record.
  * Every blocking boundary runs through ``_run_step``: a wall-clock deadline
    (enforced via a ThreadPoolExecutor future so the timed-out worker is left in
    a bounded, explicitly-shut-down pool rather than leaked), plus structured
    start/success/failure logging with the per-run request id and duration.
  * Retry policy is idempotency-aware: only the SAFE, side-effect-free setup
    reads (load_system_prompt, resolve_backend) retry. The model call and
    ``run_auth_test`` (which persists results + calls generate) are NOT retried,
    so a transient blip can never duplicate or corrupt a persisted record.
  * The run NEVER crashes past setup: a brief/harness fault degrades to a still-
    emitted headline, so results are always observable from telemetry alone and
    secrets never leak (exception TYPE only is logged, never its message).

stdlib + already-imported foundry deps only.
"""
from __future__ import annotations

import concurrent.futures
import logging
import os
import random
import sys
import threading
import time
import uuid
from pathlib import Path
from typing import Callable, Dict, List, Optional, TypeVar

_T = TypeVar("_T")

# Wall-clock ceilings (seconds). Generous vs. real latency yet finite, so a hung
# dependency surfaces as a TimeoutError the caller handles rather than a wedge.
_SETUP_DEADLINE_S = 60.0
_HARNESS_DEADLINE_S = 900.0
# Bounded, jittered retry for the IDEMPOTENT setup reads only. Jitter de-syncs
# concurrent dispatchers so they don't retry in lockstep. Non-idempotent steps
# (model call, run_auth_test persist) pass retries=0 — see main().
_RETRIES = 2
_BACKOFF_BASE_S = 0.5
_JITTER_S = 0.25
# Cap the untrusted model response fed to the JSON parser (memory / adversarial).
_MAX_RAW_BYTES = 1 << 20  # 1 MiB is far above any legitimate auth plan.
# Cap any single field rendered into the headline (adversarial-input).
_MAX_FIELD_CHARS = 64


def _log(level: int, msg: str, *args: object) -> None:
    """Emit one log record, swallowing any failure of the logging stack itself.

    Logging is telemetry, never control flow: a broken/misconfigured handler
    (full disk, closed stream, formatting error) must NEVER raise into the caller
    and skip a headline emission or a ``done`` record. Every log call in this
    module goes through here so no logging fault can derail the run
    (error-handling-resilience lens).
    """
    try:
        log.log(level, msg, *args)
    except Exception:  # noqa: BLE001 -- logging must never break the run
        pass


def _call_with_deadline(fn: Callable[[], _T], seconds: float, label: str) -> _T:
    """Run *fn* under a wall-clock deadline; raise TimeoutError if it overruns.

    Uses a single-worker ``ThreadPoolExecutor`` and ``future.result(timeout)`` so
    the timeout has EXPLICIT, bounded cleanup semantics: on overrun we cancel the
    future and ``shutdown(wait=False)`` the pool, so the stray worker lives in a
    known, garbage-collectable executor (one per call, bounded blast radius) —
    not an orphaned free-floating thread. The worker itself only runs a bounded
    model/network/file call whose OWN socket/IO timeout releases its resources
    shortly after, so nothing leaks past that; this deadline is the guaranteed
    outer bound (error-handling-resilience lens).
    """
    executor = concurrent.futures.ThreadPoolExecutor(
        max_workers=1, thread_name_prefix=f"deadline-{label}")
    future = executor.submit(fn)
    try:
        return future.result(timeout=seconds)
    except concurrent.futures.TimeoutError:
        future.cancel()
        raise TimeoutError(f"{label} exceeded {seconds:.0f}s deadline")
    finally:
        # wait=False: never block the run on a wedged worker; the pool + its one
        # thread are reclaimed once fn's own IO timeout unblocks it.
        executor.shutdown(wait=False)


def _run_step(fn: Callable[[], _T], *, label: str, deadline: float,
              request_id: str, retries: int = 0) -> _T:
    """Run one boundary step: deadline + jittered retry + start/success/fail log.

    This is the single observability+resilience choke point every blocking call
    goes through, so success (with duration) and failure (exception TYPE only, to
    avoid leaking backend hostnames/secrets) are ALWAYS logged with the request
    id. Retry is caller-controlled and MUST be 0 for non-idempotent steps; the
    final failure is logged and re-raised for the caller to handle.
    """
    _log(logging.INFO, "[%s:%s] %s: start", AGENT, request_id, label)
    started = time.monotonic()
    for attempt in range(retries + 1):
        try:
            result = _call_with_deadline(fn, deadline, label)
            _log(logging.INFO, "[%s:%s] %s: ok in %.2fs", AGENT, request_id, label,
                 time.monotonic() - started)
            return result
        except Exception as exc:  # noqa: BLE001 -- retry transient, else log + re-raise
            if attempt < retries:
                delay = _BACKOFF_BASE_S * (2 ** attempt) + random.uniform(0, _JITTER_S)
                _log(logging.WARNING, "[%s:%s] %s failed (%s); retry %d/%d in %.2fs",
                     AGENT, request_id, label, type(exc).__name__,
                     attempt + 1, retries, delay)
                time.sleep(delay)
                continue
            _log(logging.ERROR, "[%s:%s] %s failed (%s) after %.2fs", AGENT,
                 request_id, label, type(exc).__name__, time.monotonic() - started)
            raise
    raise RuntimeError(f"unreachable retry exit for {label}")  # pragma: no cover


def _validated_workspace() -> Path:
    """Return the foundry root, refusing an env value that isn't the real tree.

    FORGE_WORKSPACE seeds ``sys.path``; treating it as trusted would let anyone
    who controls the environment plant a fake ``auth_harness`` and get it
    imported. We resolve it and require an existing directory containing the exact
    import dirs we will add. Every filesystem probe is wrapped so a hostile value
    (e.g. a >4096-char path that overflows the OS limit) degrades to a clear
    RuntimeError instead of an uncaught OSError at import (adversarial-input).
    Default (env unset) is the packaged location, preserving prior behaviour.
    """
    default = Path(__file__).resolve().parents[4]
    raw = os.environ.get("FORGE_WORKSPACE") or str(default)
    try:
        root = Path(raw).resolve()
        if not root.is_dir():
            raise RuntimeError(f"FORGE_WORKSPACE {raw!r} is not an existing directory")
        for sub in (root / "agents" / "common", root / "scripts"):
            if not sub.is_dir():
                raise RuntimeError(f"FORGE_WORKSPACE {root} missing import dir {sub}")
    except OSError as exc:  # over-long/unstat-able path -> clear error, never a crash
        raise RuntimeError(f"FORGE_WORKSPACE {raw!r} is unusable: {type(exc).__name__}") from exc
    return root


# sys.path AND the logger's handler list are process-global mutable state; one
# lock makes both check-then-act sequences atomic so concurrent imports across
# forge phases can't race, duplicate a path, or double-attach a handler.
_STATE_LOCK = threading.Lock()


def _ensure_import_paths(root: Path) -> None:
    """Add the foundry's import dirs to sys.path once, atomically, as absolutes.

    Absolute (resolved) paths mean a relative FORGE_WORKSPACE can't slip a
    second, differently-spelled copy of the same dir onto sys.path across runs;
    the lock closes the check-then-act race between concurrent imports.
    """
    paths: List[str] = [str((root / "agents" / "common").resolve()),
                        str((root / "scripts").resolve())]
    with _STATE_LOCK:
        for p in paths:
            if p not in sys.path:
                sys.path.insert(0, p)


WS = _validated_workspace()
_ensure_import_paths(WS)

import auth_harness  # noqa: E402
from auth_prompt import user_message  # noqa: E402
from runners.utils import load_system_prompt, resolve_backend  # noqa: E402
from runners.subagent_runner import build_invoker  # noqa: E402

# Module logger. The NullHandler check-then-add is done under _STATE_LOCK so
# concurrent imports never double-attach a handler (concurrency lens).
log = logging.getLogger(__name__)
with _STATE_LOCK:
    if not any(isinstance(h, logging.NullHandler) for h in log.handlers):
        log.addHandler(logging.NullHandler())

# Framework label recorded in every result artifact. Original literal preserved
# so the emitted contract (agent field, result filename) is unchanged.
AGENT = "api-tester-test-authentication-flows"
# This framework's OWN system-prompt file — behaviour-preserving: the plan the
# model emits is driven by this exact doc, as before hardening.
SUBAGENT_MD = Path(__file__).resolve().parents[1] / "subagent" / "api-tester-test-authentication-flows.md"

# The four headline metric keys the harness returns; validated before the print
# so a malformed summary is a logged, explicit failure rather than a KeyError.
_SUMMARY_KEYS = ("auth_flow_pass_rate_pct", "false_acceptance_rate_pct",
                 "false_rejection_rate_pct", "executed_cases")


def _build_invoker(system: str) -> Callable[[str], str]:
    """Per-framework seam: wire this framework's runner into an ``invoke(brief)``.

    This is the ONE line that differs across the four dispatchers (the runner
    import). The model call is run under a deadline in _make_generate, so a
    stalled network can never hang the run even if the runner sets no timeout.
    """
    return build_invoker(WS, system, user_message)


def _prepare(request_id: str) -> Callable[[str], str]:
    """Load prompt, log backend, build the invoker; log then re-raise on fault.

    load_system_prompt and resolve_backend are IDEMPOTENT reads, so they retry
    (deadline + jittered backoff) to ride out a transient blip. build_invoker has
    no external side effect either. Prompt/backend values are validated (non-empty
    str / dict) so a degraded dependency return can't crash later with a
    Type/AttributeError. Setup faults are re-raised: a broken environment must
    fail loudly, and _run_step has already logged the reason at ERROR.
    """
    system = _run_step(lambda: load_system_prompt(SUBAGENT_MD), label="load_prompt",
                       deadline=_SETUP_DEADLINE_S, request_id=request_id, retries=_RETRIES)
    if not isinstance(system, str) or not system.strip():
        raise RuntimeError(f"empty/invalid system prompt from {SUBAGENT_MD}")
    spec = _run_step(lambda: resolve_backend(WS), label="resolve_backend",
                     deadline=_SETUP_DEADLINE_S, request_id=request_id, retries=_RETRIES)
    if not isinstance(spec, dict):
        raise RuntimeError("resolve_backend returned a non-dict spec")
    _log(logging.INFO, "[%s:%s] backend provider=%s model=%s", AGENT, request_id,
         spec.get("provider"), spec.get("model"))
    return _run_step(lambda: _build_invoker(system), label="build_invoker",
                     deadline=_SETUP_DEADLINE_S, request_id=request_id, retries=_RETRIES)


def _make_generate(invoke: Callable[[str], str], brief: str,
                   request_id: str) -> Callable[[], Dict]:
    """Wrap the model call so any elicitation fault degrades to an empty plan.

    The model call runs under a deadline (NOT retried — it is non-idempotent); its
    output is size-capped before the untrusted-JSON parse (so a multi-MB body
    can't exhaust memory); a timeout/connection/parse fault degrades to {} (the
    harness records an explicit failing case — never a silent success). Success is
    logged WITH duration; only exception TYPE is logged so secrets never leak.
    """
    def generate() -> Dict:
        started = time.monotonic()
        try:
            raw = _call_with_deadline(lambda: invoke(brief), _HARNESS_DEADLINE_S, "invoke")
            if isinstance(raw, str) and len(raw) > _MAX_RAW_BYTES:
                _log(logging.WARNING, "[%s:%s] model response %d bytes > cap; truncating",
                     AGENT, request_id, len(raw))
                raw = raw[:_MAX_RAW_BYTES]
            plan = auth_harness.extract_json(raw)
        except Exception as exc:  # noqa: BLE001 -- model/network/parse fault -> empty plan
            _log(logging.WARNING, "[%s:%s] plan elicitation failed (%s); empty plan",
                 AGENT, request_id, type(exc).__name__)
            return {}
        if not isinstance(plan, dict) or not plan:
            _log(logging.WARNING, "[%s:%s] no usable JSON plan; empty plan", AGENT, request_id)
            return {}
        schemes = plan.get("schemes")
        n = len(schemes) if isinstance(schemes, list) else 0
        _log(logging.INFO, "[%s:%s] plan elicited in %.2fs (%d schemes)", AGENT,
             request_id, time.monotonic() - started, n)
        return plan
    return generate


def _field(value: object) -> str:
    """Render one summary value as a bounded, single-line string (adversarial).

    A harness value could carry a pathological ``__str__`` (huge output or one
    that raises); we coerce under guard and truncate to a small cap so it can
    never blow up or hang the headline/log. A value whose rendered length is
    EXACTLY _MAX_FIELD_CHARS is kept verbatim (``<=``); only a strictly longer one
    is truncated with an ellipsis marker. On any failure the field degrades to a
    safe placeholder rather than propagating.
    """
    try:
        text = str(value)[:_MAX_FIELD_CHARS + 1]
    except Exception:  # noqa: BLE001 -- broken __str__ must never break the headline
        return "<unrenderable>"
    return text if len(text) <= _MAX_FIELD_CHARS else text[:_MAX_FIELD_CHARS] + "…"


def _emit_summary(summary: object, request_id: str) -> None:
    """Emit the headline line + a structured metric log, tolerating any summary.

    The headline is the run's committed result, so NOTHING may prevent it: every
    log call routes through ``_log`` (which can't raise), and the headline print
    runs in its own guarded block so a broken stream can't propagate either. A
    None/non-dict/pathological summary degrades to "?"/placeholder fields. This
    function returns normally on every input and logging state (resilience lens).
    """
    data = summary if isinstance(summary, dict) else {}
    if not data:
        _log(logging.ERROR, "[%s:%s] harness returned no summary dict", AGENT, request_id)
    vals = {k: _field(data.get(k, "?")) for k in _SUMMARY_KEYS}
    _log(logging.INFO, "[%s:%s] metrics pass_rate=%s far=%s frr=%s executed=%s",
         AGENT, request_id, vals["auth_flow_pass_rate_pct"],
         vals["false_acceptance_rate_pct"], vals["false_rejection_rate_pct"],
         vals["executed_cases"])
    try:
        print(f"[{AGENT}] pass_rate={vals['auth_flow_pass_rate_pct']}% "
              f"FAR={vals['false_acceptance_rate_pct']}% "
              f"FRR={vals['false_rejection_rate_pct']}% "
              f"executed={vals['executed_cases']}")
    except Exception as exc:  # noqa: BLE001 -- a broken stdout must not fail the run
        _log(logging.ERROR, "[%s:%s] headline print failed (%s)", AGENT,
             request_id, type(exc).__name__)
    _log(logging.INFO, "[%s:%s] done; executed=%s", AGENT, request_id,
         vals["executed_cases"])


def _generate_brief(request_id: str) -> str:
    """Build the scheme brief; degrade to an empty brief on any fault.

    Brief generation must never take the run down (chaos-engineering): it runs via
    ``_run_step`` (deadline + structured logging) and is an idempotent read, so it
    may retry. On timeout/failure we log and return "" so the harness still runs
    and records explicit failing cases, and the headline still emits.
    """
    try:
        return _run_step(auth_harness.scheme_brief, label="scheme_brief",
                         deadline=_SETUP_DEADLINE_S, request_id=request_id, retries=_RETRIES)
    except Exception as exc:  # noqa: BLE001 -- degrade to empty brief, run continues
        _log(logging.ERROR, "[%s:%s] scheme_brief failed (%s); using empty brief",
             AGENT, request_id, type(exc).__name__)
        return ""


def main() -> None:
    """Public entrypoint (PRESERVED): run the auth test and print the headline.

    ``run_auth_test`` is NON-IDEMPOTENT — it calls generate() and PERSISTS the
    results (writes result/case files). It is therefore run with retries=0: a
    transient fault degrades to a still-emitted headline rather than re-running
    and risking a duplicate or corrupt persisted record (data-integrity lens).
    The harness owns its own internal resilience. Emits the SAME headline line as
    before hardening.
    """
    request_id = uuid.uuid4().hex[:8]
    _log(logging.INFO, "[%s:%s] dispatch start; workspace=%s", AGENT, request_id, WS)
    invoke = _prepare(request_id)
    brief = _generate_brief(request_id)
    generate = _make_generate(invoke, brief, request_id)
    summary: Optional[Dict] = None
    try:
        summary = _run_step(lambda: auth_harness.run_auth_test(AGENT, generate),
                            label="run_auth_test", deadline=_HARNESS_DEADLINE_S,
                            request_id=request_id, retries=0)  # non-idempotent: never retry
    except Exception:  # noqa: BLE001 -- already logged by _run_step; still emit headline
        summary = None
    _emit_summary(summary, request_id)


if __name__ == "__main__":
    main()

# --- Contract-oracle rollout (plan 40): hard guardrail carried in every prompt copy ---
# ## Contract-conformance oracle & deviation findings (hard guardrail)
#
# Your expected outcome for every case is the UNIVERSAL HTTP/REST contract for that operation, read from
# `agent-foundry/references/contract-oracle.md` — NEVER the target's own documentation or observed
# behaviour. For each case emit `expected_by_contract` (the status + invariants from the contract table)
# and, only when the target's documented expectation differs, `expected_by_docs`. A separate
# deterministic harness fills `observed` and emits `deviations[]` — every case where observed differs
# from expected_by_contract, or where expected_by_docs differs from expected_by_contract — as findings,
# surfaced EVEN WHEN the response is acceptable by the target's own docs. Verify every effect BLACK-BOX by
# read-back (a follow-up request): a create is proven by a follow-up GET returning the resource, a delete
# by a follow-up GET returning 404, an update by a follow-up GET reflecting the change — never by a
# database row, log line, or injected instrumentation the target may not expose; where such an assertion
# is impossible black-box, degrade to the observable signal rather than skipping it. Repeat each case the
# configured soak count and flag any non-deterministic result as a deviation. Enumerate the FULL
# documented surface — every resource × every method, and every field/parameter including nested paths and
# date/range; a documented capability that is unimplemented (404 or ignored) is a `missing_capability`
# deviation. You MUST NOT encode the target's observed behaviour as the contract, and MUST NOT carry an
# `also_accept` that admits a deviation from a standard code (e.g. accepting 200 for a creation the
# contract fixes at 201); either is a hard-guardrail violation and fails closed.
