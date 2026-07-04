"""Shared LangGraph runner — model init + single-node StateGraph.

Thin dispatchers call::

    from runners.langgraph_runner import build_invoker
    invoke = build_invoker(WS, system, user_message)
    raw_str = invoke(brief)          # -> str (raw LLM output)

Hardening rationale (per-lens, so a future run sees WHAT was protected and WHY):
  * backend + import: resolution goes through ``runners.utils.resolve_backend``,
    which inserts ``ws/scripts`` on ``sys.path`` exactly once under a lock and
    keys off a membership check.  That single choke point closes the import-
    injection, unbounded-``sys.path``-growth, and concurrent-race defects at
    once (security / memory-resource / concurrency lenses) — this module never
    touches ``sys.path`` itself.
  * network + chaos + error-handling: every LLM call carries an explicit
    ``timeout`` and runs under a bounded retry-with-jittered-backoff wrapper (full
    jitter prevents a synchronized thundering herd against a flaky backend); a
    persistently down/slow backend degrades to a raised, logged error instead of an
    indefinite hang or a silent empty "success". A raising ``on_usage`` callback is
    isolated so it can never discard a good result (network / chaos-engineering /
    error-handling lenses).
  * vulnerability (SSRF): the base_url the OpenAI/Ollama clients dial is asserted to
    be loopback/private BEFORE any client is built, so a tampered backend spec cannot
    turn a model call into a request-forgery probe of an internal/public host.
  * memory-resource: each LLM/HTTP client is reused across calls (no per-call
    reconnect) and closed via a ``weakref.finalize`` tied to the call closure, so
    repeated ``build_invoker`` calls don't leak sockets/FDs.
  * adversarial-input: the ``brief`` is length-validated before it is ever
    concatenated into a prompt and shipped to the model, so a multi-megabyte
    payload can't exhaust memory or wedge the call (adversarial-input lens).
  * observability: a module logger with a NullHandler names the backend at build
    time and logs every call attempt, retry, and terminal failure (never prompt
    or response bytes, which may be sensitive).
  * maintainability / minimalist: the two public builders are thin wrappers over
    one ``_build_call`` so a backend kind is added or a bug fixed in exactly one
    place (DRY); each broad-looking except is narrowed and documented.

stdlib + already-vendored deps (langgraph / langchain_* / openai) only.
"""
from __future__ import annotations

import ipaddress
import logging
import random
import threading
import time
import uuid
import weakref
from pathlib import Path
from typing import Any, Callable, Dict, Optional, Tuple
from urllib.parse import urlparse

from runners.utils import resolve_backend

# Library logger. NullHandler keeps imports silent by default (this module has 87
# dependents); a caller opts into diagnostics via
# ``logging.getLogger("runners.langgraph_runner").setLevel(...)``. Build/selection
# detail is DEBUG; a completed call is INFO (so success is visible under a normal
# production INFO threshold); each retry is WARNING and a terminal give-up is ERROR
# so a degraded backend is loud without ever crashing on import. Call outcomes are
# also counted in _METRICS, readable via get_metrics() for monitoring (observability
# lens).
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# Wall-clock ceiling handed to every LLM/network call. Backends are local
# (loopback/private shims and proxies), so a healthy response returns in well
# under this bound; the cap turns an unreachable/hung backend into a fast, logged
# failure instead of an indefinite block (network / chaos-engineering lenses).
_CALL_TIMEOUT_S: float = 30.0

# Bounded retry budget for a single call. A momentary blip (proxy restart, accept
# backlog) is absorbed by one cheap retry; beyond the budget we surface the error
# rather than retrying forever (chaos-engineering / error-handling-resilience).
_MAX_ATTEMPTS: int = 3
_BACKOFF_BASE_S: float = 0.25  # exponential: 0.25s, 0.5s between the bounded attempts

# Hard ceiling on the caller-supplied ``brief`` before it is concatenated into a
# prompt. Briefs are kilobytes in practice; 100k chars is generous headroom yet
# forbids a hostile ``invoke("a" * 10**7)`` from exhausting memory or wedging the
# model call (adversarial-input / memory-resource lenses).
_MAX_BRIEF_CHARS: int = 100_000

# Default token cap for the multicaller's anthropic path, preserving the historical
# hardcoded 1024 that the multicaller used before consolidation (system-design lens).
_MULTICALLER_ANTHROPIC_MAX_TOKENS: int = 1024


