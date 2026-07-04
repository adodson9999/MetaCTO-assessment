#!/usr/bin/env python3
"""Unit tests for scripts/backend_config.py — the foundry's single LLM-backend resolver.

Covers the whole resolution WORKFLOW and its safety properties:
  * config layering: DEFAULTS -> config.toml [backend] -> FORGE_* env overrides;
  * resilience: a missing / unreadable / malformed TOML, or a non-table [backend], degrades to
    defaults+env instead of crashing;
  * every provider (ollama / claude-haiku / claude-cli) yields the exact uniform connection dict,
    'auto' picks the first reachable backend in preference order and falls back to ollama, and an
    unknown provider raises;
  * SSRF containment: liveness probes are confined to loopback/private hosts.

Run: agent-foundry/.venv/bin/python agent-foundry/tests/unit/scripts/test_backend_config.py
"""
from __future__ import annotations

import importlib
import os
import sys
import tempfile
from pathlib import Path

WS = Path(__file__).resolve().parents[3]          # agent-foundry
sys.path.insert(0, str(WS / "scripts"))
import backend_config as bc  # noqa: E402

importlib.reload(bc)

CLAUDE_CLI_EXPECTED = {
    "provider": "claude-cli", "openai_compatible": True,
    "base_url": "http://127.0.0.1:8787/v1", "model": "claude-haiku-4-5",
    "api_key_env": "FORGE_SHIM_KEY",
    "native": {"kind": "openai-cli", "model": "claude-haiku-4-5"}, "air_gapped": False,
}

# Full byte-for-byte pins for EVERY provider (not just claude-cli) so a silent drift in any
# row of _PROVIDER_SPECS / DEFAULTS — base_url, model, api_key_env, native.kind, air_gapped —
# is caught, since 182 dependents consume this exact dict (unit-test lens).
EXPECTED_SPECS = {
    "ollama": {
        "provider": "ollama", "openai_compatible": True,
        "base_url": "http://127.0.0.1:11434/v1", "model": "qwen2.5:14b-instruct",
        "api_key_env": "OLLAMA_API_KEY",
        "native": {"kind": "ollama", "model": "qwen2.5:14b-instruct"}, "air_gapped": True,
    },
    "claude-haiku": {
        "provider": "claude-haiku", "openai_compatible": True,
        "base_url": "http://127.0.0.1:4000/v1", "model": "claude-haiku-4-5",
        "api_key_env": "ANTHROPIC_API_KEY",
        "native": {"kind": "anthropic", "model": "claude-haiku-4-5"}, "air_gapped": False,
    },
    "claude-cli": CLAUDE_CLI_EXPECTED,
}


def _write_cfg(d: Path, body: str) -> Path:
    (d / "config.toml").write_text(body)
    return d


def _clear_env():
    for k in list(os.environ):
        if k.startswith("FORGE_"):
            del os.environ[k]


# ---- config layering -------------------------------------------------------
def test_defaults_when_no_config():
    _clear_env()
    with tempfile.TemporaryDirectory() as td:
        cfg = bc._load_config(Path(td))
        assert cfg["provider"] == "ollama"
        assert cfg["ollama_base_url"] == bc.DEFAULTS["ollama_base_url"]


def test_config_file_overrides_defaults():
    _clear_env()
    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), '[backend]\nprovider = "claude-cli"\n')
        assert bc._load_config(Path(td))["provider"] == "claude-cli"


def test_env_overrides_win():
    _clear_env()
    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), '[backend]\nprovider = "ollama"\n')
        os.environ["FORGE_PROVIDER"] = "claude-cli"
        try:
            assert bc._load_config(Path(td))["provider"] == "claude-cli"
        finally:
            _clear_env()


