"""Shared Claude Code subagent runner.

Elicits via the ``claude`` CLI when available (Anthropic backend), else falls back to the
local OpenAI-compatible endpoint (Ollama /v1). Thin dispatchers call::

    from runners.subagent_runner import build_invoker
    invoke = build_invoker(WS, system, user_message)
    raw_str = invoke(brief)          # -> str (raw model output)

Both backends share one failure protocol (each returns ``None`` on miss); if both miss,
``invoke`` raises :class:`BackendUnavailable`. Every I/O boundary is wrapped and logged, and
all untrusted text is size-bounded. Per-guard rationale lives inline at each site. stdlib +
sibling ``runners.utils`` helpers only.
"""
from __future__ import annotations

import json
import logging
import random
import shutil
import subprocess
import time
import urllib.error
import urllib.request
import uuid
from pathlib import Path
from typing import Callable, Optional

from runners.utils import resolve_backend

# Library logger. NullHandler keeps imports silent by default (no stderr noise for the
# ~95 dependents); a caller opts into diagnostics via
# logging.getLogger("runners.subagent_runner").setLevel(...). Per-attempt detail is DEBUG; each
# backend success and the invoke-level outcome are INFO and carry a monotonic-clock LATENCY
# (``total=..ms`` / per-backend ``..ms``) so timing is diagnosable without a metrics backend;
# every failure/fallback is WARNING so a degraded run is loud without crashing. All request-scoped
# lines share the same ``cid`` correlation id, so one request is a complete, timed, greppable
# trace even across a CLI->local fallback (observability lens).
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# Default local response_format for single-JSON-object agents. Named module constant (not a
# mutable default argument) so the shared instance can never be aliased/mutated by a caller.
_DEFAULT_RESPONSE_FORMAT = {"type": "json_object"}

# Immutable sentinel distinguishing "argument omitted" from an explicit ``response_format=None``.
# Using a mutable ``{...}`` as a default argument is the classic shared-mutable-default footgun;
# a unique sentinel lets us keep EXACTLY the historical behavior — omitted => json_object,
# explicit None => omit the constraint (array agents) — with an immutable default (api-contract).
_UNSET = object()

# Upper bound on any single text field (system prompt or brief) before it is concatenated /
# serialized / shipped to a subprocess. Real prompts are kilobytes; a 2 MiB ceiling is orders
# of magnitude of headroom yet forbids a hostile ``system = "a" * 1_000_000_000`` from
# exhausting memory across the f-string, the JSON body, and the subprocess argv at once
# (adversarial-input / memory-resource lens). Truncates-with-a-loud-warning rather than
# raising, so a merely-large-but-benign prompt still runs.
_MAX_FIELD_BYTES = 2 * 1024 * 1024

# Character ceiling used to slice a field BEFORE encoding, so a hostile gigabyte string is never
# materialized as bytes. UTF-8 encodes each code point to at most 4 bytes, so a slice of this many
# characters can never exceed _MAX_FIELD_BYTES once encoded; slicing a ``str`` is O(k) in the
# KEPT length, not the input length, so the untrusted tail is dropped without allocating it
# (adversarial-input / memory-resource lens).
_MAX_FIELD_CHARS = _MAX_FIELD_BYTES // 4

# Cap on any model response we pull into memory — the HTTP body from the local endpoint AND the
# stdout of the ``claude`` subprocess. A compromised or buggy backend streaming an unbounded body
# (or /dev/zero behind a reverse proxy), or a runaway CLI writing gigabytes to stdout, must not
# OOM the process; anything past this is refused and falls into the normal fallback path. The CLI
# is capped AFTER the fact (subprocess.run buffers stdout), so the cap here bounds what we ACCEPT
# and forward, not what the child may transiently allocate (adversarial-input / memory lens).
_MAX_RESPONSE_BYTES = 16 * 1024 * 1024

# Bounded retry policy for the local endpoint. Transient faults (a momentary connection refuse
# during backend startup, a read timeout under load, a 5xx) get a small, bounded number of
# retries with backoff; permanent faults (4xx, malformed/undecodable body, missing keys) are
# NOT retried — retrying them only burns the deadline (network / error-handling-resilience).
_LOCAL_ATTEMPTS = 3
_LOCAL_BACKOFF_S = 0.5
# Full-jitter fraction: the actual sleep is a uniform random point in [base/2, base], so many
# concurrent callers hitting the same transient fault do NOT retry in lockstep and stampede the
# recovering backend (network lens — thundering-herd avoidance).
_BACKOFF_JITTER = 0.5

# Per-call deadlines. Both are hard upper bounds so a hung backend can never stall a forge phase
# indefinitely (chaos / device-stack lens).
_CLI_TIMEOUT_S = 180
_HTTP_TIMEOUT_S = 300