# call(prompt) -> (content_str, usage_metadata_or_None)
_CallFn = Callable[[str], Tuple[str, Optional[dict]]]


class _EmptyResponseError(RuntimeError):
    """A backend returned a structurally-empty response (e.g. no choices) on success.

    Raised so an empty/degenerate backend reply is treated as a retryable FAILURE by
    ``_with_retry`` rather than a silent empty "success" (error-handling-resilience
    lens). Module-private; callers only ever see it via the propagated call failure.
    """


# --- lightweight in-process metrics (observability lens) --------------------
# Monotonic counters an operator/monitor can scrape without a metrics backend: how
# many LLM calls succeeded, how many failed after the retry budget, and how many
# individual attempts were retried. Kept as a plain dict behind a lock so concurrent
# invokers increment it race-free (concurrency lens). Read via get_metrics(); a
# healthy call rate and a rising failure count are both visible in production even
# when log level hides DEBUG detail.
_METRICS_LOCK = threading.Lock()
_METRICS: Dict[str, int] = {"calls_succeeded": 0, "calls_failed": 0, "call_retries": 0}


def _incr_metric(name: str, amount: int = 1) -> None:
    """Atomically add *amount* to counter *name* (created on first use).

    Observability lens: a single choke point for counter mutation keeps every
    increment under one lock, so success/failure/retry tallies stay consistent under
    concurrent invocation without each call site re-implementing the locking.
    """
    with _METRICS_LOCK:
        _METRICS[name] = _METRICS.get(name, 0) + amount


def get_metrics() -> Dict[str, int]:
    """Return a snapshot copy of the call counters for monitoring/alerting.

    Observability lens: exposes ``calls_succeeded`` / ``calls_failed`` /
    ``call_retries`` so a health probe or dashboard can alert on a failure spike or a
    stalled success rate. A COPY is returned so a reader can never mutate the live
    counters (data-integrity lens). This is additive read-only surface — no existing
    caller is affected.
    """
    with _METRICS_LOCK:
        return dict(_METRICS)


def _guard_build(client: Any, finish: Callable[[], _CallFn]) -> _CallFn:
    """Run *finish* (post-construction setup) and close *client* if it raises.

    Error-handling-resilience lens: a client (OpenAI/ChatAnthropic/ChatOllama) is a
    resource acquired by construction. If any later setup step in a caller factory
    fails (a bad ``spec['native']['model']`` lookup, a validation error, the cleanup
    registration itself), the half-built client must be released deterministically —
    not left to non-deterministic GC. This wraps that setup so an exception triggers
    an immediate best-effort ``_safe_close`` before the error propagates, giving each
    factory rollback-on-failure without duplicating try/finally in every one (DRY).
    """
    try:
        return finish()
    except BaseException:
        _safe_close(client)
        raise


def _new_request_id() -> str:
    """Return a short correlation id for tracing one invoker's calls across logs.

    Observability lens: a caller may pass its own ``request_id`` into
    ``build_invoker`` to join these logs to an upstream distributed trace; when it
    doesn't, we mint a short random one so every log line is still correlatable to a
    single invoker instance. The 8-hex prefix is plenty to disambiguate concurrent
    invokers without bloating each line.
    """
    return uuid.uuid4().hex[:8]


def _assert_local_base_url(base_url: str) -> str:
    """Return *base_url* iff it targets a loopback/private host, else raise.

    SSRF containment (vulnerability lens): the OpenAI/Ollama HTTP clients dial
    whatever ``base_url`` the resolved backend spec carries. A foundry backend only
    ever listens on loopback or an RFC-1918 private address, so we refuse any other
    host BEFORE a client is constructed — an env-injected or otherwise-tampered
    ``base_url`` pointing at an internal or public host can never turn a model call
    into a request-forgery probe. A bare hostname (e.g. ``localhost``) that isn't a
    literal is treated as non-local and refused rather than DNS-resolved here (the
    resolver-based check lives in backend_config; this module fails closed).
    """
    host = urlparse(base_url).hostname or ""
    if host in ("localhost", ""):
        return base_url
    try:
        ip = ipaddress.ip_address(host)
    except ValueError as exc:
        raise ValueError(
            f"refusing non-local backend base_url {base_url!r} (host {host!r} is not a "
            f"loopback/private literal) — SSRF containment"
        ) from exc
    if not (ip.is_loopback or ip.is_private or ip.is_link_local):
        raise ValueError(
            f"refusing non-local backend base_url {base_url!r} (host {host!r}) — SSRF containment"
        )
    return base_url


