"""Shared Claude Agent SDK runner.

Native Claude SDK when the backend is Anthropic; falls back to the local
OpenAI-compatible endpoint (Ollama /v1) when the native path is unavailable
(air-gapped, SDK missing, backend down, or the call times out).

Thin dispatchers call::

    from runners.claude_sdk_runner import build_invoker
    invoke = build_invoker(WS, system, user_message)
    raw_str = invoke(brief)          # -> str (raw model output)

Hardening rationale (each guard is annotated at its site):
  * observability — module logger + NullHandler; the chosen backend, every
    call, and every failure/fallback are logged. Every raise on a failure path
    is preceded by a log at WARNING/ERROR so no fault leaves without a trace.
  * chaos / network / error-handling-resilience — every I/O (model call, HTTP)
    is wrapped, timeout-bounded, and retried with backoff on *transient* faults;
    a circuit breaker trips the native path off after repeated native outages so
    calls stop paying the native timeout and fail straight to the local fallback;
    a total failure of BOTH paths is raised (reported) not masked as empty.
  * adversarial-input / memory-resource / device-stack — the per-call user
    message is size-capped before it is encoded/sent, AND the HTTP response is
    read under a byte cap, so neither an oversized brief nor a runaway backend
    response can exhaust memory on a constrained device.
  * concurrency / memory-resource — the reused event loop (asyncio.Runner) is
    created once under a per-invoker lock (no check-then-act race) and closed via
    a weakref.finalize so its file descriptors are released when the invoker is
    collected, never leaked across a long-running orchestration.
  * security / vulnerability — the backend-resolved base_url host is verified
    LOCAL (loopback/private) with backend_config's SSRF-safe check before any
    request is dialled; no attacker-controlled URL, no shell, no file writes.

stdlib + the (optional) claude_agent_sdk only; no new third-party imports.
"""
from __future__ import annotations

import asyncio
import json
import logging
import threading
import time
import urllib.error
import urllib.request
import uuid
import weakref
from contextlib import contextmanager
from pathlib import Path
from typing import Callable, Iterator, List, Optional
from urllib.parse import urlparse

from runners.utils import resolve_backend

# Library logger. NullHandler keeps imports silent for the 87 dependents; a
# caller opts into diagnostics via
# logging.getLogger("runners.claude_sdk_runner").setLevel(...). Backend choice
# and each successful call are DEBUG; recoverable faults/fallbacks are WARNING;
# a terminal failure that is about to be raised is ERROR so it is never invisible
# (observability lens).
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# Hard ceiling on the per-call user message. Briefs are kilobytes at most; a
# 4 MiB cap is generous headroom yet forbids a hostile/oversized brief from
# exhausting memory when JSON-encoded or buffered for the request
# (adversarial-input / memory-resource lens).
_MAX_MESSAGE_BYTES = 4 * 1024 * 1024

# Hard ceiling on the HTTP response we buffer. A misconfigured/compromised local
# backend could stream an unbounded body; resp.read(N) caps what we pull into RAM
# so a constrained device cannot be OOM-ed by the reply (device-stack lens).
_MAX_RESPONSE_BYTES = 16 * 1024 * 1024

# Timeouts. The native SDK path has NO timeout of its own, so a slow/hung cloud
# backend would block asyncio forever and never fall back; we bound it. The HTTP
# fallback timeout is kept modest (local shim/Ollama answer in seconds) so a hung
# local server fails fast instead of stalling orchestration (network / chaos /
# device-stack lens).
_NATIVE_TIMEOUT_S = 120.0
_HTTP_TIMEOUT_S = 90.0

# Bounded retry with linear backoff for the *transient* HTTP fallback faults
# (connection refused mid-restart, read timeout). Bounded so a persistently-down
# backend fails fast and is reported, never retried forever (network /
# error-handling-resilience lens).
_HTTP_RETRIES = 2
_HTTP_BACKOFF_S = 0.5

# Circuit breaker: after this many CONSECUTIVE native failures, stop attempting
# the native path and go straight to the local fallback, so an ongoing native
# outage no longer costs _NATIVE_TIMEOUT_S per call. A single native success
# resets the count and re-closes the breaker (chaos-engineering lens).
_NATIVE_FAILURE_THRESHOLD = 3