class BackendUnavailable(RuntimeError, OSError):
    """Raised by ``invoke`` when EVERY configured backend failed to answer.

    Backward-compatibility (api-contract lens): the ORIGINAL runner had no exception handling
    on the local path, so a total outage propagated a raw ``urllib.error.URLError`` (an
    ``OSError``) to the caller — it never returned ``""``. To keep every existing
    ``except OSError``/``except URLError`` site working AND to give a clearer type, this
    subclasses BOTH ``RuntimeError`` (its documented public type) and ``OSError`` (what callers
    could already catch). No dependent caught the empty string because the original never
    produced one; making the outage explicit and loggable is therefore additive, not breaking
    (error-handling-resilience / observability lens).
    """


def _bounded(field: str, value: str) -> str:
    """Return *value* bounded to ``_MAX_FIELD_BYTES`` (UTF-8), warning if it clips.

    Root of the adversarial-input guard: the CHARACTER length is checked first (``len(value)`` is
    O(1) and allocates nothing), and if it exceeds the char ceiling the string is sliced to that
    ceiling BEFORE any ``encode()``. A hostile ``"x" * 10**9`` is therefore never encoded whole —
    at most ``_MAX_FIELD_CHARS`` characters (~0.5 MiB) are materialized as bytes, not a gigabyte.
    Because UTF-8 is <=4 bytes/char, the char-sliced value can still be a little over the byte cap
    (multi-byte code points), so a final byte-level trim enforces the exact bound. Truncation (not
    rejection) keeps a large-but-benign prompt working (adversarial-input / memory-resource lens).
    """
    if len(value) > _MAX_FIELD_CHARS:
        log.warning("%s is %d chars (> %d char cap); truncating before encode",
                    field, len(value), _MAX_FIELD_CHARS)
        value = value[:_MAX_FIELD_CHARS]
    encoded = value.encode("utf-8", errors="ignore")
    if len(encoded) <= _MAX_FIELD_BYTES:
        return value
    log.warning("%s is %d bytes (> %d byte cap); truncating before use",
                field, len(encoded), _MAX_FIELD_BYTES)
    return encoded[:_MAX_FIELD_BYTES].decode("utf-8", errors="ignore")


def _cap_output(field: str, cid: str, value: str) -> str:
    """Return *value* truncated to ``_MAX_RESPONSE_BYTES`` (UTF-8), warning if it clips.

    The ``claude`` CLI's stdout is captured whole by ``subprocess.run`` and returned verbatim by
    the original code — an unbounded amount of memory forwarded downstream if a runaway/compromised
    CLI emits gigabytes. This applies the SAME output cap the local HTTP path already enforces, so
    both backends bound what they ACCEPT and forward (adversarial-input / memory-resource lens).
    """
    encoded = value.encode("utf-8", errors="ignore")
    if len(encoded) <= _MAX_RESPONSE_BYTES:
        return value
    log.warning("[%s] %s is %d bytes (> %d cap); truncating model output",
                cid, field, len(encoded), _MAX_RESPONSE_BYTES)
    return encoded[:_MAX_RESPONSE_BYTES].decode("utf-8", errors="ignore")


def _elapsed_ms(started: float) -> float:
    """Milliseconds since a ``time.monotonic()`` start marker (monotonic == immune to clock skew).

    Centralizes latency measurement so every backend span reports timing the same way, giving the
    observability lens per-operation latency without a metrics dependency (observability lens).
    """
    return (time.monotonic() - started) * 1000.0


