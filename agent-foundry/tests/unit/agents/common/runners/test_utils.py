#!/usr/bin/env python3
"""Unit tests for agents/common/runners/utils.py — the shared runner helpers.

Covers the whole prompt-resolution WORKFLOW and both public helpers' safety
properties:

  * load_system_prompt priority chain (FORGE_SKILL_DOC -> primary_fn -> subagent_md),
    YAML front-matter stripping (populated / empty / no-trailing-newline), and every
    degradation path (missing file, oversize file, non-UTF-8 bytes, path traversal,
    symlink escape, TOCTOU-unreadable env doc, raising/empty primary_fn);
  * resolve_backend return shape, sys.path single-insert idempotency across repeated
    calls, and thread-safety under concurrent invocation.

Run: agent-foundry/.venv/bin/python agent-foundry/tests/unit/agents/common/runners/test_utils.py
"""
from __future__ import annotations

import logging
import os
import sys
import tempfile
import threading
import time
from pathlib import Path

WS = Path(__file__).resolve().parents[5]  # agent-foundry
sys.path.insert(0, str(WS / "agents" / "common"))
sys.path.insert(0, str(WS / "scripts"))

from runners import utils  # noqa: E402
from runners.utils import load_system_prompt, resolve_backend  # noqa: E402

# A subagent md path that lives under the foundry's agents/ tree, so utils'
# workspace containment resolves to the real foundry root (WS).
SUBAGENT_ANCHOR = WS / "agents" / "general" / "bug-reporter" / "subagent" / "anchor.md"


def _clear_skill_doc():
    os.environ.pop("FORGE_SKILL_DOC", None)


# --- load_system_prompt: source priority ------------------------------------
def test_env_override_takes_priority():
    _clear_skill_doc()
    with tempfile.NamedTemporaryFile("w", suffix=".md", dir=str(WS), delete=False, encoding="utf-8") as f:
        f.write("ENV PROMPT")
        doc = f.name
    try:
        os.environ["FORGE_SKILL_DOC"] = doc
        # primary_fn present but env-var must win.
        assert load_system_prompt(SUBAGENT_ANCHOR, lambda: "PRIMARY") == "ENV PROMPT"
    finally:
        _clear_skill_doc()
        os.unlink(doc)


def test_primary_fn_used_when_env_absent():
    _clear_skill_doc()
    assert load_system_prompt(SUBAGENT_ANCHOR, lambda: "PRIMARY PROMPT") == "PRIMARY PROMPT"


def test_direct_subagent_read_when_no_env_no_primary():
    _clear_skill_doc()
    with tempfile.NamedTemporaryFile("w", suffix=".md", dir=str(WS), delete=False, encoding="utf-8") as f:
        f.write("BODY ONLY")
        md = f.name
    try:
        assert load_system_prompt(Path(md), None) == "BODY ONLY"
    finally:
        os.unlink(md)


# --- load_system_prompt: YAML front-matter stripping ------------------------
def _write_md(body: str) -> str:
    fd, path = tempfile.mkstemp(suffix=".md", dir=str(WS))
    with os.fdopen(fd, "w", encoding="utf-8") as f:
        f.write(body)
    return path


def test_frontmatter_populated_stripped():
    _clear_skill_doc()
    md = _write_md("---\nname: x\nmodel: y\n---\nHELLO BODY")
    try:
        assert load_system_prompt(Path(md)) == "HELLO BODY"
    finally:
        os.unlink(md)


def test_frontmatter_empty_stripped():
    _clear_skill_doc()
    md = _write_md("---\n---\nEMPTY FM BODY")
    try:
        assert load_system_prompt(Path(md)) == "EMPTY FM BODY"
    finally:
        os.unlink(md)


def test_frontmatter_no_trailing_newline_stripped():
    _clear_skill_doc()
    # Closing --- has NO trailing newline and no body after it.
    md = _write_md("---\nkey: value\n---")
    try:
        assert load_system_prompt(Path(md)) == ""
    finally:
        os.unlink(md)


def test_no_frontmatter_left_intact():
    _clear_skill_doc()
    md = _write_md("plain body no front matter")
    try:
        assert load_system_prompt(Path(md)) == "plain body no front matter"
    finally:
        os.unlink(md)