def _safe_close(client: Any) -> None:
    """Best-effort close of an LLM/HTTP client, swallowing any close-time error.

    Memory-resource lens: OpenAI/langchain clients hold a pooled HTTP transport
    (sockets/file descriptors). We close it deterministically so repeated
    ``build_invoker`` calls don't leak connections. A missing/failing ``close`` is
    non-fatal — it must never turn teardown into a crash — so it is logged at DEBUG
    and ignored.
    """
    closer = getattr(client, "close", None)
    if not callable(closer):
        return
    try:
        closer()
    except Exception as exc:  # noqa: BLE001 - teardown must never raise; log and move on
        log.debug("ignoring error while closing LLM client: %s: %s", exc.__class__.__name__, exc)


def _register_cleanup(call: _CallFn, *clients: Any) -> _CallFn:
    """Tie each *client*'s lifetime to the returned *call* closure via a finalizer.

    Memory-resource lens: the client is reused across every ``invoke`` (performance
    lens — no per-call reconnect), and ``weakref.finalize`` closes it exactly once
    when the ``call`` closure is garbage-collected (i.e. when the invoker/graph is
    dropped). This bounds FD/socket lifetime to the invoker's lifetime without
    changing the public API or reconnecting on the hot path.
    """
    for client in clients:
        weakref.finalize(call, _safe_close, client)
    return call


def _validate_brief(brief: str) -> str:
    """Return *brief* unchanged, or raise on a hostile/invalid value.

    Fails fast at the boundary (adversarial-input lens): a non-str or an
    over-``_MAX_BRIEF_CHARS`` payload is rejected with a precise ValueError before
    it is ever concatenated with the system prompt and sent to the model, so it can
    neither exhaust memory nor silently corrupt the request.
    """
    if not isinstance(brief, str):
        raise ValueError(f"brief must be str, got {type(brief).__name__}")
    if len(brief) > _MAX_BRIEF_CHARS:
        raise ValueError(
            f"brief is {len(brief)} chars (> {_MAX_BRIEF_CHARS} cap); refusing to send"
        )
    return brief


def _coerce_content(raw: Any) -> str:
    """Normalize an LLM message ``content`` to a plain string.

    Anthropic may return a list of content-block dicts; everything else is already
    a string. A list is flattened by concatenating each block's ``text`` (or its
    ``str`` when the block isn't a dict). Returns "" only for a genuinely empty
    payload — the caller decides whether that empty is an error (error-handling lens).
    """
    if isinstance(raw, str):
        return raw
    if isinstance(raw, list):
        return "".join(
            b.get("text", "") if isinstance(b, dict) else str(b) for b in raw
        )
    return "" if raw is None else str(raw)


def _with_retry(fn: Callable[[], Tuple[str, Optional[dict]]], label: str) -> Tuple[str, Optional[dict]]:
    """Run *fn* under a bounded retry-with-backoff, logging and re-raising on give-up.

    Rationale (chaos-engineering / error-handling-resilience / network lenses): a
    transient backend fault (restart, momentary refuse, timeout blip) is retried a
    small, fixed number of times with exponential backoff; a persistent fault raises
    the LAST error after the budget is spent — never an indefinite loop and never a
    swallowed error masquerading as success. ``label`` names the backend/model in
    every log line without leaking prompt/response bytes (observability lens).

    Observability: a completed call is logged at INFO (visible under production's
    typical INFO threshold, not just DEBUG) and increments ``calls_succeeded``; each
    retried attempt increments ``call_retries``; a terminal give-up logs at ERROR and
    increments ``calls_failed`` — so success rate and failure spikes are both
    monitorable via :func:`get_metrics` without a metrics backend.
    """
    last_exc: Optional[BaseException] = None
    for attempt in range(1, _MAX_ATTEMPTS + 1):
        try:
            result = fn()
        except Exception as exc:  # noqa: BLE001 - transient backend/network faults are retried; re-raised below
            last_exc = exc
            _incr_metric("call_retries")
            log.warning(
                "%s call attempt %d/%d failed: %s: %s",
                label, attempt, _MAX_ATTEMPTS, exc.__class__.__name__, exc,
            )
            if attempt < _MAX_ATTEMPTS:
                # Exponential backoff with full jitter (network lens): the random
                # 0.5x–1.5x spread de-synchronizes many clients retrying a flaky
                # backend at once, so a struggling server isn't hammered by a
                # synchronized thundering herd.
                base = _BACKOFF_BASE_S * (2 ** (attempt - 1))
                time.sleep(base * (0.5 + random.random()))
            continue
        _incr_metric("calls_succeeded")
        log.info("%s call succeeded on attempt %d/%d", label, attempt, _MAX_ATTEMPTS)
        return result
    _incr_metric("calls_failed")
    log.error("%s call failed after %d attempts; giving up", label, _MAX_ATTEMPTS)
    assert last_exc is not None  # loop ran at least once, so an exception was recorded
    raise last_exc


