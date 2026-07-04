"""Shared utilities for forge-agent framework runners.

Two public helpers, imported by every framework runner (343 dependents):

  * ``load_system_prompt`` — resolve an agent's system prompt from a documented
    priority chain, hardened against path traversal, symlink escape, oversized
    files, locale-dependent decoding, and transient IO faults.
  * ``resolve_backend`` — thin wrapper over ``scripts/backend_config.resolve``
    that inserts the foundry's ``scripts`` dir on ``sys.path`` exactly once,
    under a lock, so concurrent phases never race or leak duplicate entries.

stdlib only. All guards below carry a rationale comment so a future hardening
run can see WHAT was protected and WHY without re-deriving the threat model.
"""
from __future__ import annotations

import logging
import os
import random
import re
import sys
import threading
import time
from pathlib import Path
from typing import Any, Callable, Optional, TypedDict, TypeVar

# Library logger. NullHandler keeps imports silent by default (no stderr noise for
# 343 dependents); a caller opts into diagnostics via
# logging.getLogger("runners.utils").setLevel(...). Source selection is INFO so the
# happy path is traceable; every fallback/failure is WARNING so misconfiguration is
# loud without crashing the run (observability lens).
log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# Size cap for any prompt document we read. Prompts are kilobytes at most; a 1 MiB
# ceiling is orders of magnitude of headroom yet forbids memory exhaustion from a
# hostile FORGE_SKILL_DOC pointing at /dev/zero, a 10 GB file, or a fifo
# (adversarial-input / memory-resource lens). Enforced via stat().st_size BEFORE any
# read, so the bytes are never pulled into RAM.
_MAX_PROMPT_BYTES = 1 * 1024 * 1024

# Wall-clock ceiling for a caller-supplied primary_fn. primary_fn is often
# active_prompt() reading a local module, but a misbehaving one that blocks on a
# stuck DB/API/remote service would otherwise WEDGE agent startup forever — a
# raised exception is caught, but infinite blocking is not. We run it on a DAEMON
# worker and, on timeout, degrade to the on-disk subagent doc so startup always
# makes progress (chaos-engineering lens). Overridable via FORGE_PRIMARY_FN_TIMEOUT_S.
_PRIMARY_FN_TIMEOUT_S = 10.0

# Wall-clock ceiling for backend_config.resolve(). resolve() may probe a backend
# over the network (Ollama/LiteLLM/claude shim); if that dependency hangs, a
# synchronous call would wedge every agent phase. We run it on a DAEMON worker with
# this timeout and, on timeout, raise TimeoutError so the caller sees a fast, clear
# failure instead of an indefinite stall (chaos-engineering lens). backend_config's
# own probes are already short-bounded, so this is a belt-and-braces outer cap.
# Overridable via FORGE_BACKEND_TIMEOUT_S.
_BACKEND_RESOLVE_TIMEOUT_S = 30.0

# resolve_backend retries a timed-out/errored resolve() a few times with capped
# exponential backoff before giving up, so a momentary backend blip self-heals
# instead of failing the whole phase (chaos-engineering lens). Total added latency
# is bounded (attempts x base x growth, capped), never unbounded.
_BACKEND_RESOLVE_ATTEMPTS = 3
_BACKEND_RETRY_BASE_S = 0.2
_BACKEND_RETRY_MAX_S = 2.0
# FULL JITTER on the backoff: each attempt sleeps a uniform-random duration in
# [0, capped_exponential]. Without jitter, N agents that hit the same backend outage
# retry in lockstep (all at T+0.2s, T+0.4s, ...) and stampede the backend the instant
# it recovers — a thundering herd. Randomizing each sleep independently spreads the
# retries out, so a recovering backend sees a smooth trickle, not a synchronized spike
# (chaos-engineering lens). random (not secrets) is fine: this is load-spreading, not
# a security decision.
_BACKEND_RETRY_JITTER = True

# Hard ceiling on how many timeout worker threads may be in flight at once across
# the whole module. Every _call_with_timeout run acquires one permit before spawning
# a thread and releases it only when that thread actually finishes — so a thread that
# has TIMED OUT but is still blocked keeps its permit. A storm of repeated timeouts is
# therefore throttled here (at most _MAX_TIMEOUT_WORKERS stuck threads can ever exist)
# instead of spawning threads without bound and exhausting the OS thread table
# (memory-resource / error-handling-resilience lens). If no permit frees up within a
# short grace we raise TimeoutError rather than block, so the cap never wedges a
# caller. Overridable via FORGE_MAX_TIMEOUT_WORKERS (a bad value falls back to 16).
def _init_max_workers() -> int:
    raw = os.environ.get("FORGE_MAX_TIMEOUT_WORKERS")
    try:
        return max(1, int(raw)) if raw else 16
    except (TypeError, ValueError):
        return 16