def test_env_overrides_every_config_key():
    # unit-test gap: the FORGE_* override loop must apply to EVERY key, not just provider.
    # Regression guard — e.g. if the loop keyed off a fixed subset, base_url/model/proxy would
    # silently ignore their env overrides.
    _clear_env()
    overrides = {
        "FORGE_OLLAMA_BASE_URL": "http://127.0.0.1:9999/v1",
        "FORGE_OLLAMA_MODEL": "llama3:70b",
        "FORGE_LITELLM_PROXY_URL": "http://127.0.0.1:4111/v1",
        "FORGE_CLAUDE_MODEL": "claude-opus-4-5",
        "FORGE_CLAUDE_CLI_SHIM_URL": "http://127.0.0.1:8811/v1",
    }
    for k, v in overrides.items():
        os.environ[k] = v
    try:
        with tempfile.TemporaryDirectory() as td:
            cfg = bc._load_config(Path(td))
        assert cfg["ollama_base_url"] == "http://127.0.0.1:9999/v1"
        assert cfg["ollama_model"] == "llama3:70b"
        assert cfg["litellm_proxy_url"] == "http://127.0.0.1:4111/v1"
        assert cfg["claude_model"] == "claude-opus-4-5"
        assert cfg["claude_cli_shim_url"] == "http://127.0.0.1:8811/v1"
    finally:
        _clear_env()


def test_partial_config_merges_over_defaults():
    # unit-test gap: a [backend] table that sets only SOME keys must MERGE — the specified
    # keys override while every unspecified key retains its DEFAULT (not wiped to missing).
    _clear_env()
    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td),
                   '[backend]\nprovider = "ollama"\nollama_model = "custom:8b"\n')
        cfg = bc._load_config(Path(td))
        assert cfg["ollama_model"] == "custom:8b"                       # overridden
        assert cfg["ollama_base_url"] == bc.DEFAULTS["ollama_base_url"]  # merged default kept
        assert cfg["litellm_proxy_url"] == bc.DEFAULTS["litellm_proxy_url"]
        assert cfg["claude_model"] == bc.DEFAULTS["claude_model"]
        # and the merged config still resolves to a byte-identical-shape spec
        assert bc.resolve(Path(td))["model"] == "custom:8b"


def test_config_ignored_when_tomllib_unavailable():
    # unit-test gap: on a runtime without tomllib (pre-3.11), _load_config must fall back to
    # DEFAULTS+env and NEVER attempt to parse the file — a present config.toml is simply skipped.
    _clear_env()
    orig = bc.tomllib
    bc.tomllib = None
    try:
        with tempfile.TemporaryDirectory() as td:
            _write_cfg(Path(td), '[backend]\nprovider = "claude-cli"\n')
            cfg = bc._load_config(Path(td))
            assert cfg["provider"] == "ollama"        # file ignored -> DEFAULTS win
            os.environ["FORGE_PROVIDER"] = "claude-haiku"
            try:
                assert bc._load_config(Path(td))["provider"] == "claude-haiku"  # env still applies
            finally:
                _clear_env()
    finally:
        bc.tomllib = orig


# ---- resilience ------------------------------------------------------------
def test_malformed_toml_degrades_not_crashes():
    _clear_env()
    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), '[backend]\nprovider = "ollama"\n  bad = [unclosed')
        cfg = bc._load_config(Path(td))          # must not raise
        assert cfg["provider"] == "ollama"        # falls back to defaults


def test_non_table_backend_key_ignored():
    _clear_env()
    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), 'backend = "not-a-table"\n')
        cfg = bc._load_config(Path(td))
        assert cfg["provider"] == "ollama"


# ---- SSRF containment ------------------------------------------------------
def test_is_local_host():
    assert bc._is_local_host("127.0.0.1")
    assert bc._is_local_host("localhost")
    assert bc._is_local_host("10.0.0.5")          # RFC-1918 private
    assert not bc._is_local_host("8.8.8.8")       # public


def test_reachable_refuses_non_local():
    assert bc._reachable("http://8.8.8.8:80") is False       # SSRF guard, no connection attempted


def test_reachable_false_when_nothing_listening():
    assert bc._reachable("http://127.0.0.1:1") is False       # local but (almost surely) closed


def test_is_local_ip_literals():
    assert bc._is_local_ip("127.0.0.1")
    assert bc._is_local_ip("10.0.0.5")
    assert bc._is_local_ip("169.254.1.1")     # link-local
    assert not bc._is_local_ip("8.8.8.8")
    assert not bc._is_local_ip("not-an-ip")   # bad input -> False, never raises