def _openai_caller(spec: dict, max_tokens: Optional[int]) -> _CallFn:
    """Build a call() for the OpenAI-compatible shim (``kind == 'openai-cli'``).

    Used both by the standard path (``claude -p`` CLI shim for a Claude Code
    session) and the multicaller. Sets an explicit per-request ``timeout`` so a hung
    shim fails fast (network lens). An empty ``choices`` array on a 200 response is a
    BACKEND ERROR, not a valid empty answer: it is raised as ``_EmptyResponseError``
    (never returned as a silent empty "success"), so ``_with_retry`` retries it and,
    if it persists, the failure surfaces to the caller (error-handling-resilience
    lens). Indexing ``choices[0]`` is reached only when non-empty (math-correctness).
    """
    from openai import OpenAI  # noqa: PLC0415 - deferred; heavy optional dep

    # base_url is validated BEFORE construction so a rejected host never leaks a
    # client (no resource to roll back on the SSRF path).
    base_url = _assert_local_base_url(spec["base_url"])
    client = OpenAI(base_url=base_url, api_key="local-shim", timeout=_CALL_TIMEOUT_S)

    def finish() -> _CallFn:
        model = spec["native"]["model"]  # may raise (KeyError) — guarded below

        def call(prompt: str) -> Tuple[str, Optional[dict]]:
            kwargs: dict = {
                "model": model,
                "temperature": 0,
                "messages": [{"role": "user", "content": prompt}],
                "timeout": _CALL_TIMEOUT_S,
            }
            if max_tokens is not None:
                kwargs["max_tokens"] = max_tokens
            r = client.chat.completions.create(**kwargs)
            choices = getattr(r, "choices", None) or []
            if not choices:
                raise _EmptyResponseError("openai-cli backend returned no choices (empty response)")
            return choices[0].message.content or "", None

        return _register_cleanup(call, client)

    # Close the just-built client if any setup step raises (error-handling lens).
    return _guard_build(client, finish)


def _anthropic_caller(spec: dict, max_tokens: Optional[int], use_usage: bool) -> _CallFn:
    """Build a call() for native Anthropic (``kind == 'anthropic'``).

    ``timeout`` bounds the request (network lens); ``max_tokens`` is passed through
    when supplied. ``use_usage`` controls whether ``usage_metadata`` is surfaced (the
    token-tracking agents want it; the multicaller historically did too).
    """
    from langchain_anthropic import ChatAnthropic  # noqa: PLC0415 - deferred optional dep

    kwargs: dict = {"model": spec["native"]["model"], "temperature": 0, "timeout": _CALL_TIMEOUT_S}
    if max_tokens is not None:
        kwargs["max_tokens"] = max_tokens
    # No base_url SSRF check here: ChatAnthropic dials Anthropic's own fixed cloud
    # endpoint, not spec["base_url"], so there is no attacker-controllable target.
    llm = ChatAnthropic(**kwargs)

    def finish() -> _CallFn:
        def call(prompt: str) -> Tuple[str, Optional[dict]]:
            result = llm.invoke(prompt)
            content = _coerce_content(getattr(result, "content", None))
            usage = getattr(result, "usage_metadata", None) if use_usage else None
            return content, usage

        return _register_cleanup(call, llm)

    # Close the just-built llm if cleanup registration or setup raises (error-handling lens).
    return _guard_build(llm, finish)


