#!/usr/bin/env python3
# Used by: shared infra — LLM backend resolution for EVERY phase4_* agent workflow + runners.
"""
Central backend switch for every component (agents, judge, debaters, evolvers).

One provider toggle drives the whole foundry. Swapping models is a one-line
change in config.toml ([backend].provider). Providers:

    - "ollama"        : local, OpenAI-compatible at http://127.0.0.1:11434/v1
    - "claude-haiku"  : Anthropic claude-haiku-4-5 (OpenAI path via LiteLLM proxy)
    - "claude-cli"    : Anthropic via the `claude -p` CLI shim (no API credits)
    - "auto"          : pick the first REACHABLE backend (see _auto_detect) —
                        prefers Claude inside a Claude Code session, always
                        falls back to local Ollama; never selects a backend
                        whose shim/proxy isn't actually listening.

Components that only speak the OpenAI protocol (SkillClaw, EverOS's OpenAI path)
reach Claude through a local LiteLLM proxy, so Claude stays interchangeable
everywhere. Ollama is natively OpenAI-compatible and needs no shim.

Resilience & safety: a missing, unreadable, or malformed config.toml never
crashes resolution — it degrades to defaults+env with a logged warning. Liveness
probes are confined to loopback/private hosts (the only places a foundry backend
runs), so an attacker-controlled base_url in the environment cannot turn this into
an SSRF probe of arbitrary public hosts. All name resolution is bounded by a
timeout (run in a throwaway daemon thread — never via the process-global
socket.setdefaulttimeout, so concurrent callers can't race on it) so a slow/hung
system resolver can never stall startup, and the probe connects to the SAME
address that was security-checked (no TOCTOU DNS rebind between check and connect).
When 'auto' finds nothing reachable it returns a fallback spec tagged
``unverified: True`` so a caller can tell a healthy pick from a dead-endpoint guess.

stdlib only. Reads config.toml if present (Py3.11+ tomllib), else env vars,
else sane local defaults.
"""
from __future__ import annotations

import ipaddress
import logging
import os
import socket
import time
from pathlib import Path
from urllib.parse import urlparse

try:
    import tomllib  # py3.11+
except ModuleNotFoundError:  # pragma: no cover
    tomllib = None

# Structured, opt-in telemetry for this init path. Silent by default (a library
# NullHandler), so importing this module never emits noise; a caller that wants
# visibility into which config source and provider were chosen can raise the level
# (logging.getLogger("backend_config").setLevel(logging.DEBUG)). Resolution detail
# is DEBUG; degraded/fallback conditions are WARNING so misconfiguration is loud.
log = logging.getLogger(__name__)
# Idempotent handler install (memory-resource lens): re-importing/reloading this module
# must NOT stack a second NullHandler on the same logger. We attach exactly one and only
# if none is already present, so repeated importlib.reload() leaks no handlers.
if not any(isinstance(h, logging.NullHandler) for h in log.handlers):
    log.addHandler(logging.NullHandler())

# Probe timeout: backends are always local (loopback/private), so a live server
# answers a TCP connect in well under 0.4s; the short bound keeps 'auto' snappy and
# fails fast on a down backend instead of stalling the whole foundry on startup.
_PROBE_TIMEOUT_S = 0.4
_PROBE_ATTEMPTS = 2  # one cheap retry absorbs a momentary bind/accept blip (network lens)
# Backoff before the retry connect. A tiny (jittered) pause lets a service that binds its
# port a few ms after the first failure recover into the second attempt, instead of firing
# both connects back-to-back and missing the recovery window (network lens). Kept short so a
# genuinely-down backend still fails auto-detect fast.
_PROBE_BACKOFF_S = 0.05

# Hard ceiling on any name-resolution call. A blocking gethostbyname/getaddrinfo has
# NO timeout of its own and would otherwise hang for the system DNS timeout (15s+),
# or indefinitely on a suspended process — stalling the whole foundry at startup when
# provider='auto' triggers _auto_detect. We cap every lookup at this bound instead
# (network / device-stack / adversarial-input lenses).
_DNS_TIMEOUT_S = 0.5