def test_resolve_host_ip_literal_bypasses_dns():
    # A numeric literal must round-trip WITHOUT touching the resolver (fast path).
    orig = bc.socket.getaddrinfo
    bc.socket.getaddrinfo = lambda *a, **k: (_ for _ in ()).throw(AssertionError("DNS used for literal"))
    try:
        assert bc._resolve_host_ip("127.0.0.1") == "127.0.0.1"
        assert bc._resolve_host_ip("10.1.2.3") == "10.1.2.3"
    finally:
        bc.socket.getaddrinfo = orig


def test_resolve_host_ip_returns_none_on_failure():
    orig = bc.socket.getaddrinfo
    bc.socket.getaddrinfo = lambda *a, **k: (_ for _ in ()).throw(OSError("resolver down"))
    try:
        assert bc._resolve_host_ip("slow.example.invalid") is None   # degrades, never raises
    finally:
        bc.socket.getaddrinfo = orig


def test_resolve_host_ip_never_touches_global_timeout():
    # Concurrency lens: the bounded lookup must NOT mutate the process-global socket
    # default timeout at all (it resolves in a worker thread), so it can never race with
    # or leak onto other sockets in the process.
    before = bc.socket.getdefaulttimeout()
    orig = bc.socket.getaddrinfo
    bc.socket.getaddrinfo = lambda *a, **k: (_ for _ in ()).throw(OSError("timed out"))
    try:
        bc._resolve_host_ip("slow.example.invalid")
    finally:
        bc.socket.getaddrinfo = orig
    assert bc.socket.getdefaulttimeout() == before


def test_resolve_host_ip_no_setdefaulttimeout_call():
    # Prove no global-timeout mutation: if setdefaulttimeout were called, this fails.
    calls = []
    orig_set = bc.socket.setdefaulttimeout
    orig_gai = bc.socket.getaddrinfo
    bc.socket.setdefaulttimeout = lambda v: calls.append(v)
    bc.socket.getaddrinfo = lambda *a, **k: [(2, 1, 6, "", ("10.0.0.9", 0))]
    try:
        assert bc._resolve_host_ip("host.example.internal") == "10.0.0.9"
        assert calls == [], "must not mutate global socket timeout"
    finally:
        bc.socket.setdefaulttimeout = orig_set
        bc.socket.getaddrinfo = orig_gai


def test_resolve_host_ip_times_out_on_hung_resolver():
    # A hung resolver must not stall past the DNS bound: worker thread is abandoned, None returned.
    import time as _t
    orig = bc.socket.getaddrinfo
    bc.socket.getaddrinfo = lambda *a, **k: _t.sleep(5) or [(2, 1, 6, "", ("127.0.0.1", 0))]
    old_bound = bc._DNS_TIMEOUT_S
    bc._DNS_TIMEOUT_S = 0.05
    start = _t.monotonic()
    try:
        assert bc._resolve_host_ip("hangs.example.invalid") is None
        assert _t.monotonic() - start < 1.0, "must return well before the hung resolver finishes"
    finally:
        bc.socket.getaddrinfo = orig
        bc._DNS_TIMEOUT_S = old_bound


def test_resolve_host_ip_non_string_returns_none():
    assert bc._resolve_host_ip(123) is None       # non-string (e.g. TOML int) -> None, no crash
    assert bc._resolve_host_ip(None) is None


def test_reachable_success_on_listening_socket():
    # Positive TCP path: a real listening socket on loopback must probe True.
    import socket as _s
    srv = _s.socket(_s.AF_INET, _s.SOCK_STREAM)
    srv.bind(("127.0.0.1", 0))
    srv.listen(1)
    port = srv.getsockname()[1]
    try:
        assert bc._reachable(f"http://127.0.0.1:{port}") is True
    finally:
        srv.close()


def test_reachable_toctou_uses_checked_ip():
    # SSRF/TOCTOU: even if resolution yields a PUBLIC ip, _reachable must refuse and
    # never call create_connection — the checked ip is the one that would be dialed.
    orig_resolve, orig_conn = bc._resolve_host_ip, bc.socket.create_connection
    bc._resolve_host_ip = lambda host: "8.8.8.8"
    bc.socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(AssertionError("connected to non-local"))
    try:
        assert bc._reachable("http://evil.example.com:80") is False
    finally:
        bc._resolve_host_ip, bc.socket.create_connection = orig_resolve, orig_conn