def _ollama_caller(spec: dict, use_usage: bool) -> _CallFn:
    """Build a call() for native Ollama (the local air-gapped fallback).

    Ollama's OpenAI-compat ``base_url`` carries a ``/v1`` suffix that its native
    client must not have, so it is stripped. ``format='json'`` mirrors the historical
    behavior. A per-request ``timeout`` bounds the invoke (network lens).
    """
    from langchain_ollama import ChatOllama  # noqa: PLC0415 - deferred optional dep

    base_url = _assert_local_base_url(spec["base_url"]).replace("/v1", "")
    llm = ChatOllama(
        model=spec["native"]["model"],
        base_url=base_url,
        temperature=0,
        format="json",
        timeout=_CALL_TIMEOUT_S,
    )

    def finish() -> _CallFn:
        def call(prompt: str) -> Tuple[str, Optional[dict]]:
            result = llm.invoke(prompt)
            content = _coerce_content(getattr(result, "content", None))
            usage = getattr(result, "usage_metadata", None) if use_usage else None
            return content, usage

        return _register_cleanup(call, llm)

    # Close the just-built llm if cleanup registration or setup raises (error-handling lens).
    return _guard_build(llm, finish)


def _build_call(
    ws: Path,
    max_tokens: Optional[int],
    use_usage: bool,
    request_id: Optional[str] = None,
) -> _CallFn:
    """Resolve the backend and return a bounded, retrying, logged ``call(prompt)``.

    This is the single source of truth for the three backend kinds
    (``openai-cli`` / ``anthropic`` / ``ollama``) that ``_build_standard_call`` and
    ``_build_multicaller`` used to duplicate (maintainability / minimalist /
    system-design lenses). It:
      * resolves the backend via ``resolve_backend`` (safe, one-time ``sys.path``
        insert under a lock — security / concurrency / memory-resource lenses);
      * builds the kind-specific inner caller with an explicit per-request timeout;
      * wraps it in ``_with_retry`` so every returned ``call`` retries transient
        faults a bounded number of times and raises (not returns empty) on a
        persistent one (chaos-engineering / error-handling-resilience / network).

    ``max_tokens`` and ``use_usage`` are the only axes on which the two public
    builders differ; passing them in keeps one implementation, not two.
    ``request_id`` (a correlation id; auto-generated when omitted) is folded into the
    log ``label`` so every attempt/retry/failure line for this invoker can be traced
    end-to-end through distributed logs (observability lens). The trailing kwarg is
    additive, so ``_build_call``'s existing two-positional callers are unaffected.
    """
    rid = request_id or _new_request_id()
    spec = resolve_backend(ws)
    kind = spec["native"]["kind"]
    label = (f"langgraph[rid={rid} "
             f"{spec.get('provider', '?')}/{spec['native'].get('model', '?')}/{kind}]")
    log.debug("building langgraph call for backend %s (use_usage=%s, max_tokens=%s)",
              label, use_usage, max_tokens)

    # max_tokens is an ANTHROPIC-ONLY cap (see build_invoker: "only applied to
    # ChatAnthropic"). It is therefore withheld from the openai-cli and ollama
    # callers so the contract matches the behavior — previously the multicaller's
    # 1024 leaked into the openai-cli request and silently truncated it (logic-error
    # lens).
    if kind == "openai-cli":
        inner = _openai_caller(spec, max_tokens=None)
    elif kind == "anthropic":
        inner = _anthropic_caller(spec, max_tokens, use_usage)
    else:
        inner = _ollama_caller(spec, use_usage)

    def call(prompt: str) -> Tuple[str, Optional[dict]]:
        return _with_retry(lambda: inner(prompt), label)

    return call


def _build_standard_call(
    ws: Path,
    max_tokens: Optional[int] = None,
) -> _CallFn:
    """Return ``call(prompt) -> (str, usage_meta)`` for the standard two-backend path.

    Public signature preserved. Surfaces ``usage_metadata`` (``use_usage=True``) so
    the ``on_usage`` callback in :func:`build_invoker` keeps working, and passes
    ``max_tokens`` through unchanged.
    """
    return _build_call(ws, max_tokens=max_tokens, use_usage=True)


def _build_multicaller(ws: Path) -> _CallFn:
    """Return ``call(prompt) -> (str, usage_meta)`` supporting anthropic / openai-cli / ollama.

    Public signature preserved. Used by the four agents carrying the ``_caller()``
    multi-backend pattern (content-type-negotiation, api-gateway-routing,
    soft-delete, create-postman). The anthropic path keeps the historical 1024
    ``max_tokens`` default via ``_MULTICALLER_ANTHROPIC_MAX_TOKENS``; the shared
    ``_build_call`` applies it only to the anthropic caller (the openai-cli and
    ollama callers ignore an anthropic-only cap, matching prior behavior).
    """
    return _build_call(
        ws, max_tokens=_MULTICALLER_ANTHROPIC_MAX_TOKENS, use_usage=True
    )