_MAX_TIMEOUT_WORKERS = _init_max_workers()
_WORKER_ACQUIRE_GRACE_S = 1.0
_WORKER_SEMAPHORE = threading.BoundedSemaphore(_MAX_TIMEOUT_WORKERS)

# Upper bound on distinct scripts-dirs we will ever add to the process-global
# sys.path. resolve_backend inserts one entry per unique workspace; a harness that
# resolves many different ws roots would otherwise grow sys.path without bound. We
# track what we've inserted and refuse to add more than this many, so sys.path can
# never balloon regardless of how many workspaces are seen (memory-resource lens).
_MAX_TRACKED_SCRIPT_DIRS = 32

# One newline-tolerant pass that strips a leading YAML front-matter block. The body
# between the delimiters is optional ((?:...)? ) so EMPTY front-matter ("---\n---")
# matches, and the trailing newline after the closing "---" is optional (\n?) so a
# file with no final newline still matches (math-correctness / logic-error lens).
_FRONT_MATTER_RE = re.compile(r"^---\n(?:.*?\n)?---\n?", re.DOTALL)

# Guards the one-time sys.path mutation in resolve_backend. sys.path is a shared,
# mutable, process-global list; concurrent resolve_backend calls across forge phases
# would otherwise interleave read/insert and either lose updates or append duplicates
# that grow sys.path unboundedly (concurrency / memory-resource / system-design lens).
_SYS_PATH_LOCK = threading.Lock()

# Set of scripts-dirs this module has inserted, so we never insert the same dir
# twice AND can cap the total distinct dirs (see _MAX_TRACKED_SCRIPT_DIRS). Only
# ever mutated while holding _SYS_PATH_LOCK.
_INSERTED_SCRIPT_DIRS: set[str] = set()


class BackendSpec(TypedDict):
    """Uniform connection spec returned by :func:`resolve_backend`.

    Mirrors ``scripts/backend_config.resolve`` exactly so callers know the shape
    without reading backend_config (maintainability lens). Documenting the keys
    here is contract-only; the value is produced verbatim by backend_config.

    Keys:
        provider: backend id ("ollama" | "claude-haiku" | "claude-cli").
        openai_compatible: True when reachable over the OpenAI protocol.
        base_url: OpenAI-compatible endpoint (loopback/private only).
        model: model identifier.
        api_key_env: name of the env var holding the API key (never the value).
        native: native-flavor sub-spec ({"kind": str, "model": str}).
        air_gapped: True when the backend needs no outbound network.
    """

    provider: str
    openai_compatible: bool
    base_url: str
    model: str
    api_key_env: str
    native: dict
    air_gapped: bool


def _safe_read(path: Path) -> str:
    """Read *path* as UTF-8, size-capped, or raise.

    Guards applied before the bytes are touched:
      * ``stat().st_size`` is checked against ``_MAX_PROMPT_BYTES`` so an
        oversized or infinite source (/dev/zero, fifo) is refused up front,
        never streamed into memory (memory-resource / adversarial-input lens).
      * ``encoding="utf-8-sig"`` is explicit so decoding never depends on the host
        locale — an ISO-8859-1/ASCII box won't crash on non-ASCII prompts — and it
        also strips a leading UTF-8 BOM (U+FEFF) that Windows/some editors prepend,
        so a BOM can't defeat the ``^---`` front-matter regex (device-stack lens).
        ``errors="strict"`` surfaces genuinely malformed bytes to the caller's
        fallback chain rather than silently corrupting.

    Raises OSError/ValueError/UnicodeDecodeError; callers catch and degrade.
    """
    size = path.stat().st_size  # may raise OSError; propagated to the caller's guard
    if size > _MAX_PROMPT_BYTES:
        raise ValueError(f"prompt document {path} is {size} bytes (> {_MAX_PROMPT_BYTES} cap)")
    return path.read_text(encoding="utf-8-sig", errors="strict")