def test_reachable_unresolvable_host_refused():
    orig = bc._resolve_host_ip
    bc._resolve_host_ip = lambda host: None
    try:
        assert bc._reachable("http://never.resolves.invalid:80") is False
    finally:
        bc._resolve_host_ip = orig


# ---- provider specs / resolve ---------------------------------------------
def test_resolve_each_provider_shape():
    # Pin EVERY provider's full output dict (byte-for-byte), not just claude-cli — a drift in
    # any spec row for ollama or claude-haiku must fail here, not silently reach a dependent.
    _clear_env()
    for prov, expected in EXPECTED_SPECS.items():
        with tempfile.TemporaryDirectory() as td:
            _write_cfg(Path(td), f'[backend]\nprovider = "{prov}"\n')
            r = bc.resolve(Path(td))
            assert r == expected, f"{prov}: {r} != {expected}"
            assert list(r.keys()) == list(expected.keys()), "key order/set drift"


def test_spec_for_matches_expected_for_every_provider():
    # Direct unit test of the _spec_for helper (the builder resolve() delegates to), so its
    # per-row mapping is validated independently of the config-layering path.
    for prov, expected in EXPECTED_SPECS.items():
        assert bc._spec_for(prov, dict(bc.DEFAULTS)) == expected


def test_spec_for_unverified_adds_only_that_key():
    # The additive unverified flag must leave the pinned keys untouched and add exactly one key.
    base = bc._spec_for("ollama", dict(bc.DEFAULTS))
    flagged = bc._spec_for("ollama", dict(bc.DEFAULTS), unverified=True)
    assert flagged == {**base, "unverified": True}
    assert set(flagged) - set(base) == {"unverified"}


def test_openai_base_for_every_provider():
    # Direct helper test: the probed endpoint for each provider maps to the right cfg key,
    # and an unknown provider yields None (used by _auto_detect to skip it).
    cfg = dict(bc.DEFAULTS)
    assert bc._openai_base_for("ollama", cfg) == cfg["ollama_base_url"]
    assert bc._openai_base_for("claude-haiku", cfg) == cfg["litellm_proxy_url"]
    assert bc._openai_base_for("claude-cli", cfg) == cfg["claude_cli_shim_url"]
    assert bc._openai_base_for("nope", cfg) is None


def test_is_local_host_resolves_hostname_via_ip():
    # _is_local_host must honor the resolved IP (not just literals): a name that resolves to a
    # private ip is local; one that resolves public is not; unresolvable is not.
    orig = bc._resolve_host_ip
    try:
        bc._resolve_host_ip = lambda h: "10.1.2.3"
        assert bc._is_local_host("intranet.example") is True
        bc._resolve_host_ip = lambda h: "93.184.216.34"
        assert bc._is_local_host("public.example") is False
        bc._resolve_host_ip = lambda h: None
        assert bc._is_local_host("nx.example") is False
    finally:
        bc._resolve_host_ip = orig


def test_resolve_unknown_provider_raises():
    _clear_env()
    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), '[backend]\nprovider = "does-not-exist"\n')
        try:
            bc.resolve(Path(td))
            assert False, "expected ValueError for unknown provider"
        except ValueError:
            pass


def test_auto_detect_prefers_first_reachable(monkeypatch=None):
    _clear_env()
    cfg = dict(bc.DEFAULTS)
    orig_reach, orig_sess = bc._reachable, bc._is_claude_code_session
    try:
        bc._is_claude_code_session = lambda: True
        bc._reachable = lambda base, timeout=bc._PROBE_TIMEOUT_S: "8787" in base   # only claude-cli shim up
        assert bc._auto_detect(cfg) == "claude-cli"
        bc._reachable = lambda base, timeout=bc._PROBE_TIMEOUT_S: False              # nothing up
        assert bc._auto_detect(cfg) == "ollama"                                      # documented fallback
    finally:
        bc._reachable, bc._is_claude_code_session = orig_reach, orig_sess


def test_valid_providers_derived_from_specs():
    # VALID_PROVIDERS must stay in lockstep with the spec table (no drift) plus 'auto'.
    assert set(bc.VALID_PROVIDERS) == set(bc._PROVIDER_SPECS) | {"auto"}
    for prov in bc._PROVIDER_SPECS:
        assert prov in bc.VALID_PROVIDERS


