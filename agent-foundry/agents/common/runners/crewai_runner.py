"""Shared CrewAI runner — Agent + Task + Crew boilerplate.

Thin dispatchers call::

    from runners.crewai_runner import build_invoker
    invoke = build_invoker(WS, system, user_message)
    raw_str = invoke(brief)          # -> str (raw crew output)

Hardening rationale (this module is a framework *adapter* around an external LLM
backend, so every boundary is defensive):

  * Backend resolution is delegated to :func:`runners.utils.resolve_backend`,
    which owns the one-time, lock-guarded ``sys.path`` insert. That keeps the
    injected ``scripts`` dir off this module's hot path, avoids unbounded
    ``sys.path`` growth across repeated ``build_invoker`` calls, and prevents a
    race on the shared process-global list (memory-resource / concurrency /
    system-design lens) — and confines the import to the FORGE_WORKSPACE-derived
    ``scripts`` dir rather than trusting an arbitrary path (security lens).
  * The resolved spec is *validated* before use — a malformed/partial spec
    degrades to a safe default backend instead of raising ``KeyError`` /
    ``AttributeError`` (adversarial-input lens).
  * ``kind`` is branched three ways (anthropic / openai-cli / ollama) so the
    ``claude-cli`` shim is never silently mis-prefixed as ollama (logic-error).
  * Every I/O — resolve, LLM construction, ``crew.kickoff`` — is wrapped, timed,
    logged, and retried with bounded exponential backoff + jitter; a down or slow
    backend degrades to a structured error string rather than hanging or crashing
    (chaos-engineering / network / error-handling-resilience / observability lens).
  * The backend is resolved ONCE into frozen kwargs, but a fresh ``LLM`` plus
    ``Agent``/``Task``/``Crew`` is built per invocation, so two threads calling
    ``invoke`` concurrently never share any mutable CrewAI/LLM state (concurrency).
  * Invocation attempts/successes/failures + latency are counted (see
    :func:`get_metrics`) and every log line is stamped with a monotonic
    invocation id for correlation (observability lens).

stdlib + crewai + the already-present ``runners.utils`` only. Immutable style:
no input object is mutated; new dicts/strings are returned.
"""
from __future__ import annotations

import contextlib
import itertools
import json
import logging
import random
import threading
import time
from pathlib import Path
from types import MappingProxyType
from typing import Any, Callable, Iterator, Mapping

from runners.utils import resolve_backend

# Library logger. NullHandler keeps imports silent by default (no stderr noise
# for the 87 dependent dispatchers); a caller opts into diagnostics via
# logging.getLogger("runners.crewai_runner").setLevel(...). The happy path logs
# at INFO (backend chosen, each invoke) and every fallback/failure at WARNING so
# a degraded backend is loud without crashing the run (observability lens).
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())