DEFAULTS = {
    "provider": "ollama",
    "ollama_base_url": "http://127.0.0.1:11434/v1",
    "ollama_model": "qwen2.5:14b-instruct",
    "claude_model": "claude-haiku-4-5",
    "litellm_proxy_url": "http://127.0.0.1:4000/v1",  # universal OpenAI-compat shim
    "claude_cli_shim_url": "http://127.0.0.1:8787/v1",  # OpenAI-compat shim over `claude -p`
}

# Table-driven provider specs — the single source of truth for how each concrete
# provider maps onto the uniform connection dict, so resolve() has no repeated
# near-identical branches (one row per provider; add a backend by adding a row).
_PROVIDER_SPECS = {
    "ollama": {"base_url_key": "ollama_base_url", "model_key": "ollama_model",
               "api_key_env": "OLLAMA_API_KEY", "native_kind": "ollama", "air_gapped": True},
    "claude-haiku": {"base_url_key": "litellm_proxy_url", "model_key": "claude_model",
                     "api_key_env": "ANTHROPIC_API_KEY", "native_kind": "anthropic", "air_gapped": False},
    "claude-cli": {"base_url_key": "claude_cli_shim_url", "model_key": "claude_model",
                   "api_key_env": "FORGE_SHIM_KEY", "native_kind": "openai-cli", "air_gapped": False},
}

# The complete set of accepted provider strings, DERIVED from the two tables above so a
# new backend lights up everywhere by adding exactly one _PROVIDER_SPECS row (no second
# hardcoded list to forget — maintainability lens). 'auto' is a resolver directive, not
# a concrete spec, hence appended rather than stored as a row.
VALID_PROVIDERS = tuple(_PROVIDER_SPECS) + ("auto",)


def _load_config(workspace: Path | None = None) -> dict:
    """Layer config: built-in DEFAULTS, then config.toml's [backend] table if present and
    well-formed, then FORGE_* env overrides. A missing/unreadable/malformed TOML file, or a
    [backend] key that is not a table, is treated as absent — logged as a warning and skipped —
    so a corrupt config never crashes the whole foundry's startup."""
    cfg = dict(DEFAULTS)
    path = (workspace or Path(".")) / "config.toml"
    if tomllib and path.exists():
        try:
            with open(path, "rb") as f:
                data = tomllib.load(f)
        except (tomllib.TOMLDecodeError, OSError, ValueError) as exc:
            log.warning("config.toml at %s is unreadable/malformed (%s); using defaults+env",
                        path, exc.__class__.__name__)
            data = {}
        backend = data.get("backend", {})
        if isinstance(backend, dict):
            cfg.update(backend)
        else:
            log.warning("config.toml [backend] is %s, expected a table; ignoring it",
                        type(backend).__name__)
    # env overrides win (handy for quick experiments / CI)
    for k in cfg:
        env = os.environ.get(f"FORGE_{k.upper()}")
        if env:
            cfg[k] = env
    return cfg


def _is_claude_code_session() -> bool:
    """True when an Anthropic-backed Claude path is plausibly available: the
    ``claude`` CLI is on PATH AND ANTHROPIC_API_KEY is set. Used only to ORDER
    'auto' detection — never to force an unreachable backend (reachability is
    still probed before any provider is chosen)."""
    import shutil
    return bool(os.environ.get("ANTHROPIC_API_KEY")) and shutil.which("claude") is not None


def _openai_base_for(provider: str, cfg: dict) -> str | None:
    """The OpenAI-compatible endpoint a runner actually dials for each provider.
    This is the right thing to probe for liveness because every framework runner
    reaches the backend through this path (claude-haiku => the LiteLLM proxy,
    claude-cli => the `claude -p` shim, ollama => ollama itself)."""
    return {
        "ollama": cfg["ollama_base_url"],
        "claude-haiku": cfg["litellm_proxy_url"],
        "claude-cli": cfg["claude_cli_shim_url"],
    }.get(provider)