# --- load_system_prompt: failure / degradation paths ------------------------
def test_missing_subagent_file_raises():
    _clear_skill_doc()
    missing = WS / "does-not-exist-xyz.md"
    try:
        load_system_prompt(missing, None)
        assert False, "expected OSError for missing terminal file"
    except OSError:
        pass


def test_oversize_env_doc_falls_back_to_primary():
    _clear_skill_doc()
    big = _write_md("x" * (utils._MAX_PROMPT_BYTES + 10))
    try:
        os.environ["FORGE_SKILL_DOC"] = big
        # Oversize env doc must be refused and degrade to primary_fn, not read.
        assert load_system_prompt(SUBAGENT_ANCHOR, lambda: "FALLBACK") == "FALLBACK"
    finally:
        _clear_skill_doc()
        os.unlink(big)


def test_non_utf8_env_doc_falls_back():
    _clear_skill_doc()
    fd, path = tempfile.mkstemp(suffix=".md", dir=str(WS))
    with os.fdopen(fd, "wb") as f:
        f.write(b"\xff\xfe invalid utf8 \x80")
    try:
        os.environ["FORGE_SKILL_DOC"] = path
        assert load_system_prompt(SUBAGENT_ANCHOR, lambda: "SAFE FALLBACK") == "SAFE FALLBACK"
    finally:
        _clear_skill_doc()
        os.unlink(path)


def test_traversal_env_doc_rejected():
    _clear_skill_doc()
    # Classic traversal to a file outside the workspace must be ignored -> primary_fn.
    os.environ["FORGE_SKILL_DOC"] = "/etc/passwd"
    try:
        assert load_system_prompt(SUBAGENT_ANCHOR, lambda: "REJECTED") == "REJECTED"
    finally:
        _clear_skill_doc()


def test_symlink_escape_env_doc_rejected():
    _clear_skill_doc()
    link = WS / "utils_test_symlink.md"
    if link.exists() or link.is_symlink():
        link.unlink()
    link.symlink_to("/etc/hosts")  # symlink inside WS pointing outside
    try:
        os.environ["FORGE_SKILL_DOC"] = str(link)
        assert load_system_prompt(SUBAGENT_ANCHOR, lambda: "NO ESCAPE") == "NO ESCAPE"
    finally:
        _clear_skill_doc()
        link.unlink()


def test_nonexistent_env_doc_falls_back():
    _clear_skill_doc()
    os.environ["FORGE_SKILL_DOC"] = str(WS / "no-such-skill-doc.md")
    try:
        assert load_system_prompt(SUBAGENT_ANCHOR, lambda: "FELL BACK") == "FELL BACK"
    finally:
        _clear_skill_doc()


def test_raising_primary_fn_degrades_to_file():
    _clear_skill_doc()
    md = _write_md("FILE AFTER RAISE")

    def boom() -> str:
        raise RuntimeError("primary exploded")

    try:
        assert load_system_prompt(Path(md), boom) == "FILE AFTER RAISE"
    finally:
        os.unlink(md)


def test_empty_primary_fn_degrades_to_file():
    _clear_skill_doc()
    md = _write_md("FILE AFTER EMPTY")
    try:
        assert load_system_prompt(Path(md), lambda: "   ") == "FILE AFTER EMPTY"
    finally:
        os.unlink(md)


# --- resolve_backend: shape + sys.path hygiene + concurrency ----------------
_EXPECTED_KEYS = {
    "provider", "openai_compatible", "base_url", "model", "api_key_env", "native", "air_gapped",
}


def test_resolve_backend_returns_expected_shape():
    spec = resolve_backend(WS)
    # Exact key set — no extra, no missing (catches a drifted return contract).
    assert set(spec.keys()) == _EXPECTED_KEYS, set(spec.keys()) ^ _EXPECTED_KEYS
    # Per-key types, so a reviewer knows the shape is asserted, not just the names.
    assert isinstance(spec["provider"], str) and spec["provider"]
    assert isinstance(spec["openai_compatible"], bool)
    assert isinstance(spec["base_url"], str) and spec["base_url"].startswith("http")
    assert isinstance(spec["model"], str) and spec["model"]
    assert isinstance(spec["api_key_env"], str)
    assert isinstance(spec["air_gapped"], bool)
    assert isinstance(spec["native"], dict)
    assert isinstance(spec["native"].get("model"), str)
    # native model must agree with the top-level model (backend_config invariant).
    assert spec["native"]["model"] == spec["model"]