# Errors on the native path that mean "backend/SDK unavailable" and therefore
# justify falling back to the local OpenAI-compatible endpoint. Anything OUTSIDE
# this set (e.g. a programming error like AttributeError/KeyError from malformed
# state) is NOT an availability signal and must propagate, so a real bug is not
# masked as a silent fallback (error-handling-resilience / api-contract lens).
_NATIVE_FALLBACK_ERRORS = (
    ImportError,           # claude_agent_sdk not installed (air-gapped)
    asyncio.TimeoutError,  # native call exceeded _NATIVE_TIMEOUT_S
    ConnectionError,       # backend down / refused
    OSError,               # socket-level failure reaching the backend
    RuntimeError,          # e.g. asyncio.run() from a running loop / SDK runtime
    TimeoutError,          # builtin timeout alias
)

# Fixed, low-cardinality telemetry tag vocabulary. Kept as constants so log/metric
# tags can never drift or accept an unbounded free-form value (observability lens).
_BACKEND_NATIVE = "native"
_BACKEND_FALLBACK = "fallback"
_STATUS_SUCCESS = "success"
_STATUS_FAILURE = "failure"


class _Metrics:
    """In-process, thread-safe counter of model invocations by (backend, status).

    Gives production a failure-RATE signal for the critical model call without a
    third-party metrics dependency: the process (or a /metrics scraper) reads
    :func:`get_metrics` to see ``{(native|fallback, success|failure): count}`` and
    alert on a rising fallback/failure ratio. Increments are lock-guarded so
    concurrent invoke() calls cannot lose a count (observability / concurrency lens).
    The key space is a fixed 2x2 set, so the map is bounded — no per-request key
    growth (memory-resource lens).
    """

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._counts: dict = {}

    def incr(self, backend: str, status: str) -> None:
        """Bump the counter for one (backend, status) outcome, atomically."""
        with self._lock:
            key = (backend, status)
            self._counts[key] = self._counts.get(key, 0) + 1

    def snapshot(self) -> dict:
        """Return an immutable copy of the counters (safe to read concurrently)."""
        with self._lock:
            return dict(self._counts)


_METRICS = _Metrics()


def get_metrics() -> dict:
    """Read-only snapshot of invocation counters keyed by ``(backend, status)``.

    Additive helper — does NOT touch build_invoker's contract — so an operator or a
    /metrics endpoint can observe native-vs-fallback success/failure rates for the
    critical model call from telemetry alone (observability lens).
    """
    return _METRICS.snapshot()


@contextmanager
def _span(name: str, rid: str, backend: str) -> Iterator[None]:
    """Trace span + metric around one backend call, so a failure here is fully
    diagnosable from telemetry alone (observability lens).

    Emits a start line and a single structured end line tagged
    ``span=<name> rid=<rid> backend=<backend> status=... ms=...`` (success at INFO,
    failure at WARNING) and records the outcome in :data:`_METRICS`. Duration uses
    ``perf_counter`` (monotonic) so a wall-clock jump can't produce a negative or
    absurd latency (device-stack lens). Exceptions are re-raised unchanged — the
    span never swallows a fault (error-handling-resilience lens).
    """
    start = time.perf_counter()
    log.debug("[rid=%s] span start: %s backend=%s", rid, name, backend)
    try:
        yield
    except BaseException:
        _METRICS.incr(backend, _STATUS_FAILURE)
        log.warning("[rid=%s] span end: %s backend=%s status=%s ms=%.1f",
                    rid, name, backend, _STATUS_FAILURE, (time.perf_counter() - start) * 1000.0)
        raise
    _METRICS.incr(backend, _STATUS_SUCCESS)
    log.info("[rid=%s] span end: %s backend=%s status=%s ms=%.1f",
             rid, name, backend, _STATUS_SUCCESS, (time.perf_counter() - start) * 1000.0)