def build_invoker(
    ws: Path,
    system: str,
    user_message_fn: Callable[[str], str],
    response_format: Optional[dict] = _UNSET,  # type: ignore[assignment]
) -> Callable[[str], str]:
    """Return ``invoke(brief: str) -> str`` backed by the Claude Code subagent.

    Args:
        ws: FORGE_WORKSPACE root path.
        system: Fully-loaded system-prompt string.
        user_message_fn: The ``user_message`` callable from ``*_prompt`` module.
        response_format: OpenAI-compatible ``response_format`` sent on the local (Ollama) path.
            Behavior is UNCHANGED from prior releases:
              * omitted           -> ``{"type": "json_object"}`` (single-JSON-object agents);
              * ``None`` (explicit) -> omit the constraint entirely, so agents that emit a JSON
                *array* are not forced to a single object (the ``json_object`` constraint drops
                the other array elements, emptying multi-item extractors — see n600);
              * an explicit dict  -> sent verbatim.

    The public signature and the returned ``invoke(brief) -> str`` contract are unchanged; the
    only difference is the default is now an immutable sentinel instead of a shared mutable dict,
    removing the mutable-default footgun without altering any caller's behavior (api-contract).
    """
    # Resolve the immutable sentinel to the historical semantics (see docstring). Every existing
    # call is preserved: build_invoker(WS, sys, um) -> json_object; response_format=None -> omit.
    effective_format: Optional[dict]
    if response_format is _UNSET:
        effective_format = _DEFAULT_RESPONSE_FORMAT
    else:
        effective_format = response_format

    # Bound the system prompt ONCE at build time — it is fixed for the invoker's life, so there
    # is no reason to re-check it per brief (adversarial-input / performance lens).
    safe_system = _bounded("system", system)

    # Lock-guarded, single-insert, membership-checked backend resolution. Replaces the old
    # unguarded sys.path.insert + import backend_config (security / concurrency / memory).
    spec = resolve_backend(ws)
    base_url = spec["base_url"]
    model = spec["model"]
    native_kind = spec["native"]["kind"]
    log.debug("subagent runner backend: provider=%s kind=%s base_url=%s model=%s",
              spec.get("provider"), native_kind, base_url, model)

    def _via_claude_cli(user_msg: str, cid: str) -> Optional[str]:
        """Elicit via ``claude -p``; return stdout, or None if unavailable/failed.

        Returns None (not a raise) so both backends fail uniformly (maintainability). Catches
        only ``TimeoutExpired``/``OSError`` so ``KeyboardInterrupt``/``SystemExit`` still
        propagate — a Ctrl-C is never masked into a fallback (error-handling-resilience).
        """
        if native_kind != "anthropic" or not shutil.which("claude"):
            return None
        prompt = f"{safe_system}\n\n{user_msg}"
        started = time.monotonic()  # span start: measure end-to-end CLI latency (observability)
        try:
            proc = subprocess.run(  # noqa: S603 - fixed argv, no shell, no user-controlled exe
                ["claude", "-p", prompt, "--output-format", "text"],
                cwd=str(ws),
                capture_output=True,
                text=True,
                timeout=_CLI_TIMEOUT_S,
            )
        except subprocess.TimeoutExpired:
            log.warning("[%s] claude CLI timed out after %.0fms (limit %ss); fallback=local",
                        cid, _elapsed_ms(started), _CLI_TIMEOUT_S)
            return None
        except OSError as exc:
            log.warning("[%s] claude CLI spawn failed (%s) after %.0fms; fallback=local",
                        cid, exc.__class__.__name__, _elapsed_ms(started))
            return None
        ms = _elapsed_ms(started)
        if proc.returncode != 0:
            # Non-zero exit is a real, diagnosable failure — surface the code, latency, and a
            # bounded slice of stderr so the fallback is not invisible (observability).
            log.warning("[%s] claude CLI exited %d in %.0fms: %s; fallback=local",
                        cid, proc.returncode, ms, (proc.stderr or "").strip()[:500])
            return None
        # Success — cap stdout to the shared output limit (a runaway CLI must not forward gigabytes
        # downstream), then return it verbatim INCLUDING an empty string, which is a valid reply and
        # must not be coerced into a fallback (adversarial-input / logic-error / math-correctness).
        out = _cap_output("claude CLI stdout", cid, proc.stdout)
        log.info("[%s] claude-cli ok: %d chars in %.0fms", cid, len(out), ms)
        return out

    def _request_local(user_msg: str) -> str:
        """Send one local HTTP request; return the parsed content string.

        Separate from the retry loop so the loop reads as pure policy. Response is read under a
        byte cap and decoded strictly (a non-UTF-8 body raises, caught by the loop's parse arm).
        """
        payload: dict = {
            "model": model,
            "temperature": 0,
            "messages": [
                {"role": "system", "content": safe_system},
                {"role": "user", "content": user_msg},
            ],
            "stream": False,
        }
        if effective_format is not None:  # None -> array agent -> omit the constraint (unchanged)
            payload["response_format"] = effective_format
        # backend_config confines base_url to loopback/private hosts; this asserts the scheme is
        # http(s) so a mutated spec can't smuggle file:// into urlopen (defense-in-depth SSRF).
        # Log at WARNING before raising so this misconfiguration is diagnosable from logs alone,
        # even if the caller swallows the exception (observability lens).
        if not base_url.startswith(("http://", "https://")):
            log.warning("refusing non-http local base_url %r; check backend config", base_url)
            raise BackendUnavailable(f"refusing non-http local base_url {base_url!r}")
        body = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(  # noqa: S310 - loopback/private endpoint, scheme-checked above
            base_url + "/chat/completions",
            data=body,
            headers={"Content-Type": "application/json"},
        )
        with urllib.request.urlopen(req, timeout=_HTTP_TIMEOUT_S) as resp:  # noqa: S310
            raw = resp.read(_MAX_RESPONSE_BYTES + 1)
        if len(raw) > _MAX_RESPONSE_BYTES:
            raise ValueError(f"local response exceeded {_MAX_RESPONSE_BYTES}-byte cap")
        data = json.loads(raw.decode("utf-8", errors="strict"))  # may raise UnicodeDecodeError
        return data["choices"][0]["message"]["content"]

    def _via_local(user_msg: str, cid: str) -> Optional[str]:
        """Elicit via the local endpoint with bounded, jittered retry; None on total failure.

        Transient faults (timeout/refused/reset/5xx) retry up to ``_LOCAL_ATTEMPTS`` with
        full-jitter backoff; permanent faults (4xx, bad/non-UTF-8 body, missing keys, oversize)
        do not retry. Returns None to match the CLI path's failure protocol; BaseExceptions
        (Ctrl-C) are not caught and propagate (network / chaos / error-handling-resilience).
        """
        last: Optional[BaseException] = None
        for attempt in range(1, _LOCAL_ATTEMPTS + 1):
            started = time.monotonic()  # span start: per-attempt HTTP latency (observability)
            try:
                content = _request_local(user_msg)
                log.info("[%s] local-endpoint ok: %d chars in %.0fms (attempt %d)",
                         cid, len(content), _elapsed_ms(started), attempt)
                return content
            except (json.JSONDecodeError, UnicodeDecodeError, KeyError,
                    IndexError, TypeError, ValueError) as exc:
                # Deterministic bad shape/encoding (incl. non-UTF-8 bytes) — retrying can't help.
                log.warning("[%s] local endpoint returned unparseable response (%s); no retry",
                            cid, exc.__class__.__name__)
                return None
            except (urllib.error.URLError, TimeoutError, OSError) as exc:
                # HTTP 4xx is a permanent client-side refusal; everything else here is a genuine
                # transient transport fault. Inlined (was two single-call helpers) so the retry
                # decision and its rationale live at the one place they matter (minimalist lens).
                is_http = isinstance(exc, urllib.error.HTTPError)
                if is_http and not 500 <= exc.code < 600:
                    log.warning("[%s] local endpoint HTTP %d (permanent); no retry", cid, exc.code)
                    return None
                last = exc
                if attempt < _LOCAL_ATTEMPTS:
                    base = _LOCAL_BACKOFF_S * attempt
                    delay = base * (1.0 - _BACKOFF_JITTER * random.random())  # noqa: S311 - jitter, not crypto
                    log.warning("[%s] local endpoint transient failure (%s) attempt %d/%d; "
                                "retrying in %.2fs", cid, exc.__class__.__name__,
                                attempt, _LOCAL_ATTEMPTS, delay)
                    time.sleep(delay)
        log.warning("[%s] local endpoint unreachable after %d attempts (last: %s)",
                    cid, _LOCAL_ATTEMPTS, last.__class__.__name__ if last else "unknown")
        return None

    def invoke(brief: str) -> str:
        """Return raw model output, trying the CLI then the local endpoint.

        Renders the user message ONCE and reuses it across both paths (performance). Uses
        ``is not None`` (not ``or``) so an empty-but-successful CLI reply is returned verbatim
        (logic-error / math-correctness). Raises :class:`BackendUnavailable` if both miss.

        Observability: opens an invoke-level span (start + total latency), tags every line with a
        correlation ``cid``, and closes the span naming the backend that answered — so one request
        is a complete, timed, greppable trace even across a CLI->local fallback.
        """
        cid = uuid.uuid4().hex[:8]
        started = time.monotonic()  # invoke span start (monotonic == clock-skew immune)
        # Bound the RAW brief BEFORE it reaches user_message_fn, so a hostile multi-gigabyte
        # brief can't exhaust memory inside the caller's template function; then bound the
        # rendered message too, since user_message_fn may expand it (adversarial-input lens).
        safe_brief = _bounded("brief", brief)
        user_msg = _bounded("user_message", user_message_fn(safe_brief))
        log.debug("[%s] invoke start: kind=%s msg=%d chars", cid, native_kind, len(user_msg))

        result = _via_claude_cli(user_msg, cid)
        if result is not None:
            log.info("[%s] invoke ok via=claude-cli chars=%d total=%.0fms",
                     cid, len(result), _elapsed_ms(started))
            return result
        result = _via_local(user_msg, cid)
        if result is not None:
            log.info("[%s] invoke ok via=local chars=%d total=%.0fms",
                     cid, len(result), _elapsed_ms(started))
            return result
        # Total outage: one WARNING closing the span, naming the whole fallback chain tried and the
        # total latency, so the failure is fully diagnosable from telemetry even if the caller
        # swallows the raise (observability lens).
        log.warning("[%s] invoke failed via=claude-cli,local total=%.0fms; both backends failed",
                    cid, _elapsed_ms(started))
        raise BackendUnavailable(
            f"[{cid}] no backend answered: claude CLI and the local endpoint both failed "
            "(see WARNING logs from runners.subagent_runner for the cause)"
        )

    return invoke