def test_unknown_provider_error_lists_valid_set():
    _clear_env()
    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), '[backend]\nprovider = "nope"\n')
        try:
            bc.resolve(Path(td))
            assert False, "expected ValueError"
        except ValueError as e:
            for prov in bc.VALID_PROVIDERS:
                assert repr(prov) in str(e)     # message derived from the real set


def test_auto_detect_air_gapped_default_when_all_down():
    _clear_env()
    cfg = dict(bc.DEFAULTS)
    orig_reach, orig_sess = bc._reachable, bc._is_claude_code_session
    try:
        bc._is_claude_code_session = lambda: False
        bc._reachable = lambda base, timeout=bc._PROBE_TIMEOUT_S: False
        assert bc._auto_detect(cfg) == "ollama"     # unverified air-gapped fallback
    finally:
        bc._reachable, bc._is_claude_code_session = orig_reach, orig_sess


def test_workspace_from_env_none_when_unset():
    old = os.environ.pop("FORGE_WORKSPACE", None)
    try:
        assert bc._workspace_from_env() is None
    finally:
        if old is not None:
            os.environ["FORGE_WORKSPACE"] = old


def test_workspace_from_env_rejects_nonexistent():
    old = os.environ.get("FORGE_WORKSPACE")
    os.environ["FORGE_WORKSPACE"] = "/no/such/dir/anywhere/xyzzy"
    try:
        assert bc._workspace_from_env() is None      # path-traversal hardening: fail closed
    finally:
        if old is None:
            os.environ.pop("FORGE_WORKSPACE", None)
        else:
            os.environ["FORGE_WORKSPACE"] = old


def test_workspace_from_env_accepts_existing_dir():
    old = os.environ.get("FORGE_WORKSPACE")
    with tempfile.TemporaryDirectory() as td:
        os.environ["FORGE_WORKSPACE"] = td
        try:
            got = bc._workspace_from_env()
            assert got is not None and got == Path(td).resolve()
        finally:
            if old is None:
                os.environ.pop("FORGE_WORKSPACE", None)
            else:
                os.environ["FORGE_WORKSPACE"] = old


def test_reachable_unparseable_url_refused():
    # A malformed url must be refused, logged, and never crash.
    assert bc._reachable("http://[::1:bad:port]") is False


def test_reachable_non_string_base_url_no_crash():
    # adversarial-input: a non-string base_url (e.g. `ollama_base_url = 123` in config.toml)
    # must be rejected, not crash with TypeError from urlparse.
    assert bc._reachable(123) is False
    assert bc._reachable(None) is False


def test_backoff_delay_bounded_and_grows():
    # network lens: retry backoff is positive, jittered, and grows with the attempt number.
    d1 = bc._backoff_delay(1)
    d2 = bc._backoff_delay(2)
    assert 0 < d1 <= bc._PROBE_BACKOFF_S * 1.25
    assert d2 >= bc._PROBE_BACKOFF_S * 2      # exponential floor for attempt 2
    assert d2 <= bc._PROBE_BACKOFF_S * 2 * 1.25


def test_probe_tcp_sleeps_between_retries():
    # A failing probe must back off before its retry, not fire both connects instantly.
    slept = []
    orig_sleep, orig_conn = bc.time.sleep, bc.socket.create_connection
    bc.time.sleep = lambda s: slept.append(s)
    bc.socket.create_connection = lambda *a, **k: (_ for _ in ()).throw(OSError("refused"))
    try:
        assert bc._probe_tcp("127.0.0.1", 9, "127.0.0.1", 0.01) is False
        assert len(slept) == bc._PROBE_ATTEMPTS - 1   # one sleep between the two attempts
        assert all(s > 0 for s in slept)
    finally:
        bc.time.sleep, bc.socket.create_connection = orig_sleep, orig_conn


def test_auto_detect_verified_true_when_reachable():
    _clear_env()
    cfg = dict(bc.DEFAULTS)
    orig_reach, orig_sess = bc._reachable, bc._is_claude_code_session
    try:
        bc._is_claude_code_session = lambda: True
        bc._reachable = lambda base, timeout=bc._PROBE_TIMEOUT_S: "8787" in base
        assert bc._auto_detect_verified(cfg) == ("claude-cli", True)
        bc._reachable = lambda base, timeout=bc._PROBE_TIMEOUT_S: False
        assert bc._auto_detect_verified(cfg) == ("ollama", False)   # chaos: unverified fallback
    finally:
        bc._reachable, bc._is_claude_code_session = orig_reach, orig_sess