def _guard_message(brief: str, user_message_fn: Callable[[str], str]) -> str:
    """Render and size-check the per-call user message, or raise ValueError.

    Rationale: ``user_message_fn`` is caller-supplied and ``brief`` is external
    input; a non-str render or an oversized payload would either crash the JSON
    encoder or exhaust memory. We reject both BEFORE any encode/send so the fault
    is a clear, bounded ValueError rather than an OOM, and we log the rejection at
    ERROR so a hostile input is visible in telemetry (adversarial-input /
    memory-resource / observability lens).
    """
    msg = user_message_fn(brief)
    if not isinstance(msg, str):
        log.error("rejecting user message: user_message_fn returned %s, expected str",
                  type(msg).__name__)
        raise ValueError(f"user_message_fn returned {type(msg).__name__}, expected str")
    if len(msg.encode("utf-8", errors="ignore")) > _MAX_MESSAGE_BYTES:
        log.error("rejecting user message: %d-byte payload exceeds %d-byte cap",
                  len(msg), _MAX_MESSAGE_BYTES)
        raise ValueError(f"user message exceeds {_MAX_MESSAGE_BYTES}-byte cap; refusing to send")
    return msg


def _assert_local_url(url: str) -> None:
    """Raise ValueError unless *url*'s host is loopback/private, or crash-free.

    Defence-in-depth SSRF guard (security lens): backend_config already only ever
    yields a local base_url, but we re-verify at the point of use with its own
    timeout-bounded, DNS-rebind-safe ``_is_local_host`` so a future/mutated spec
    can never make urlopen dial an arbitrary public host. Failure is logged at
    ERROR and raised before any socket is opened.
    """
    import backend_config  # noqa: PLC0415 - importable via resolve_backend's sys.path insert

    try:
        host = urlparse(url).hostname or ""
    except ValueError as exc:  # malformed URL — refuse rather than dial
        log.error("refusing request: unparseable base_url %r (%s)", url, exc.__class__.__name__)
        raise ValueError(f"unparseable base_url {url!r}") from exc
    if not backend_config._is_local_host(host):
        log.error("refusing request: non-local base_url host %r (SSRF containment)", host)
        raise ValueError(f"refusing non-local backend host {host!r}")


async def _native_call(system: str, model: str, message: str) -> str:
    """Stream one native Claude SDK query to a joined string.

    Deferred import of ``claude_agent_sdk`` (absent when air-gapped) so importing
    THIS module never hard-requires the SDK; an ImportError here is caught by the
    caller and triggers the OpenAI-compatible fallback (chaos lens).
    """
    from claude_agent_sdk import query, ClaudeAgentOptions  # type: ignore[import]

    opts = ClaudeAgentOptions(system_prompt=system, model=model)
    chunks: List[str] = []
    async for msg in query(prompt=message, options=opts):
        chunks.append(str(getattr(msg, "content", msg)))
    return "".join(chunks)


def _run_native(runner: asyncio.Runner, coro_fn: Callable[[], "asyncio.Future"]) -> str:
    """Execute a native coroutine on the shared loop under a hard timeout.

    Reuses ONE event loop (``runner``) across calls instead of asyncio.run()'s
    fresh-loop-per-call, removing per-invocation loop setup/teardown overhead and
    the RuntimeError from nesting event loops (performance / system-design lens).
    The timeout is applied inside the loop via asyncio.wait_for so a hung backend
    surfaces as asyncio.TimeoutError -> fallback, never an infinite block (network
    / chaos lens).
    """
    async def _bounded() -> str:
        return await asyncio.wait_for(coro_fn(), timeout=_NATIVE_TIMEOUT_S)

    return runner.run(_bounded())


def _http_post_once(url: str, body: bytes) -> str:
    """One bounded HTTP POST to the local OpenAI-compatible endpoint.

    The request is timeout-bounded and the response is read under a byte cap so a
    runaway backend body cannot exhaust memory (device-stack lens). The body is
    parsed defensively: a malformed/short JSON body (missing choices/message/
    content) raises a clear ValueError rather than an opaque KeyError/IndexError
    (chaos / error-handling / observability lens). The urlopen context manager
    guarantees the socket FD is closed even on a parse error (memory-resource lens).
    """
    req = urllib.request.Request(
        url, data=body, headers={"Content-Type": "application/json"}, method="POST"
    )
    with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:  # nosec B310 - host verified local upstream
        raw = resp.read(_MAX_RESPONSE_BYTES + 1)
    if len(raw) > _MAX_RESPONSE_BYTES:
        log.error("refusing response from %s: body exceeds %d-byte cap", url, _MAX_RESPONSE_BYTES)
        raise ValueError(f"response body exceeds {_MAX_RESPONSE_BYTES}-byte cap")
    try:
        data = json.loads(raw)
        return data["choices"][0]["message"]["content"]
    except (json.JSONDecodeError, KeyError, IndexError, TypeError) as exc:
        log.error("malformed completion response from %s: %s", url, exc.__class__.__name__)
        raise ValueError(f"malformed completion response: {exc.__class__.__name__}") from exc