def test_resolve_backend_no_duplicate_sys_path():
    scripts_dir = str((WS / "scripts").resolve(strict=False))
    for _ in range(5):
        resolve_backend(WS)
    assert sys.path.count(scripts_dir) == 1  # single insert, no unbounded growth


def test_resolve_backend_thread_safe():
    scripts_dir = str((WS / "scripts").resolve(strict=False))
    errors: list[BaseException] = []
    results: list[dict] = []

    def worker() -> None:
        try:
            results.append(resolve_backend(WS))
        except BaseException as exc:  # noqa: BLE001 - record any race failure
            errors.append(exc)

    threads = [threading.Thread(target=worker) for _ in range(16)]
    for t in threads:
        t.start()
    for t in threads:
        t.join()

    assert not errors, f"concurrent resolve_backend raised: {errors}"
    assert len(results) == 16
    assert sys.path.count(scripts_dir) == 1  # no duplicates even under contention


# --- round-2: blank env doc, BOM, primary_fn hang, sys.path cap -------------
def test_blank_env_doc_falls_back_to_primary():
    _clear_skill_doc()
    blank = _write_md("   \n\t  \n")  # whitespace only
    try:
        os.environ["FORGE_SKILL_DOC"] = blank
        # Must NOT return "" from the env tier — fall through to primary_fn.
        assert load_system_prompt(SUBAGENT_ANCHOR, lambda: "REAL PROMPT") == "REAL PROMPT"
    finally:
        _clear_skill_doc()
        os.unlink(blank)


def test_blank_env_doc_falls_all_the_way_to_file():
    _clear_skill_doc()
    blank = _write_md("")  # truly empty
    md = _write_md("FILE WINS")
    try:
        os.environ["FORGE_SKILL_DOC"] = blank
        assert load_system_prompt(Path(md), None) == "FILE WINS"
    finally:
        _clear_skill_doc()
        os.unlink(blank)
        os.unlink(md)


def test_utf8_bom_frontmatter_stripped():
    _clear_skill_doc()
    fd, path = tempfile.mkstemp(suffix=".md", dir=str(WS))
    # BOM + populated front-matter + body; BOM must not defeat the ^--- regex.
    with os.fdopen(fd, "wb") as f:
        f.write("﻿---\nname: x\n---\nBOM BODY".encode("utf-8"))
    try:
        assert load_system_prompt(Path(path), None) == "BOM BODY"
    finally:
        os.unlink(path)


def test_utf8_bom_plain_body_stripped():
    _clear_skill_doc()
    fd, path = tempfile.mkstemp(suffix=".md", dir=str(WS))
    with os.fdopen(fd, "wb") as f:
        f.write("﻿plain body".encode("utf-8"))  # BOM, no front-matter
    try:
        # BOM must be gone — result is the clean body, no leading U+FEFF.
        result = load_system_prompt(Path(path), None)
        assert result == "plain body"
        assert not result.startswith("﻿")
    finally:
        os.unlink(path)


def test_hanging_primary_fn_times_out_and_falls_back():
    _clear_skill_doc()
    md = _write_md("FILE AFTER HANG")

    def hang() -> str:
        time.sleep(30)  # would wedge startup without the timeout guard
        return "NEVER"

    try:
        os.environ["FORGE_PRIMARY_FN_TIMEOUT_S"] = "0.2"  # keep the test fast
        start = time.monotonic()
        result = load_system_prompt(Path(md), hang)
        elapsed = time.monotonic() - start
        assert result == "FILE AFTER HANG"
        assert elapsed < 5, f"did not time out promptly (took {elapsed:.1f}s)"
    finally:
        os.environ.pop("FORGE_PRIMARY_FN_TIMEOUT_S", None)
        os.unlink(md)


def test_workspace_resolve_failure_degrades(monkeypatch=None):
    _clear_skill_doc()
    md = _write_md("FILE AFTER RESOLVE FAIL")
    orig = utils._workspace_for
    try:
        os.environ["FORGE_SKILL_DOC"] = str(WS / "anything.md")

        def boom(_p):
            raise OSError("simulated resolve/permission failure")

        utils._workspace_for = boom  # force the guarded path in _try_env_override
        assert load_system_prompt(Path(md), None) == "FILE AFTER RESOLVE FAIL"
    finally:
        utils._workspace_for = orig
        _clear_skill_doc()
        os.unlink(md)