def _getaddrinfo_first(host: str) -> str | None:
    """Return the first resolved IP for ``host`` or None on any resolver error.
    Pure wrapper around getaddrinfo (no shared/global state) so it is safe to run
    from a worker thread; all exceptions are contained and logged."""
    try:
        infos = socket.getaddrinfo(host, None, proto=socket.IPPROTO_TCP)
    except (OSError, ValueError, UnicodeError) as exc:
        log.debug("name resolution for %r failed (%s)", host, exc.__class__.__name__)
        return None
    return infos[0][4][0] if infos else None


def _resolve_host_ip(host: str) -> str | None:
    """Resolve a hostname to a single IP under a hard timeout, returning None on any
    failure. Centralizes name resolution so BOTH the SSRF check and the actual connect
    use the SAME resolved address (closing the TOCTOU DNS-rebind window — vulnerability
    lens). Numeric literals bypass the resolver entirely (fast path, no DNS).

    Concurrency: the lookup runs in a short-lived DAEMON thread joined for at most
    _DNS_TIMEOUT_S. We do NOT touch socket.setdefaulttimeout() — that is process-global
    shared mutable state, so two concurrent resolvers would race on it and could restore
    each other's value or leak a 0.5s default onto every unrelated socket in the process
    (concurrency + error-handling-resilience lenses). A thread carries its own result and
    mutates nothing shared, and if the resolver hangs the daemon thread is simply
    abandoned (it cannot block startup) while we return None."""
    if not isinstance(host, str) or not host:
        return None
    try:
        return str(ipaddress.ip_address(host))  # already a literal — no DNS at all
    except ValueError:
        pass
    import threading
    result: list[str | None] = [None]

    def _worker() -> None:
        result[0] = _getaddrinfo_first(host)

    t = threading.Thread(target=_worker, name="backend-config-dns", daemon=True)
    t.start()
    t.join(_DNS_TIMEOUT_S)
    if t.is_alive():
        log.debug("name resolution for %r exceeded %ss; treating as unresolved", host, _DNS_TIMEOUT_S)
        return None
    return result[0]


def _is_local_ip(ip: str) -> bool:
    """True only for loopback / link-local / RFC-1918-private ADDRESSES — the only places a
    foundry backend ever listens. Takes an already-resolved literal so the SSRF decision and
    the eventual connect key off one identical address, giving the caller SSRF containment
    with no second, rebindable lookup."""
    try:
        parsed = ipaddress.ip_address(ip)
    except ValueError:
        return False
    return parsed.is_loopback or parsed.is_private or parsed.is_link_local


def _is_local_host(host: str) -> bool:
    """True only for loopback / link-local / RFC-1918-private hosts — the only places a foundry
    backend ever listens. Confines liveness probes to those, so a base_url injected via env can
    never make _reachable() open a connection to an arbitrary public host (SSRF containment).
    Resolution is timeout-bounded via _resolve_host_ip so a hung DNS server cannot stall this."""
    if host in ("localhost", ""):
        return True
    ip = _resolve_host_ip(host)
    return ip is not None and _is_local_ip(ip)


def _reachable(base_url: str, timeout: float = _PROBE_TIMEOUT_S) -> bool:
    """Cheap TCP liveness probe of a LOCAL endpoint's host:port — no HTTP, no deps.
    Confirms something is listening so 'auto' never selects a backend whose server isn't running.

    SSRF + TOCTOU containment: the host is resolved ONCE to a concrete IP; that same IP is both
    security-checked (must be local) AND connected to, so an attacker-controlled DNS name cannot
    resolve to 127.0.0.1 for the check and to a public host for the connect. Every failure mode
    (bad url, non-local target, resolution failure, refused/timed-out connect) is logged with its
    cause so it is visible which backend failed and why (observability lens). Retries once to
    absorb a momentary bind/accept blip."""
    try:
        u = urlparse(base_url)
        host = u.hostname or "127.0.0.1"
        port = u.port or (443 if u.scheme == "https" else 80)
    except (ValueError, TypeError, AttributeError) as exc:
        # These guard a non-string base_url — e.g. `ollama_base_url = 123` in config.toml,
        # which TOML types as an int; urlparse(123) raises AttributeError (a bytes/int mix),
        # and a bad :port raises ValueError. Any of them would otherwise crash the whole
        # startup; instead we treat it as an unprobeable/bad url (adversarial-input lens).
        log.warning("liveness probe skipped: invalid base_url %r (%s)", base_url, exc.__class__.__name__)
        return False
    ip = "127.0.0.1" if host in ("localhost", "") else _resolve_host_ip(host)
    if ip is None:
        log.warning("liveness probe skipped: host %r did not resolve within %ss", host, _DNS_TIMEOUT_S)
        return False
    if not _is_local_ip(ip):
        log.warning("refusing liveness probe of non-local host %r (resolved %s) — SSRF containment", host, ip)
        return False
    return _probe_tcp(ip, port, host, timeout)