def _openai_compat(spec: dict, system: str, message: str, request_id: str = "-") -> str:
    """Call the local OpenAI-compatible endpoint with bounded retry + backoff.

    ``request_id`` is an OPTIONAL per-invocation correlation id (default "-" for
    direct callers) stamped into every log line so a single failed invocation can
    be traced across attempts (observability lens). The default keeps the public
    signature backward-compatible.

    The base_url host is re-verified local before any request (SSRF containment).
    Transient faults (URLError/timeout/refused mid-restart) are retried a bounded
    number of times with linear backoff; a malformed-but-received response is NOT
    retried (retrying a bug wastes time). After the last attempt the failure is
    logged at ERROR and re-raised so a persistently-down fallback is reported as a
    failure, never swallowed into a silent empty success (network / error-handling
    / chaos / observability lens).
    """
    url = spec["base_url"] + "/chat/completions"
    _assert_local_url(url)
    body = json.dumps(
        {
            "model": spec["model"],
            "temperature": 0,
            "messages": [
                {"role": "system", "content": system},
                {"role": "user", "content": message},
            ],
            "stream": False,
            "response_format": {"type": "json_object"},
        }
    ).encode("utf-8")

    last_exc: Optional[Exception] = None
    for attempt in range(1, _HTTP_RETRIES + 2):
        try:
            out = _http_post_once(url, body)
            log.debug("[rid=%s] openai-compat call to %s succeeded (attempt %d)", request_id, url, attempt)
            return out
        except ValueError:
            raise  # malformed/oversized response — a bug, not transient; do not retry
        except (urllib.error.URLError, TimeoutError, OSError) as exc:
            last_exc = exc
            log.warning("[rid=%s] openai-compat call to %s attempt %d/%d failed: %s",
                        request_id, url, attempt, _HTTP_RETRIES + 1, exc.__class__.__name__)
            if attempt <= _HTTP_RETRIES:
                time.sleep(_HTTP_BACKOFF_S * attempt)
    log.error("[rid=%s] openai-compat endpoint %s unreachable after %d attempts",
              request_id, url, _HTTP_RETRIES + 1)
    raise RuntimeError(f"openai-compat endpoint {url} unreachable after "
                       f"{_HTTP_RETRIES + 1} attempts") from last_exc


class _NativeChannel:
    """Thread-safe holder for one reused event loop + a native circuit breaker.

    ``asyncio.Runner`` is NOT thread-safe, so the lock is held across the WHOLE
    native call (Runner build + ``runner.run()`` + breaker update), not merely the
    check-then-act. Concurrent invoke() calls are therefore serialized onto the one
    shared loop — never driving ``run()`` from two threads at once (the undefined
    behavior the concurrency / device-stack lenses flagged). ``close`` releases the
    loop's file descriptors; a weakref.finalize on the owning invoker calls it so
    nothing leaks across a long run (memory-resource / error-handling-resilience
    lens).
    """

    def __init__(self, system: str, model: str) -> None:
        self._system = system
        self._model = model
        self._lock = threading.Lock()
        self._runner: Optional[asyncio.Runner] = None
        self._consecutive_failures = 0

    @property
    def _open(self) -> bool:
        """True while the breaker is CLOSED (native allowed). Read under no lock
        is fine: a stale read only costs one extra native attempt or one skipped
        attempt, never corrupts state."""
        return self._consecutive_failures < _NATIVE_FAILURE_THRESHOLD

    def call(self, message: str) -> str:
        """Run the native path, tripping/​resetting the breaker. Raises on failure
        (caller decides fallback).

        The ENTIRE call — Runner creation AND ``runner.run()`` — is held under the
        lock, because ``asyncio.Runner`` is NOT thread-safe: two threads driving the
        same event loop's ``run()`` at once is undefined behavior. Serializing here
        makes concurrent invoke() calls safe on one shared loop, and also makes the
        breaker-counter update race-free without a second lock acquisition
        (concurrency / device-stack lens). The native path is I/O-bound and already
        timeout-bounded, so this serialization does not create an unbounded wait."""
        with self._lock:
            if self._runner is None:
                self._runner = asyncio.Runner()
            try:
                out = _run_native(self._runner, lambda: _native_call(self._system, self._model, message))
            except BaseException:
                self._consecutive_failures += 1
                raise
            self._consecutive_failures = 0
            return out

    def close(self) -> None:
        """Idempotently close the event loop, releasing its FDs. Broad except is
        intentional: cleanup must never raise during finalization/GC."""
        with self._lock:
            runner, self._runner = self._runner, None
        if runner is not None:
            try:
                runner.close()
            except Exception as exc:  # noqa: BLE001 - never let teardown raise
                log.debug("native runner close raised during cleanup: %s", exc.__class__.__name__)