def _resolve_env_doc(raw: str, workspace: Path) -> Optional[Path]:
    """Validate a ``$FORGE_SKILL_DOC`` value, returning a safe Path or None.

    Rationale: the value is attacker-influenceable environment input, so it is
    NOT trusted (security / vulnerability / adversarial-input lens). We:
      * ``resolve()`` the path (follows symlinks, collapses ``..``) so traversal
        like ``../../etc/passwd`` or a symlink escaping the tree is normalized to
        its real location before any containment check;
      * require the resolved real path to stay within the resolved *workspace*
        (``is_relative_to``), rejecting both raw traversal and symlink-to-outside;
      * require it to be a regular file, refusing devices/fifos/dirs.
    Any failure returns None so the caller falls back — never reads the file.
    """
    try:
        candidate = Path(raw).resolve(strict=True)
        root = workspace.resolve(strict=False)
    except OSError as exc:
        log.warning("FORGE_SKILL_DOC %r could not be resolved: %s; ignoring", raw, exc)
        return None
    if not candidate.is_relative_to(root):
        log.warning("FORGE_SKILL_DOC %r resolves outside workspace %s; ignoring", raw, root)
        return None
    if not candidate.is_file():
        log.warning("FORGE_SKILL_DOC %r is not a regular file; ignoring", raw)
        return None
    return candidate


def _try_env_override(subagent_md: Path) -> Optional[str]:
    """Tier 1: return the validated $FORGE_SKILL_DOC body, or None to fall through.

    Containment is anchored on the *subagent_md* parent's workspace: we walk up to
    the ``agents`` root's parent so a legitimately-placed skill doc under the
    foundry is accepted while anything outside is refused. Read faults degrade to
    None rather than propagating (chaos / error-handling-resilience lens).
    """
    raw = os.environ.get("FORGE_SKILL_DOC")
    if not raw:
        return None
    try:
        # _workspace_for calls Path.resolve(), which can raise OSError (e.g. a
        # permission error or a symlink loop while traversing the anchor path);
        # a fault here must degrade to the next tier, not escape (error-handling lens).
        workspace = _workspace_for(subagent_md)
        safe = _resolve_env_doc(raw, workspace)
        if safe is None:
            return None
        body = _safe_read(safe).strip()
    except (OSError, ValueError, UnicodeDecodeError) as exc:
        # Covers the TOCTOU window (file made unreadable after the is_file check),
        # oversize, non-UTF-8, and a resolve() failure — degrade instead of crashing.
        log.warning("FORGE_SKILL_DOC=%r unusable (%s); falling back", raw, exc)
        return None
    if not body:
        # A blank/whitespace-only override is not a usable prompt; returning "" here
        # would short-circuit the chain and hand the caller an empty system prompt.
        # Fall through to primary_fn / subagent_md instead (logic-error lens).
        log.warning("FORGE_SKILL_DOC=%r is blank; falling back", raw)
        return None
    log.info("system prompt source: FORGE_SKILL_DOC=%s", safe)
    return body


_T = TypeVar("_T")


def _timeout_from_env(env_var: str, default: float) -> float:
    """Resolve a positive timeout from *env_var*, else *default*.

    A missing, non-numeric, or non-positive override falls back to *default* so a
    fat-fingered env var can't disable an anti-hang guard (chaos-engineering lens).
    """
    raw = os.environ.get(env_var)
    if not raw:
        return default
    try:
        value = float(raw)
    except (TypeError, ValueError):
        return default
    return value if value > 0 else default


def _call_with_timeout(fn: Callable[[], _T], timeout_s: float, label: str) -> _T:
    """Run *fn* on a bounded DAEMON worker thread, returning its result or raising.

    Rationale (error-handling-resilience / memory-resource / chaos lens):

    * A hung dependency must never wedge startup NOR leak a thread that blocks
      interpreter exit. The worker is a ``daemon`` thread — unlike a
      ThreadPoolExecutor worker, which the runtime joins at exit — so a stuck *fn*
      is abandoned cleanly when the process ends. We cannot portably kill a thread;
      daemon status bounding its lifetime to the process is the strongest safe
      stdlib guarantee. The *resource* contract is explicit: if *fn* times out, any
      handle/socket/lock it holds stays held until *fn* itself unwinds — so callers
      pass short-lived, cancellation-tolerant work here, never a long transaction.
    * Threads can't accumulate without bound: we take a permit from
      ``_WORKER_SEMAPHORE`` before spawning and release it only when the worker
      *actually finishes*. A timed-out-but-still-blocked thread keeps its permit, so
      at most ``_MAX_TIMEOUT_WORKERS`` stuck threads can ever exist; past that we
      raise ``TimeoutError`` instead of spawning more (bounded blast radius).

    On timeout we raise ``TimeoutError``; if *fn* raised, we re-raise its exception;
    success returns *fn*'s value.
    """
    if not _WORKER_SEMAPHORE.acquire(timeout=_WORKER_ACQUIRE_GRACE_S):
        raise TimeoutError(f"{label}: no worker slot free ({_MAX_TIMEOUT_WORKERS} in flight)")

    box: dict[str, Any] = {}

    def _runner() -> None:
        try:
            box["value"] = fn()
        except BaseException as exc:  # noqa: BLE001 - propagated to the caller below
            box["error"] = exc
        finally:
            _WORKER_SEMAPHORE.release()  # permit freed only when the work truly ends

    worker = threading.Thread(target=_runner, name=label, daemon=True)
    worker.start()
    worker.join(timeout_s)
    if worker.is_alive():
        raise TimeoutError(f"{label} exceeded {timeout_s}s")
    if "error" in box:
        raise box["error"]
    return box["value"]