def test_auto_detect_respects_preference_order():
    # unit-test lens: if MULTIPLE backends are up, the HIGHER-preference one wins — a test
    # that only mocks one-up cannot catch an order regression, so mock two-up here.
    _clear_env()
    cfg = dict(bc.DEFAULTS)
    orig_reach, orig_sess = bc._reachable, bc._is_claude_code_session
    try:
        bc._is_claude_code_session = lambda: True
        # both claude-cli (8787) and claude-haiku (4000) up; claude-cli must win by order.
        bc._reachable = lambda base, timeout=bc._PROBE_TIMEOUT_S: ("8787" in base or "4000" in base)
        assert bc._auto_detect(cfg) == "claude-cli"
        # now only claude-haiku up -> it wins over the (down) claude-cli and (down) ollama.
        bc._reachable = lambda base, timeout=bc._PROBE_TIMEOUT_S: "4000" in base
        assert bc._auto_detect(cfg) == "claude-haiku"
    finally:
        bc._reachable, bc._is_claude_code_session = orig_reach, orig_sess


def test_resolve_auto_fallback_tags_unverified():
    # chaos-engineering: provider='auto' with nothing reachable must return a spec flagged
    # unverified=True so callers can tell a dead-endpoint guess from a healthy pick.
    _clear_env()
    orig_reach, orig_sess = bc._reachable, bc._is_claude_code_session
    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), '[backend]\nprovider = "auto"\n')
        try:
            bc._is_claude_code_session = lambda: False
            bc._reachable = lambda base, timeout=bc._PROBE_TIMEOUT_S: False
            spec = bc.resolve(Path(td))
            assert spec["provider"] == "ollama"
            assert spec.get("unverified") is True
        finally:
            bc._reachable, bc._is_claude_code_session = orig_reach, orig_sess


def test_resolve_explicit_provider_has_no_unverified_key():
    # The pinned contract: an explicit provider spec must NEVER carry the unverified key.
    _clear_env()
    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), '[backend]\nprovider = "ollama"\n')
        assert "unverified" not in bc.resolve(Path(td))


def test_warn_if_api_key_missing_fires_for_cloud(capfd=None):
    # observability: a non-air-gapped backend with an unset api_key_env must WARN.
    import logging as _l
    records = []
    h = _l.Handler(); h.emit = lambda r: records.append(r.getMessage())
    bc.log.addHandler(h); bc.log.setLevel(_l.WARNING)
    old = os.environ.pop("ANTHROPIC_API_KEY", None)
    try:
        bc._warn_if_api_key_missing({"provider": "claude-haiku", "api_key_env": "ANTHROPIC_API_KEY", "air_gapped": False})
        assert any("ANTHROPIC_API_KEY" in m for m in records), records
        records.clear()
        # air-gapped ollama needs no key -> no warning
        bc._warn_if_api_key_missing({"provider": "ollama", "api_key_env": "OLLAMA_API_KEY", "air_gapped": True})
        assert records == []
    finally:
        bc.log.removeHandler(h)
        if old is not None:
            os.environ["ANTHROPIC_API_KEY"] = old


def test_warn_if_api_key_present_is_silent():
    import logging as _l
    records = []
    h = _l.Handler(); h.emit = lambda r: records.append(r.getMessage())
    bc.log.addHandler(h); bc.log.setLevel(_l.WARNING)
    old = os.environ.get("ANTHROPIC_API_KEY")
    os.environ["ANTHROPIC_API_KEY"] = "sk-present"
    try:
        bc._warn_if_api_key_missing({"provider": "claude-haiku", "api_key_env": "ANTHROPIC_API_KEY", "air_gapped": False})
        assert records == []
    finally:
        bc.log.removeHandler(h)
        if old is None:
            os.environ.pop("ANTHROPIC_API_KEY", None)
        else:
            os.environ["ANTHROPIC_API_KEY"] = old