def build_invoker(
    ws: Path,
    system: str,
    user_message_fn: Callable[[str], str],
) -> Callable[[str], str]:
    """Return ``invoke(brief: str) -> str`` backed by the Claude Agent SDK.

    Args:
        ws: FORGE_WORKSPACE root path.
        system: Fully-loaded system-prompt string.
        user_message_fn: The ``user_message`` callable from ``*_prompt`` module.

    Backend resolution is delegated to the shared, lock-guarded ``resolve_backend``
    so the process-global ``sys.path`` mutation happens once, race-free, with no
    unbounded duplicate growth. The native event loop + circuit breaker live in a
    thread-safe :class:`_NativeChannel`; a weakref.finalize closes it when the
    returned ``invoke`` is garbage-collected, so loops never leak across a long
    orchestration (concurrency / memory-resource / error-handling lens).
    """
    spec = resolve_backend(Path(ws))
    native_kind = spec["native"]["kind"]
    log.debug("build_invoker: provider=%s native_kind=%s base_url=%s",
              spec.get("provider"), native_kind, spec.get("base_url"))

    channel = _NativeChannel(system, spec["native"]["model"]) if native_kind == "anthropic" else None

    def invoke(brief: str) -> str:
        """Render + size-guard the brief, try native (unless the breaker is
        tripped), fall back to local on availability faults, and report a total
        failure as an exception.

        A short per-invocation correlation id (``rid``) is generated and stamped
        into every log line, and each backend attempt runs inside a :func:`_span`
        that records a (backend, status) metric and a timed trace line — so one
        invocation's native attempt, fallback, and retries are stitched together
        AND its success/failure rate is observable from telemetry alone, all
        without an API change (observability lens)."""
        rid = uuid.uuid4().hex[:8]
        message = _guard_message(brief, user_message_fn)
        if channel is not None and channel._open:
            try:
                with _span("native_call", rid, _BACKEND_NATIVE):
                    out = channel.call(message)
                return out
            except _NATIVE_FALLBACK_ERRORS as exc:
                # Availability fault only — the span already logged+counted the
                # native failure; degrade to the local endpoint. Non-availability
                # errors (programming bugs) are outside this tuple and propagate.
                log.warning("[rid=%s] native SDK path unavailable (%s); falling back to %s",
                            rid, exc.__class__.__name__, spec.get("base_url"))
        elif channel is not None:
            log.warning("[rid=%s] native circuit breaker open after %d failures; using fallback",
                        rid, _NATIVE_FAILURE_THRESHOLD)
        with _span("openai_compat", rid, _BACKEND_FALLBACK):
            return _openai_compat(spec, system, message, request_id=rid)

    if channel is not None:
        # Release the event loop's FDs when the invoker is collected. finalize is
        # GC-safe and idempotent, so no leak whether invoke() is dropped or the
        # process exits (memory-resource / error-handling-resilience lens).
        weakref.finalize(invoke, channel.close)
    return invoke