def build_invoker(
    ws: Path,
    system: str,
    user_message_fn: Callable[[str], str],
    max_tokens: Optional[int] = None,
    multicaller: bool = False,
    on_usage: Optional[Callable[[Optional[dict]], None]] = None,
    request_id: Optional[str] = None,
) -> Callable[[str], str]:
    """Return ``invoke(brief: str) -> str`` backed by a compiled LangGraph StateGraph.

    Args:
        ws: FORGE_WORKSPACE root path.
        system: Fully-loaded system-prompt string.
        user_message_fn: The ``user_message`` callable from ``*_prompt`` module.
        max_tokens: Optional token cap (only applied to ChatAnthropic).
        multicaller: Use the three-backend ``_caller()`` pattern instead of the
            standard two-backend model.  Set for the four agents that originally
            used ``_caller()`` (content-type, routing, soft-delete, postman).
        on_usage: Optional callback receiving ``msg.usage_metadata`` (a dict or
            ``None``) after each LLM call.  Used by the two token-tracking agents
            (queryparam, versioning) to accumulate TOTALS.
        request_id: Optional correlation id joining this invoker's log lines to an
            upstream distributed trace. Auto-generated when omitted. Additive
            keyword-only-in-practice arg — existing positional callers are unaffected.

    Hardening: the ``brief`` is length-validated before every model call
    (adversarial-input lens); the model call runs under bounded retry+timeout and,
    on terminal failure, raises a logged error rather than returning a silent empty
    string (chaos / error-handling-resilience lenses); every log line carries the
    correlation id for end-to-end tracing (observability lens).
    """
    from typing import TypedDict
    from langgraph.graph import StateGraph, END  # type: ignore[import]  # noqa: PLC0415

    rid = request_id or _new_request_id()
    # Route through _build_call directly (not the two public builders) so the rid
    # threads into the retry/attempt log labels without changing those builders'
    # frozen public signatures. multicaller keeps its historical anthropic-only cap.
    mt = _MULTICALLER_ANTHROPIC_MAX_TOKENS if multicaller else max_tokens
    call: _CallFn = _build_call(ws, max_tokens=mt, use_usage=True, request_id=rid)

    class S(TypedDict):
        brief: str
        output: str

    def generate_node(state: S) -> S:
        brief = _validate_brief(state["brief"])
        prompt = f"{system}\n\n{user_message_fn(brief)}"
        try:
            content, usage_meta = call(prompt)
        except Exception as exc:  # noqa: BLE001 - re-raise after logging without leaking prompt/response
            # Log model/backend context (NOT prompt/response, which may be
            # sensitive) then propagate: a failed LLM call is a hard error the
            # caller must see, never a silent empty "success" (error-handling /
            # observability lenses). The rid ties this line to the attempt logs.
            log.error("langgraph generate_node LLM call failed [rid=%s]: %s: %s",
                      rid, exc.__class__.__name__, exc)
            raise
        # Confirm the success path at INFO (observability lens): visible under a
        # production INFO threshold (not just DEBUG), it proves the node completed and
        # surfaces a suspiciously empty/short output for diagnosis, rather than leaving
        # success inferable only from the absence of an error. Only the length is
        # logged — never the content, which may be sensitive.
        log.info("langgraph generate_node completed [rid=%s]: output_chars=%d usage=%s",
                 rid, len(content), "present" if usage_meta else "none")
        # on_usage is an untrusted caller callback: a raising callback must NOT
        # discard the LLM output we already produced. We isolate it so a bad
        # callback is logged and swallowed while invoke() still returns the result
        # (error-handling-resilience lens).
        if on_usage is not None:
            try:
                on_usage(usage_meta)
            except Exception as exc:  # noqa: BLE001 - callback failure must not lose a good result
                log.error("on_usage callback raised (%s); output preserved",
                          exc.__class__.__name__)
        return {"brief": brief, "output": content}

    g: StateGraph = StateGraph(S)
    g.add_node("generate", generate_node)
    g.set_entry_point("generate")
    g.add_edge("generate", END)
    graph = g.compile()

    def invoke(brief: str) -> str:
        return graph.invoke({"brief": brief, "output": ""})["output"]

    return invoke