class _CaptureLogs:
    """Context manager capturing this module's WARNING+ log messages, restoring state on exit
    so tests stay isolated (no leaked handler / level). DRY helper for the observability tests."""
    def __init__(self):
        self.records: list[str] = []
        import logging as _l
        self._l = _l
        self._h = _l.Handler()
        self._h.emit = lambda r: self.records.append(r.getMessage())

    def __enter__(self):
        self._prev_level = bc.log.level
        bc.log.addHandler(self._h)
        bc.log.setLevel(self._l.WARNING)
        return self

    def __exit__(self, *exc):
        bc.log.removeHandler(self._h)
        bc.log.setLevel(self._prev_level)
        return False


def _with_env(name: str, value: str | None):
    """Set/clear one env var and return a restore callable (keeps the api-key tests tidy)."""
    old = os.environ.get(name)
    if value is None:
        os.environ.pop(name, None)
    else:
        os.environ[name] = value

    def restore():
        if old is None:
            os.environ.pop(name, None)
        else:
            os.environ[name] = old
    return restore


def test_warn_if_api_key_missing_every_cloud_provider():
    # unit-test lens (named gap): EACH non-air-gapped provider — including claude-cli /
    # FORGE_SHIM_KEY, previously untested — must WARN naming its own key env when unset.
    cases = {"claude-cli": "FORGE_SHIM_KEY", "claude-haiku": "ANTHROPIC_API_KEY"}
    for prov, env_name in cases.items():
        restore = _with_env(env_name, None)
        try:
            with _CaptureLogs() as cap:
                bc._warn_if_api_key_missing(bc._spec_for(prov, dict(bc.DEFAULTS)))
            msgs = " ".join(cap.records)
            assert env_name in msgs and prov in msgs, f"{prov}: {cap.records}"
        finally:
            restore()


def test_warn_if_api_key_present_silent_every_cloud_provider():
    cases = {"claude-cli": "FORGE_SHIM_KEY", "claude-haiku": "ANTHROPIC_API_KEY"}
    for prov, env_name in cases.items():
        restore = _with_env(env_name, "sk-present-value")
        try:
            with _CaptureLogs() as cap:
                bc._warn_if_api_key_missing(bc._spec_for(prov, dict(bc.DEFAULTS)))
            assert cap.records == [], f"{prov} should be silent when key set: {cap.records}"
        finally:
            restore()


def test_warn_if_api_key_missing_skips_air_gapped_ollama():
    # ollama is air-gapped and needs no key even when OLLAMA_API_KEY is unset -> no warning.
    restore = _with_env("OLLAMA_API_KEY", None)
    try:
        with _CaptureLogs() as cap:
            bc._warn_if_api_key_missing(bc._spec_for("ollama", dict(bc.DEFAULTS)))
        assert cap.records == [], cap.records
    finally:
        restore()


def test_resolve_claude_cli_warns_on_missing_shim_key():
    # Through the public entrypoint: resolving claude-cli with FORGE_SHIM_KEY unset must warn,
    # and MUST still return the byte-identical pinned spec (the warning is side-channel only).
    _clear_env()
    restore = _with_env("FORGE_SHIM_KEY", None)
    with tempfile.TemporaryDirectory() as td:
        _write_cfg(Path(td), '[backend]\nprovider = "claude-cli"\n')
        try:
            with _CaptureLogs() as cap:
                spec = bc.resolve(Path(td))
            assert spec == CLAUDE_CLI_EXPECTED, spec
            assert any("FORGE_SHIM_KEY" in m for m in cap.records), cap.records
        finally:
            restore()


def test_reload_does_not_stack_null_handlers():
    # memory-resource: reloading the module must not accumulate NullHandlers on the logger.
    n_before = sum(isinstance(h, importlib.import_module("logging").NullHandler) for h in bc.log.handlers)
    importlib.reload(bc)
    import logging as _l
    n_after = sum(isinstance(h, _l.NullHandler) for h in bc.log.handlers)
    assert n_after <= 1, f"expected at most one NullHandler, got {n_after}"
    assert n_after >= 1, "must still have exactly one NullHandler after reload"


def main() -> int:
    tests = [v for k, v in sorted(globals().items()) if k.startswith("test_")]
    failed = 0
    for t in tests:
        try:
            t(); print(f"PASS  {t.__name__}")
        except AssertionError as e:
            failed += 1; print(f"FAIL  {t.__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