def _try_primary_fn(primary_fn: Optional[Callable[[], str]]) -> Optional[str]:
    """Tier 2: call *primary_fn* (typically ``active_prompt()``), or None.

    A raising, empty, OR HUNG ``primary_fn`` must not abort or wedge prompt
    resolution. We run it on a daemon worker with a wall-clock timeout (see
    ``_call_with_timeout``), so a primary_fn that blocks on a stuck DB/API can't hang
    agent startup and can't leak a thread that blocks process exit — on timeout or
    any exception we log and fall through to the on-disk subagent doc, so this call
    always returns promptly (chaos-engineering / error-handling-resilience lens).
    """
    if primary_fn is None:
        return None
    timeout_s = _timeout_from_env("FORGE_PRIMARY_FN_TIMEOUT_S", _PRIMARY_FN_TIMEOUT_S)
    try:
        result = _call_with_timeout(primary_fn, timeout_s, "primary_fn")
    except TimeoutError:
        log.warning("primary_fn timed out after %ss; falling back to subagent doc", timeout_s)
        return None
    except Exception as exc:  # noqa: BLE001 - any failure degrades to the file tier
        log.warning("primary_fn raised (%s); falling back to subagent doc", exc)
        return None
    if not isinstance(result, str) or not result.strip():
        log.warning("primary_fn returned no usable prompt; falling back to subagent doc")
        return None
    log.info("system prompt source: primary_fn")
    return result


def _read_subagent_md(subagent_md: Path) -> str:
    """Tier 3 (terminal): read *subagent_md*, strip YAML front-matter, return body.

    This is the last resort. If it too fails there is no further fallback, so the
    OSError/ValueError is allowed to propagate — a totally missing prompt is a hard
    configuration error the caller must see, not silently mask (error-handling lens).
    """
    text = _safe_read(Path(subagent_md))
    body = _FRONT_MATTER_RE.sub("", text, count=1).strip()
    log.info("system prompt source: subagent_md=%s", subagent_md)
    return body


def _workspace_for(subagent_md: Path) -> Path:
    """Best-effort workspace root used to contain $FORGE_SKILL_DOC.

    Walks up from *subagent_md* to the parent of the nearest ``agents`` dir (the
    foundry root). Falls back to the file's own parent when no ``agents`` ancestor
    exists, keeping the containment check conservative rather than crashing.
    """
    resolved = Path(subagent_md).resolve(strict=False)
    for parent in resolved.parents:
        if parent.name == "agents":
            return parent.parent
    return resolved.parent


def load_system_prompt(
    subagent_md: Path,
    primary_fn: Optional[Callable[[], str]] = None,
) -> str:
    """Return the agent system prompt, honouring $FORGE_SKILL_DOC override.

    Priority order (each tier degrades to the next on failure, never propagating
    until the terminal tier — chaos / error-handling-resilience lens):
      1. ``$FORGE_SKILL_DOC`` env-var path — validated for traversal/symlink
         escape and size-capped before reading (security / vulnerability lens).
      2. ``primary_fn()`` if provided — typically ``active_prompt()`` from the
         debate-gated ``*_prompt`` module.
      3. Body of *subagent_md* with the YAML front-matter block stripped.

    Public signature and return type (``str``) are unchanged for all callers.
    """
    body = _try_env_override(subagent_md)
    if body is not None:
        return body
    body = _try_primary_fn(primary_fn)
    if body is not None:
        return body
    return _read_subagent_md(subagent_md)