def test_resolve_backend_sys_path_bounded_across_workspaces():
    # Many DISTINCT ws roots must not grow sys.path without bound. We drive far past
    # the cap and assert the tracked-dir set never exceeds _MAX_TRACKED_SCRIPT_DIRS.
    before = len(sys.path)
    for i in range(utils._MAX_TRACKED_SCRIPT_DIRS + 20):
        fake_ws = WS / "tests" / "_fake_ws" / f"ws{i}"
        try:
            resolve_backend(fake_ws)
        except Exception:  # noqa: BLE001 - backend_config import path is the shared one; ignore resolve errors
            pass
    assert len(utils._INSERTED_SCRIPT_DIRS) <= utils._MAX_TRACKED_SCRIPT_DIRS
    # sys.path grew by at most the cap, never one-per-call.
    assert len(sys.path) - before <= utils._MAX_TRACKED_SCRIPT_DIRS


# --- round-3: daemon worker, _call_with_timeout, resolve_backend timeout ----
def test_hung_primary_fn_worker_is_daemon_and_not_leaked():
    # The anti-hang worker MUST be a daemon so a stuck primary_fn can't block
    # interpreter exit (error-handling-resilience / memory-resource lens). We record
    # live threads before, run a call that times out on a still-blocked fn, and assert
    # the leftover worker is a daemon (won't join at exit) — no non-daemon leak.
    _clear_skill_doc()
    md = _write_md("FILE")
    release = threading.Event()

    def hang() -> str:
        release.wait(30)  # stays blocked past the timeout window
        return "NEVER"

    try:
        os.environ["FORGE_PRIMARY_FN_TIMEOUT_S"] = "0.2"
        assert load_system_prompt(Path(md), hang) == "FILE"
        leftover = [t for t in threading.enumerate() if t.name == "primary_fn" and t.is_alive()]
        assert leftover, "expected the timed-out worker to still be running"
        assert all(t.daemon for t in leftover), "timed-out worker must be a daemon thread"
    finally:
        release.set()  # let the worker finish so the test process stays tidy
        os.environ.pop("FORGE_PRIMARY_FN_TIMEOUT_S", None)
        os.unlink(md)


def test_call_with_timeout_returns_value():
    assert utils._call_with_timeout(lambda: 42, 1.0, "ok") == 42


def test_call_with_timeout_propagates_exception():
    def boom():
        raise KeyError("nope")

    try:
        utils._call_with_timeout(boom, 1.0, "boom")
        assert False, "expected the worker's exception to propagate"
    except KeyError:
        pass


def test_call_with_timeout_raises_timeout():
    start = time.monotonic()
    try:
        utils._call_with_timeout(lambda: time.sleep(30), 0.2, "slow")
        assert False, "expected TimeoutError"
    except TimeoutError:
        pass
    assert time.monotonic() - start < 5, "timeout did not fire promptly"


def test_timeout_from_env_validation():
    key = "FORGE_TEST_TIMEOUT_XYZ"
    os.environ.pop(key, None)
    try:
        assert utils._timeout_from_env(key, 7.0) == 7.0          # unset -> default
        os.environ[key] = "not-a-number"
        assert utils._timeout_from_env(key, 7.0) == 7.0          # garbage -> default
        os.environ[key] = "-3"
        assert utils._timeout_from_env(key, 7.0) == 7.0          # non-positive -> default
        os.environ[key] = "2.5"
        assert utils._timeout_from_env(key, 7.0) == 2.5          # valid override wins
    finally:
        os.environ.pop(key, None)


def test_resolve_backend_hang_times_out():
    # A hung backend_config.resolve() must not stall resolve_backend indefinitely;
    # the outer daemon-thread timeout surfaces a fast TimeoutError (chaos lens).
    utils._ensure_scripts_importable(WS)
    import backend_config
    real_resolve = backend_config.resolve
    try:
        os.environ["FORGE_BACKEND_TIMEOUT_S"] = "0.2"
        backend_config.resolve = lambda *_a, **_k: time.sleep(30)
        start = time.monotonic()
        try:
            resolve_backend(WS)
            assert False, "expected TimeoutError from a hung resolve()"
        except TimeoutError:
            pass
        assert time.monotonic() - start < 5, "resolve_backend did not time out promptly"
    finally:
        backend_config.resolve = real_resolve
        os.environ.pop("FORGE_BACKEND_TIMEOUT_S", None)