def _probe_tcp(ip: str, port: int, host: str, timeout: float) -> bool:
    """Attempt a bounded TCP connect to an already-validated local IP, with one retry.
    Logs the concrete OSError (connection refused / timeout / DNS / transient blip) per
    attempt so a failed auto-detect says exactly WHICH backend was down and WHY, instead
    of silently swallowing the error (observability lens)."""
    for attempt in range(1, _PROBE_ATTEMPTS + 1):
        try:
            with socket.create_connection((ip, port), timeout=timeout):
                log.debug("liveness probe of %s:%d (%r) succeeded", ip, port, host)
                return True
        except OSError as exc:
            log.debug("liveness probe of %s:%d (%r) attempt %d/%d failed: %s",
                      ip, port, host, attempt, _PROBE_ATTEMPTS, exc)
            if attempt < _PROBE_ATTEMPTS:
                time.sleep(_backoff_delay(attempt))
    return False


def _backoff_delay(attempt: int) -> float:
    """Jittered exponential backoff before the next connect (network lens). Spacing the
    retries (rather than firing both immediately) lets a service that binds its port a few
    ms late recover into a later attempt; jitter avoids many callers retrying in lockstep.
    Deterministic non-random jitter (derived from a monotonic clock) keeps it dependency-
    free and test-stable while still de-synchronizing concurrent callers."""
    base = _PROBE_BACKOFF_S * (2 ** (attempt - 1))
    jitter = base * 0.25 * ((time.monotonic_ns() % 1000) / 1000.0)
    return base + jitter


def _auto_detect_verified(cfg: dict) -> tuple[str, bool]:
    """Resolve provider='auto' to (provider, verified) where ``verified`` is True only if
    the chosen backend answered a liveness probe.

    Preference order favors Claude inside a Claude Code session and always falls
    back to local Ollama. Probing is intentionally SERIAL and preference-ordered
    (first-reachable-wins): each probe is a sub-0.4s local TCP connect, so the whole
    walk is trivially cheap, and serial keeps the priority (a running higher-preference
    backend is always chosen over a lower one) that a parallel race would lose.
    Order rationale: claude-cli first (the subscription shim needs no API credits),
    then claude-haiku (metered cloud), then ollama (air-gapped local fallback).

    Chaos note: if NOTHING is reachable we still return 'ollama' with verified=False —
    not because it was verified up, but because it is the only provider that can run
    air-gapped with no metered credits, so it is the least-bad default. resolve() surfaces
    that False as an ``unverified`` flag on the spec so a caller can see the fleet was down
    rather than mistaking a dead endpoint for a healthy selection (chaos-engineering lens)."""
    order = (["claude-cli", "claude-haiku", "ollama"]
             if _is_claude_code_session() else ["ollama"])
    for prov in order:
        base = _openai_base_for(prov, cfg)
        if base and _reachable(base):
            log.debug("auto-detect selected %r (reachable at %s)", prov, base)
            return prov, True
    log.warning("auto-detect: none of %s reachable; falling back to UNVERIFIED 'ollama' "
                "(air-gapped default — start a backend if this is unexpected)", order)
    return "ollama", False


def _auto_detect(cfg: dict) -> str:
    """Back-compat wrapper: the first REACHABLE concrete backend as a bare string
    (see _auto_detect_verified for the full contract and rationale)."""
    return _auto_detect_verified(cfg)[0]