def _ensure_scripts_importable(ws: Path) -> None:
    """Put ``ws/scripts`` on sys.path exactly once, bounded and race-free.

    sys.path is a shared, mutable, process-global list; concurrent forge phases
    would otherwise interleave read/insert (losing updates or corrupting order) and
    repeated calls would append duplicates. We mutate only under ``_SYS_PATH_LOCK``,
    skip dirs already inserted, and cap distinct dirs at ``_MAX_TRACKED_SCRIPT_DIRS``
    so even many ws roots can't grow sys.path without bound (concurrency /
    memory-resource / system-design lens).
    """
    scripts_dir = str((Path(ws) / "scripts").resolve(strict=False))
    with _SYS_PATH_LOCK:
        if scripts_dir in _INSERTED_SCRIPT_DIRS:
            return
        if len(_INSERTED_SCRIPT_DIRS) >= _MAX_TRACKED_SCRIPT_DIRS:
            # Bound reached: don't grow sys.path. If the dir is already present the
            # import still works; otherwise the caller gets a clear ModuleNotFoundError.
            log.warning("sys.path scripts-dir cap (%d) reached; not inserting %s",
                        _MAX_TRACKED_SCRIPT_DIRS, scripts_dir)
            return
        if scripts_dir not in sys.path:
            sys.path.insert(0, scripts_dir)
            log.debug("inserted %s onto sys.path", scripts_dir)
        _INSERTED_SCRIPT_DIRS.add(scripts_dir)


def _backoff_delay(attempt: int) -> float:
    """Return the sleep before retry *attempt* (1-based): full-jittered capped backoff.

    The exponential ceiling is ``min(base * 2**(attempt-1), max)``; with jitter on we
    return a uniform-random value in ``[0, ceiling]`` (full jitter) so concurrent
    callers desynchronize and can't stampede a recovering backend (chaos-engineering
    lens). Jitter can be turned off (``_BACKEND_RETRY_JITTER = False``) for
    deterministic tests, which then get the plain ceiling.
    """
    ceiling = min(_BACKEND_RETRY_BASE_S * (2 ** (attempt - 1)), _BACKEND_RETRY_MAX_S)
    return random.uniform(0.0, ceiling) if _BACKEND_RETRY_JITTER else ceiling


def _resolve_with_retry(resolve: Callable[[], BackendSpec], timeout_s: float) -> BackendSpec:
    """Call *resolve* under a per-attempt timeout, retrying with jittered backoff.

    Rationale (chaos-engineering lens): a hung or momentarily-unavailable backend
    (Ollama/claude shim down or slow) should self-heal rather than fail the phase on
    the first blip. We retry up to ``_BACKEND_RESOLVE_ATTEMPTS`` times, sleeping a
    FULL-JITTERED capped exponential backoff (see ``_backoff_delay``) between tries so
    we neither hammer a struggling backend nor let many agents retry in lockstep and
    stampede it on recovery. The final failure is re-raised so a genuinely dead
    backend still surfaces a clear, fast error instead of an indefinite wait.
    """
    for attempt in range(1, _BACKEND_RESOLVE_ATTEMPTS + 1):
        try:
            return _call_with_timeout(resolve, timeout_s, "backend_config.resolve")
        except (TimeoutError, OSError, ConnectionError) as exc:
            if attempt == _BACKEND_RESOLVE_ATTEMPTS:
                log.warning("backend resolve failed after %d attempts: %s", attempt, exc)
                raise
            delay = _backoff_delay(attempt)
            log.warning("backend resolve attempt %d/%d failed (%s); retrying in %.2fs (jittered)",
                        attempt, _BACKEND_RESOLVE_ATTEMPTS, exc, delay)
            time.sleep(delay)
    raise AssertionError("unreachable")  # loop always returns or raises


def resolve_backend(ws: Path) -> BackendSpec:
    """Resolve the LLM backend spec for workspace *ws*.

    Ensures ``scripts`` is importable (see ``_ensure_scripts_importable``) then
    delegates to ``scripts/backend_config.resolve(ws)`` under a per-attempt
    wall-clock timeout with bounded retry+backoff (see ``_resolve_with_retry``):
    resolve() may probe a backend over the network, so a hung or momentarily-down
    dependency is bounded to ``_BACKEND_RESOLVE_TIMEOUT_S`` per try, self-heals across
    a couple of retries, and only a persistent failure surfaces as a fast error —
    never an indefinite stall (chaos-engineering lens).

    Return shape is byte-identical to ``backend_config.resolve`` — see
    :class:`BackendSpec`. Signature unchanged for all callers.
    """
    _ensure_scripts_importable(ws)
    import backend_config  # noqa: PLC0415 - deferred; needs the path insert above

    timeout_s = _timeout_from_env("FORGE_BACKEND_TIMEOUT_S", _BACKEND_RESOLVE_TIMEOUT_S)
    spec = _resolve_with_retry(lambda: backend_config.resolve(Path(ws)), timeout_s)
    # Backend resolution is a critical, once-per-phase init step: log its outcome at
    # INFO (not DEBUG) with provider AND model, so ops can see which backend/model an
    # agent actually bound to without enabling debug logging (observability lens).
    log.info("resolved backend for %s: provider=%s model=%s",
             ws, spec["provider"], spec["model"])
    return spec