# --- round-4: non-string primary_fn, worker cap, backend retry --------------
def test_primary_fn_returning_non_string_degrades_to_file():
    # primary_fn must return str; a non-string (e.g. dict) is not a usable prompt and
    # must fall through to the file tier, not be returned as-is (error-handling lens).
    _clear_skill_doc()
    md = _write_md("FILE AFTER NONSTRING")
    try:
        assert load_system_prompt(Path(md), lambda: {"not": "a string"}) == "FILE AFTER NONSTRING"
        assert load_system_prompt(Path(md), lambda: 123) == "FILE AFTER NONSTRING"
        assert load_system_prompt(Path(md), lambda: None) == "FILE AFTER NONSTRING"
    finally:
        os.unlink(md)


def test_worker_semaphore_caps_inflight_threads():
    # Saturating the worker permits must make the next _call_with_timeout raise a
    # fast TimeoutError instead of spawning an unbounded thread (memory-resource lens).
    # Drain whatever permits are currently free (earlier tests may hold some), so this
    # test is independent of run order.
    drained = 0
    while utils._WORKER_SEMAPHORE.acquire(blocking=False):
        drained += 1
    try:
        start = time.monotonic()
        try:
            utils._call_with_timeout(lambda: "x", 5.0, "capped")
            assert False, "expected TimeoutError when no worker slot is free"
        except TimeoutError as exc:
            assert "no worker slot free" in str(exc)
        # Must fail within the acquire grace, not block for the 5s work timeout.
        assert time.monotonic() - start < utils._WORKER_ACQUIRE_GRACE_S + 2
    finally:
        for _ in range(drained):
            utils._WORKER_SEMAPHORE.release()


def test_timed_out_worker_holds_then_frees_permit():
    # A timed-out worker keeps its permit until the work truly ends (throttles a
    # timeout storm); once the work finishes the permit is returned (no permanent leak).
    release = threading.Event()
    before = utils._WORKER_SEMAPHORE._value  # available permits (CPython BoundedSemaphore)
    try:
        try:
            utils._call_with_timeout(lambda: release.wait(30), 0.2, "held")
            assert False, "expected TimeoutError"
        except TimeoutError:
            pass
        # While the worker is still blocked, its permit is NOT back yet.
        assert utils._WORKER_SEMAPHORE._value == before - 1
    finally:
        release.set()
    # Give the worker a moment to run its finally: and release the permit.
    for _ in range(50):
        if utils._WORKER_SEMAPHORE._value == before:
            break
        time.sleep(0.02)
    assert utils._WORKER_SEMAPHORE._value == before, "permit was not returned after work ended"