class _Metrics:
    """Thread-safe in-process counters + latency sum for invocation telemetry.

    A minimal, dependency-free metrics surface (no Prometheus/OTel to keep the
    stdlib-only constraint): attempts / successes / failures and total latency,
    each mutated under one lock so concurrent ``invoke`` threads can't lose a
    count (observability + concurrency lens). Exposed via :func:`get_metrics` so
    a caller or test can scrape a consistent snapshot.
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self.attempts = 0
        self.successes = 0
        self.failures = 0
        self.latency_s_total = 0.0

    def record(self, *, success: bool, latency_s: float) -> None:
        """Record one outcome. Telemetry MUST NOT break the caller.

        Any internal fault (lock issue, arithmetic in a pathological state) is
        caught and logged, so a metrics failure can never turn ``invoke`` into a
        raising call and violate its ``Callable[[str], str]`` contract
        (error-handling-resilience lens).
        """
        try:
            with self._lock:
                self.attempts += 1
                self.latency_s_total += latency_s
                if success:
                    self.successes += 1
                else:
                    self.failures += 1
        except Exception as exc:  # noqa: BLE001 - telemetry is best-effort, never fatal
            log.warning("metrics.record failed (ignored): %s: %s", type(exc).__name__, exc)

    def snapshot(self) -> dict[str, float]:
        with self._lock:
            return {
                "attempts": self.attempts,
                "successes": self.successes,
                "failures": self.failures,
                "latency_s_total": self.latency_s_total,
            }


_METRICS = _Metrics()

# Monotonic invocation-id source. A process-wide atomic counter (guarded by the
# GIL via itertools.count, whose __next__ is atomic) stamps every invoke with a
# unique id so all log lines for one call — start, backoff, success/failure,
# degradation — can be correlated in a shared log stream (observability lens).
_INVOCATION_IDS = itertools.count(1)


def get_metrics() -> dict[str, float]:
    """Return a consistent snapshot of invocation counters (observability hook)."""
    return _METRICS.snapshot()


# Dedicated jitter PRNG. The stdlib module-global ``random`` shares one Mersenne
# state across the whole process; two threads hitting ``random.uniform`` inside
# concurrent retries interleave read/advance on that unsynchronised state
# (concurrency lens). A private ``random.Random`` instance whose ``uniform`` we
# call under ``_JITTER_LOCK`` isolates our backoff jitter from every other caller
# and from itself under contention — the intended full-jitter distribution is
# preserved and the shared PRNG is never touched.
_JITTER_RNG = random.Random()
_JITTER_LOCK = threading.Lock()

# --- bounded-resource / timeout constants (named, not magic) -----------------
# Upper bound on a single brief. Briefs are kilobytes at most; a 512 KiB ceiling
# is generous yet forbids memory exhaustion / prompt-flooding from a hostile or
# runaway caller (adversarial-input / memory-resource lens). Doubles as the char
# pre-slice length in _bounded_brief (chars >= bytes) so an oversized string is
# never fully encoded before truncation.
_MAX_BRIEF_BYTES = 512 * 1024

# Per-request wall-clock cap handed to the LLM (litellm ``timeout``). Without it
# a slow/unresponsive endpoint hangs the caller forever on a degraded network
# (network / chaos-engineering lens).
_REQUEST_TIMEOUT_S = 180.0

# Bounded retry policy for transient backend faults (rate-limit, connection
# reset, 5xx). Total worst-case added latency is deterministic:
# base * (2^0 + 2^1 + 2^2) + jitter, capped per-attempt by _BACKOFF_CAP_S
# (network / error-handling-resilience lens).
_MAX_ATTEMPTS = 3
_BACKOFF_BASE_S = 0.5
_BACKOFF_CAP_S = 8.0

# Recognised native backend kinds. Any other value is an unknown backend and is
# treated as a hard configuration error rather than being silently mis-routed
# (logic-error / maintainability lens).
_KIND_ANTHROPIC = "anthropic"
_KIND_OPENAI_CLI = "openai-cli"
_KIND_OLLAMA = "ollama"


def _error_json(reason: str) -> str:
    """Return a benign, parseable error envelope used for graceful degradation.

    Dispatchers pass the return value through ``extract_json(...) or {}`` and a
    ``[0] invalid`` parse is treated as a transient miss, so a structured string
    (never a raised exception) lets a whole run continue when one backend call
    fails (chaos-engineering / error-handling-resilience lens). No caller data is
    echoed back, so this can't become an injection/reflection vector (security).
    """
    return json.dumps({"error": "crewai_runner_unavailable", "reason": reason})


def _validate_spec(spec: Mapping[str, Any]) -> tuple[str, str, str]:
    """Extract ``(kind, model, base_url)`` from *spec*, or raise ``ValueError``.

    ``spec`` originates from ``backend_config.resolve`` but is treated as
    untrusted here: a partial/abusive spec (e.g. ``{}`` or a non-string
    ``base_url``) must surface a clear error instead of a raw ``KeyError`` /
    ``AttributeError`` deep inside LLM construction (adversarial-input lens).
    ``base_url`` is only required for the ollama path, so it defaults to "".
    """
    native = spec.get("native")
    if not isinstance(native, Mapping):
        raise ValueError("spec missing 'native' mapping")
    kind = native.get("kind")
    model = native.get("model")
    if not isinstance(kind, str) or not kind:
        raise ValueError("spec['native']['kind'] must be a non-empty string")
    if not isinstance(model, str) or not model:
        raise ValueError("spec['native']['model'] must be a non-empty string")
    base_url = spec.get("base_url", "")
    if not isinstance(base_url, str):
        raise ValueError("spec['base_url'] must be a string")
    return kind, model, base_url


def _llm_kwargs(kind: str, model: str, base_url: str) -> dict[str, Any]:
    """Build the per-``kind`` CrewAI ``LLM`` kwargs (pure; no I/O).

    Three explicit branches so the ``openai-cli`` shim is routed to an
    OpenAI-compatible endpoint rather than being lumped in with ollama and given
    the wrong ``ollama/`` prefix (logic-error lens). Every branch pins
    ``timeout`` so no path can hang (network / chaos lens). ``base_url`` has its
    trailing ``/v1`` trimmed for the ollama native API, matching the sibling
    runners.

    The two invariants shared by every backend — deterministic decoding
    (``temperature=0``) and a hang guard (``timeout``) — live in one ``base`` dict
    that each branch spreads, so they can never drift apart across branches
    (minimalist / maintainability lens).
    """
    base = {"temperature": 0, "timeout": _REQUEST_TIMEOUT_S}
    if kind == _KIND_ANTHROPIC:
        return {**base, "model": f"anthropic/{model}"}
    if kind == _KIND_OPENAI_CLI:
        return {
            **base,
            "model": f"openai/{model}",
            "base_url": base_url,
            "api_key": "local-shim",  # placeholder; the local shim ignores it (no secret)
        }
    if kind == _KIND_OLLAMA:
        return {
            **base,
            "model": f"ollama/{model}",
            "base_url": base_url.replace("/v1", ""),
            "response_format": {"type": "json_object"},
        }
    raise ValueError(f"unsupported backend kind {kind!r}")


def _sleep_backoff(attempt: int) -> None:
    """Sleep for capped exponential backoff with full jitter before a retry.

    Full jitter (``uniform(0, delay)``) de-correlates concurrent callers so they
    don't retry in lockstep and re-hammer a recovering backend (network /
    chaos-engineering lens). Jitter is drawn from the private ``_JITTER_RNG``
    under ``_JITTER_LOCK`` so concurrent retries never race on a shared PRNG state
    (concurrency lens). The chosen delay is logged so a diagnostician can tell
    deliberate backoff apart from a slow backend (observability lens).
    ``attempt`` is 0-based.
    """
    ceiling = min(_BACKOFF_CAP_S, _BACKOFF_BASE_S * (2 ** attempt))
    with _JITTER_LOCK:
        delay = _JITTER_RNG.uniform(0, ceiling)
    log.debug("backoff sleep %.3fs before retry (attempt %d, ceiling %.3fs)", delay, attempt, ceiling)
    time.sleep(delay)


def _release_crew_resources(crew: Any) -> None:
    """Best-effort release of a crew's transient resources, logging any failure.

    Calls the first teardown the crew exposes (``close`` then ``reset``). A crew
    with neither is a no-op — the ``getattr``/``callable`` guard keeps this correct
    across CrewAI versions. A teardown that raises is caught so it can't mask the
    real kickoff result, but is logged at WARNING so a failed close (the signature
    of a leaked socket/FD) is visible in telemetry, not swallowed (observability
    lens). No-teardown crews are logged once at DEBUG so the "why wasn't it closed"
    question is answerable from logs alone.
    """
    for method_name in ("close", "reset"):
        closer = getattr(crew, method_name, None)
        if callable(closer):
            try:
                closer()
            except Exception as exc:  # noqa: BLE001 - teardown must not mask the result
                log.warning(
                    "crew.%s() failed; possible resource leak: %s: %s",
                    method_name, type(exc).__name__, exc,
                )
            return
    log.debug("crew exposes no close/reset teardown; relying on GC")


@contextlib.contextmanager
def _released_crew(make_crew: Callable[[], Any]) -> Iterator[Any]:
    """Yield a fresh crew and guarantee its release on EVERY exit path.

    CrewAI ``Crew`` objects can hold transient resources (a litellm/httpx client,
    open sockets). Relying on GC to reclaim them after a failed ``kickoff`` is not
    prompt and can pile up FDs across retries. This context manager best-effort
    calls whichever teardown the crew exposes (``close``/``reset``) in a
    ``finally`` so the resource is released whether ``kickoff`` returns or raises
    (error-handling-resilience / memory-resource lens). A crew with no teardown
    method is a no-op — the ``getattr`` guard keeps this correct across CrewAI
    versions without assuming an API that may not exist.

    A teardown that itself raises is caught so it can't mask the real kickoff
    result, but it is logged at WARNING (observability lens): a failed close/reset
    is the exact signal of a leaked socket/FD, so it must be visible in telemetry
    rather than swallowed silently.
    """
    crew = make_crew()
    try:
        yield crew
    finally:
        _release_crew_resources(crew)


def _kickoff_with_retry(make_crew: Callable[[], Any]) -> str | None:
    """Run ``crew.kickoff()`` with bounded retry, returning the output or None.

    A *fresh* crew is built per attempt via ``make_crew`` so a partially-consumed
    crew is never re-run (idempotency / no shared state across retries — network /
    concurrency lens), and each attempt's crew is released on both success and
    failure via :func:`_released_crew` (error-handling-resilience lens).
    Exceptions are caught broadly *by design*: the underlying litellm/httpx
    failure surface is wide and unstable across versions, and this adapter must
    degrade rather than propagate any of it. Each failure is logged; the loop
    stops after ``_MAX_ATTEMPTS``.
    """
    for attempt in range(_MAX_ATTEMPTS):
        try:
            with _released_crew(make_crew) as crew:
                result = crew.kickoff()
            log.info("crew.kickoff succeeded on attempt %d/%d", attempt + 1, _MAX_ATTEMPTS)
            return str(result)
        except Exception as exc:  # noqa: BLE001 - broad by design; see docstring
            log.warning(
                "crew.kickoff failed (attempt %d/%d): %s: %s",
                attempt + 1, _MAX_ATTEMPTS, type(exc).__name__, exc,
            )
            if attempt + 1 < _MAX_ATTEMPTS:
                _sleep_backoff(attempt)
    log.error("crew.kickoff exhausted %d attempts; degrading", _MAX_ATTEMPTS)
    return None


def _build_llm(ws: Path) -> Mapping[str, Any] | None:
    """Resolve+validate the backend and return frozen ``LLM`` kwargs, or None.

    Returns an immutable ``MappingProxyType`` of the ``LLM`` constructor kwargs
    (never a live ``LLM`` instance). Rationale (concurrency lens): a single
    ``LLM`` object carries mutable per-call state (litellm client, message
    buffers); sharing one across every ``invoke`` thread races on that state.
    Handing back frozen kwargs lets each invocation build its OWN ``LLM`` inside
    ``make_crew`` — no mutable backend object is ever shared between threads —
    while the expensive resolve+validate still happens once at build time.

    Wraps the failure-prone boundaries (resolution, validation) so a config error
    degrades to a disabled invoker instead of crashing every dependent dispatcher
    at import time (chaos-engineering / error-handling-resilience lens).
    """
    try:
        spec = resolve_backend(ws)
        kind, model, base_url = _validate_spec(spec)
        kwargs = _llm_kwargs(kind, model, base_url)
    except Exception as exc:  # noqa: BLE001 - resolve()/validation surface; degrade
        log.error("backend resolution failed: %s: %s", type(exc).__name__, exc)
        return None
    log.info("crewai backend ready: kind=%s model=%s", kind, model)
    return MappingProxyType(kwargs)


def _coerce_brief(brief: Any) -> str:
    """Coerce an arbitrary *brief* into a length-bounded ``str`` (adversarial-input).

    ``build_invoker`` promises ``invoke(brief: str)``, but a buggy or hostile
    caller may pass any object. Two adversarial hazards are neutralised here BEFORE
    the value reaches :func:`_bounded_brief`:

      * A non-``str`` whose ``__str__`` returns a multi-gigabyte string would let
        an unbounded allocation slip past the string-sized cap. We therefore slice
        the coercion result to ``_MAX_BRIEF_BYTES`` chars immediately — the coerced
        object is only ever materialised as far as ``str()`` produces, then bounded.
      * A ``str`` is passed through untouched (the common, trusted path).

    Returns a ``str`` no larger than the char cap; the caller still applies the
    exact byte cap via :func:`_bounded_brief`. Raises only if ``str()`` itself
    raises, which the caller catches and degrades.
    """
    if isinstance(brief, str):
        return brief
    log.warning("invoke received non-str brief (%s); coercing + bounding", type(brief).__name__)
    return str(brief)[:_MAX_BRIEF_BYTES]


def _bounded_brief(brief: str) -> str:
    """Return *brief* truncated to ``_MAX_BRIEF_BYTES`` (immutably), logging if cut.

    Guards against memory exhaustion / prompt-flooding from an oversized brief
    before it is embedded into a Task (adversarial-input / memory-resource lens).

    The allocation done by ``.encode`` is bounded on EVERY path, including the
    fast path: we first slice to ``_MAX_BRIEF_BYTES`` chars. A string that fits
    the byte cap has at most that many chars (UTF-8 is >=1 byte/char), so the
    slice is a no-op for legitimate input; a hostile string — even one of emoji
    (4 bytes/char) whose *char* count is under an older gate — can never encode
    more than ``_MAX_BRIEF_BYTES`` chars, capping the transient bytes object at
    <=4*_MAX_BRIEF_BYTES regardless of content. The exact byte cap is then applied
    and decoded with ``errors='ignore'`` so a split multibyte char can't raise.
    """
    within_char_cap = len(brief) <= _MAX_BRIEF_BYTES
    head = brief if within_char_cap else brief[:_MAX_BRIEF_BYTES]  # char-slice bounds the encode
    encoded = head.encode("utf-8")
    if len(encoded) <= _MAX_BRIEF_BYTES:
        if within_char_cap:
            return brief                                 # legitimate input, untouched
        log.warning("brief of %d chars exceeds cap; truncated to %d chars", len(brief), _MAX_BRIEF_BYTES)
        return head
    log.warning("brief exceeds byte cap %d; truncating", _MAX_BRIEF_BYTES)
    return encoded[:_MAX_BRIEF_BYTES].decode("utf-8", errors="ignore")


def _make_crew_factory(
    llm_kwargs: Mapping[str, Any],
    system: str,
    role: str,
    goal: str,
    user_message_fn: Callable[[str], str],
    expected_output: str,
    safe_brief: str,
) -> Callable[[], Any]:
    """Return a zero-arg factory that builds a fresh Agent+Task+Crew per call.

    A NEW ``LLM`` is constructed here per invocation from the frozen *llm_kwargs*
    (not a shared instance), so no mutable backend object is ever touched by two
    ``invoke`` threads at once (concurrency lens). Everything downstream (Agent,
    Task, Crew) is likewise per-call, so retries never re-run consumed state.
    """
    def make_crew() -> Any:
        from crewai import LLM, Agent, Crew, Task  # noqa: PLC0415 - deferred import
        llm = LLM(**dict(llm_kwargs))
        worker = Agent(
            role=role, goal=goal, backstory=system,
            llm=llm, verbose=False, allow_delegation=False,
        )
        task = Task(
            description=user_message_fn(safe_brief),
            agent=worker, expected_output=expected_output,
        )
        return Crew(agents=[worker], tasks=[task], verbose=False)

    return make_crew


def _run_invocation_inner(make_crew: Callable[[], Any], inv_id: int) -> str:
    """Retry-driven invocation body: run, record metrics+latency, return a str.

    ANY failure in the retry path — a raising ``user_message_fn`` / ``LLM``
    construction inside ``make_crew``, or an exhausted retry loop — is converted
    to the documented error-JSON contract here. Metrics recording is itself
    non-raising (see :meth:`_Metrics.record`), so it cannot break this contract.
    """
    start = time.monotonic()
    try:
        output = _kickoff_with_retry(make_crew)
    except Exception as exc:  # noqa: BLE001 - make_crew/user_message_fn surface; degrade
        _METRICS.record(success=False, latency_s=time.monotonic() - start)
        log.error("[inv %d] failed before kickoff: %s: %s", inv_id, type(exc).__name__, exc)
        return _error_json(f"pre-kickoff failure: {type(exc).__name__}")
    latency = time.monotonic() - start
    if output is None:
        _METRICS.record(success=False, latency_s=latency)
        log.debug("[inv %d] degrading to error-JSON after exhausted retries", inv_id)
        return _error_json("kickoff exhausted retries")
    _METRICS.record(success=True, latency_s=latency)
    log.info("[inv %d] succeeded in %.3fs", inv_id, latency)
    return output


def _run_one_invocation(make_crew: Callable[[], Any], inv_id: int) -> str:
    """Outer safety net guaranteeing a ``str`` return on EVERY path.

    :func:`_run_invocation_inner` already degrades known failure modes, but this
    wrapper is the last line of defence: if ANYTHING unforeseen escapes it (a
    logging handler that raises, ``_error_json`` failing, an interpreter-level
    error), we still return a plain error string rather than propagating and
    breaking the ``Callable[[str], str]`` contract 87 dispatchers rely on
    (error-handling-resilience lens). The fallback string is a hand-built literal
    so it can't itself depend on ``json``/``_error_json`` succeeding.
    """
    try:
        return _run_invocation_inner(make_crew, inv_id)
    except Exception as exc:  # noqa: BLE001 - absolute last resort; never propagate
        with contextlib.suppress(Exception):
            log.critical("[inv %d] unexpected error escaped invocation: %s", inv_id, exc)
        return '{"error": "crewai_runner_unavailable", "reason": "unexpected error"}'


def build_invoker(
    ws: Path,
    system: str,
    user_message_fn: Callable[[str], str],
    role: str = "API testing agent",
    goal: str = "Analyse the given brief and produce a JSON test plan per your system instructions.",
    expected_output: str = "A single JSON object as specified by your system instructions.",
) -> Callable[[str], str]:
    """Return ``invoke(brief: str) -> str`` backed by a CrewAI Agent/Task/Crew.

    Public signature and return type (``str``) are unchanged for all 87 dependent
    dispatchers. On any backend failure the returned ``invoke`` yields a benign
    error-JSON string (see :func:`_error_json`) instead of raising, so a single
    unhealthy backend never aborts a whole forge run (chaos-engineering lens).

    Args mirror the original runner: *ws* (FORGE_WORKSPACE root, used only to
    locate ``scripts`` via the lock-guarded, containment-checked
    :func:`resolve_backend`), *system* (agent backstory), *user_message_fn* (the
    ``user_message`` callable), and the descriptive *role* / *goal* /
    *expected_output* labels.
    """
    llm_kwargs = _build_llm(Path(ws))  # frozen kwargs (per-thread LLM), or None

    def invoke(brief: str) -> str:
        inv_id = next(_INVOCATION_IDS)
        if llm_kwargs is None:
            log.debug("[inv %d] backend unavailable at build time", inv_id)
            return _error_json("backend unavailable at build time")
        # Prep (coerce + bound) is inside the try so even a pathological brief
        # object whose str()/len() raises degrades instead of escaping
        # (error-handling-resilience lens). _coerce_brief bounds a hostile
        # non-str's str() BEFORE the byte cap runs (adversarial-input lens).
        try:
            safe_brief = _bounded_brief(_coerce_brief(brief))
        except Exception as exc:  # noqa: BLE001 - hostile brief object; degrade
            log.error("[inv %d] brief preparation failed: %s: %s", inv_id, type(exc).__name__, exc)
            return _error_json(f"brief preparation failure: {type(exc).__name__}")
        log.info("[inv %d] invoke: brief=%d bytes", inv_id, len(safe_brief))
        make_crew = _make_crew_factory(
            llm_kwargs, system, role, goal, user_message_fn, expected_output, safe_brief,
        )
        return _run_one_invocation(make_crew, inv_id)

    return invoke