def _spec_for(provider: str, cfg: dict, unverified: bool = False) -> dict:
    """Build the uniform connection dict for one concrete provider from its table row.
    Output is identical across providers by construction, differing only in the row's
    values — the OpenAI-compatible (base_url, model, api_key_env) tuple plus the native
    flavor, so any component can pick the path it supports without hardcoding a model.

    The optional ``unverified`` key is ADDITIVE and only present (as True) on the chaos
    fallback path (auto-detect found nothing reachable). Explicit-provider specs never
    carry it, keeping resolve()'s pinned output byte-identical for the 182 dependents."""
    s = _PROVIDER_SPECS[provider]
    model = cfg[s["model_key"]]
    spec = {
        "provider": provider,
        "openai_compatible": True,
        "base_url": cfg[s["base_url_key"]],
        "model": model,
        "api_key_env": s["api_key_env"],
        "native": {"kind": s["native_kind"], "model": model},
        "air_gapped": s["air_gapped"],
    }
    if unverified:
        spec["unverified"] = True
    return spec


def _warn_if_api_key_missing(spec: dict) -> None:
    """Emit a WARNING when a non-air-gapped backend's api_key_env is unset (observability
    lens). resolve() otherwise returns 'resolved backend ...' looking healthy while the
    very first LLM call would 401 on the missing credential — this makes that misconfig
    diagnosable from logs BEFORE the call. Air-gapped ollama needs no key, so it is skipped."""
    if spec.get("air_gapped"):
        return
    env_name = spec["api_key_env"]
    if not os.environ.get(env_name):
        log.warning("backend %r selected but required API key env %s is unset; "
                    "LLM calls will fail to authenticate until it is provided",
                    spec["provider"], env_name)


def resolve(workspace: Path | None = None) -> dict:
    """Return a uniform connection spec all components can consume.

    Always exposes an OpenAI-compatible (base_url, model, api_key_env) tuple,
    plus the native flavor when relevant, so each component can pick the path
    it supports without any component hardcoding a model.

    An unknown provider raises ValueError listing the accepted set (derived from the
    spec table, so the message can never drift from what is actually supported).
    """
    cfg = _load_config(workspace)
    provider = cfg["provider"]
    unverified = False
    if provider == "auto":
        provider, verified = _auto_detect_verified(cfg)
        unverified = not verified  # chaos fallback: fleet was down, endpoint is unproven

    if provider not in _PROVIDER_SPECS:
        accepted = ", ".join(repr(p) for p in VALID_PROVIDERS)
        raise ValueError(
            f"Unknown backend provider {provider!r}. "
            f"Use one of {accepted} in config.toml [backend].provider."
        )
    spec = _spec_for(provider, cfg, unverified=unverified)
    _warn_if_api_key_missing(spec)
    log.debug("resolved backend provider=%s base_url=%s model=%s unverified=%s",
              provider, spec["base_url"], spec["model"], unverified)
    return spec


def _workspace_from_env() -> Path | None:
    """Resolve the diagnostic workspace from FORGE_WORKSPACE for the __main__ probe only.

    Path-traversal hardening (security lens): the env value is normalized with resolve()
    and must point at an EXISTING DIRECTORY, otherwise it is rejected (warned + ignored)
    rather than silently used to read a config.toml from an arbitrary location such as
    /etc. This is defense-in-depth only — resolve() still whitelists the provider and
    _is_local_host() still contains SSRF — but it fails closed on obviously hostile input."""
    raw = os.environ.get("FORGE_WORKSPACE")
    if not raw:
        return None
    try:
        candidate = Path(raw).expanduser().resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        log.warning("FORGE_WORKSPACE %r is not a valid path (%s); ignoring", raw, exc.__class__.__name__)
        return None
    if not candidate.is_dir():
        log.warning("FORGE_WORKSPACE %r is not an existing directory; ignoring", raw)
        return None
    return candidate


if __name__ == "__main__":
    import json
    # use FORGE_WORKSPACE so the diagnostic reads the foundry's config.toml (provider="auto"),
    # not a missing project-root one (which would wrongly default to ollama). The value is
    # validated (existing dir only) before use — see _workspace_from_env.
    print(json.dumps(resolve(_workspace_from_env()), indent=2))