def test_backend_resolve_retries_then_succeeds():
    # A transient failure on the first attempt must self-heal on a retry, not fail
    # the phase (chaos-engineering lens).
    utils._ensure_scripts_importable(WS)
    import backend_config
    real_resolve = backend_config.resolve
    good = resolve_backend(WS)  # capture a valid spec to hand back on the 2nd try
    calls = {"n": 0}

    def flaky(*_a, **_k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise ConnectionError("transient backend blip")
        return good

    orig_base = utils._BACKEND_RETRY_BASE_S
    try:
        backend_config.resolve = flaky
        utils._BACKEND_RETRY_BASE_S = 0.01  # keep the backoff sleep tiny
        spec = resolve_backend(WS)
        assert calls["n"] == 2, "should have retried once then succeeded"
        assert spec == good
    finally:
        backend_config.resolve = real_resolve
        utils._BACKEND_RETRY_BASE_S = orig_base


def test_backend_resolve_gives_up_after_attempts():
    # A persistently failing backend must surface a clear error after the bounded
    # retries, not retry forever (chaos-engineering / error-handling lens).
    utils._ensure_scripts_importable(WS)
    import backend_config
    real_resolve = backend_config.resolve
    calls = {"n": 0}

    def always_fail(*_a, **_k):
        calls["n"] += 1
        raise ConnectionError("backend down")

    orig_base = utils._BACKEND_RETRY_BASE_S
    try:
        backend_config.resolve = always_fail
        utils._BACKEND_RETRY_BASE_S = 0.01
        try:
            resolve_backend(WS)
            assert False, "expected the failure to surface after retries"
        except ConnectionError:
            pass
        assert calls["n"] == utils._BACKEND_RESOLVE_ATTEMPTS
    finally:
        backend_config.resolve = real_resolve
        utils._BACKEND_RETRY_BASE_S = orig_base


def test_backend_resolve_valueerror_not_retried():
    # A deterministic ValueError (unknown provider) is not transient — it must
    # propagate on the FIRST attempt without wasteful retries (correctness of retry
    # scope; don't mask a config bug behind backoff).
    utils._ensure_scripts_importable(WS)
    import backend_config
    real_resolve = backend_config.resolve
    calls = {"n": 0}

    def bad_config(*_a, **_k):
        calls["n"] += 1
        raise ValueError("unknown provider")

    try:
        backend_config.resolve = bad_config
        try:
            resolve_backend(WS)
            assert False, "expected ValueError"
        except ValueError:
            pass
        assert calls["n"] == 1, "ValueError must not be retried"
    finally:
        backend_config.resolve = real_resolve


# --- round-5: backoff jitter + INFO resolve logging -------------------------
def test_backoff_delay_is_jittered_within_ceiling():
    # With jitter ON, each backoff must be a random value in [0, capped_exponential],
    # NOT the fixed exponential — so concurrent callers desynchronize (chaos lens).
    orig = utils._BACKEND_RETRY_JITTER
    try:
        utils._BACKEND_RETRY_JITTER = True
        for attempt in range(1, utils._BACKEND_RESOLVE_ATTEMPTS + 1):
            ceiling = min(utils._BACKEND_RETRY_BASE_S * (2 ** (attempt - 1)),
                          utils._BACKEND_RETRY_MAX_S)
            samples = {utils._backoff_delay(attempt) for _ in range(200)}
            assert all(0.0 <= s <= ceiling for s in samples), f"attempt {attempt} out of range"
            # A jittered source yields many distinct values, not one fixed number.
            assert len(samples) > 20, f"attempt {attempt} looks un-jittered: {samples}"
    finally:
        utils._BACKEND_RETRY_JITTER = orig


def test_backoff_delay_deterministic_when_jitter_off():
    # Jitter can be disabled for reproducible tests; then it's exactly the ceiling.
    orig = utils._BACKEND_RETRY_JITTER
    try:
        utils._BACKEND_RETRY_JITTER = False
        assert utils._backoff_delay(1) == utils._BACKEND_RETRY_BASE_S
        # Grows exponentially but is capped at _BACKEND_RETRY_MAX_S.
        assert utils._backoff_delay(99) == utils._BACKEND_RETRY_MAX_S
    finally:
        utils._BACKEND_RETRY_JITTER = orig


def test_backoff_delays_desync_across_callers():
    # Two independent callers must not draw identical backoff sequences (that's the
    # whole point of jitter — no lockstep thundering herd on backend recovery).
    orig = utils._BACKEND_RETRY_JITTER
    try:
        utils._BACKEND_RETRY_JITTER = True
        seq_a = [utils._backoff_delay(a) for a in range(1, 4)]
        seq_b = [utils._backoff_delay(a) for a in range(1, 4)]
        assert seq_a != seq_b, "jitter should desynchronize concurrent retriers"
    finally:
        utils._BACKEND_RETRY_JITTER = orig


class _CapturingHandler(logging.Handler):
    def __init__(self):
        super().__init__()
        self.records = []

    def emit(self, record):
        self.records.append(record)


def test_resolve_backend_logs_success_at_info_with_model():
    # Backend resolution is critical init: it must log success at INFO and name the
    # provider AND model, so ops can see the binding without debug logging (obs lens).
    handler = _CapturingHandler()
    handler.setLevel(logging.INFO)
    utils.log.addHandler(handler)
    prev_level = utils.log.level
    utils.log.setLevel(logging.INFO)
    try:
        spec = resolve_backend(WS)
        infos = [r for r in handler.records
                 if r.levelno == logging.INFO and "resolved backend" in r.getMessage()]
        assert infos, "expected an INFO 'resolved backend' log line"
        msg = infos[-1].getMessage()
        assert spec["provider"] in msg, "provider missing from resolve log"
        assert spec["model"] in msg, "model missing from resolve log"
    finally:
        utils.log.removeHandler(handler)
        utils.log.setLevel(prev_level)


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
