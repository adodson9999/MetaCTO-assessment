#!/usr/bin/env python3
"""Unit tests for agents/common/auth_harness.py — the deterministic auth-flow executor.

Covers every public function AND the build->send->record workflow of run_auth_test(),
including its failure paths, with NO real network calls (auth_spec's HTTP layer is
monkeypatched per test):

  * _assert_sandbox: allows in-sandbox paths, rejects traversal/absolute escapes.
  * _assert_private_host: allows loopback/private, rejects public host + public IP.
  * _atomic_write: writes inside sandbox, refuses out-of-sandbox, leaves no temp on failure.
  * load_security / _config: happy path + missing/malformed file degrade (no crash).
  * scheme_brief: renders documented schemes + not-implemented list; tolerant of junk.
  * extract_json: fenced, bare, none, non-str, malformed -> correct value / None.
  * _message_of: JSON object, non-JSON, non-dict, oversized, non-str -> "".
  * everos_note: writes the local note even when the pool POST is stubbed to fail;
    refuses a non-private pool host; the local note is sandbox-confined.
  * emit: writes the agent result JSON atomically with the right metric name/value.
  * _write_staging_findings: numbers steps and writes JSON in the staging dir.
  * run_auth_test WORKFLOW: happy path (valid+invalid), down endpoint (code -1),
    non-2xx, malformed body, generate() raising, and empty plan -> explicit failure
    case, correct pass/FAR/FRR math, and result + staging files on disk.

Run: agent-foundry/.venv/bin/python agent-foundry/tests/unit/agents/common/test_auth_harness.py
"""
from __future__ import annotations

import importlib
import json
import os
import sys
import tempfile
from pathlib import Path

WS = Path(__file__).resolve().parents[4]          # agent-foundry
sys.path.insert(0, str(WS))
sys.path.insert(0, str(WS / "agents" / "common"))

# Import against a throwaway workspace so module-level path resolution is harmless.
_BOOT = tempfile.mkdtemp(prefix="auth_harness_boot_")
os.environ["FORGE_WORKSPACE"] = _BOOT
os.environ["FORGE_SANDBOX_ROOT"] = _BOOT
os.environ["FORGE_RUN_ID"] = "utrun"

import agents.common.auth_harness as h  # noqa: E402

importlib.reload(h)
# auth_harness does `import auth_spec` off sys.path (top-level name), so patch the
# SAME module object it holds — not agents.common.auth_spec (a distinct object).
spec = h.auth_spec


# --------------------------------------------------------------------------- #
# Harness for pointing the module at a fresh sandbox + stubbing the HTTP layer
# --------------------------------------------------------------------------- #
class _Sandbox:
    """Context manager: fresh tempdir wired as WORKSPACE + SANDBOX_ROOT, and the
    auth_spec HTTP/credential layer stubbed so NO real network call happens."""

    def __init__(self) -> None:
        self._tmp = tempfile.TemporaryDirectory()
        self.root = Path(self._tmp.name).resolve()
        self._saved: dict = {}

    def __enter__(self) -> "_Sandbox":
        self._saved = {
            "WORKSPACE": h.WORKSPACE, "SANDBOX_ROOT": h.SANDBOX_ROOT,
            "build": spec.build_credential, "request": spec._request,
            "post": h._post_everos,
        }
        h.WORKSPACE = self.root
        h.SANDBOX_ROOT = self.root
        # Default stubs: valid creds + a 200 body; overridden per test.
        spec.build_credential = lambda recipe, base, secret: ({"Authorization": "Bearer x"}, "stub")
        spec._request = lambda base, method, path, headers=None: (200, '{"message":"ok"}')
        h._post_everos = lambda url, body, idem_key=None: None  # never touch the network
        return self

    def __exit__(self, *a) -> None:
        h.WORKSPACE = self._saved["WORKSPACE"]
        h.SANDBOX_ROOT = self._saved["SANDBOX_ROOT"]
        spec.build_credential = self._saved["build"]
        spec._request = self._saved["request"]
        h._post_everos = self._saved["post"]
        self._tmp.cleanup()

    def stub_request(self, fn) -> None:
        spec._request = fn

    def stub_build(self, fn) -> None:
        spec.build_credential = fn


def _plan(*labels_recipes_expected) -> dict:
    subtests = [{"label": lbl, "credential": rec, "expected_class": exp}
                for lbl, rec, exp in labels_recipes_expected]
    return {"protected_endpoint": {"method": "GET", "path": "/auth/me"},
            "schemes": [{"scheme": "bearerJWT", "implemented": True, "subtests": subtests}],
            "not_applicable": [{"item": "apiKey", "status": "needs_to_be_built_and_tested"}]}


# --------------------------------------------------------------------------- #
# _assert_sandbox
# --------------------------------------------------------------------------- #
def test_assert_sandbox_allows_child():
    with _Sandbox() as sb:
        h._assert_sandbox(sb.root / "results" / "x.json")  # no raise


def test_assert_sandbox_rejects_traversal():
    with _Sandbox() as sb:
        try:
            h._assert_sandbox(sb.root / ".." / "escape.json")
            assert False, "expected PermissionError for traversal"
        except PermissionError:
            pass


def test_assert_sandbox_rejects_absolute_escape():
    with _Sandbox():
        try:
            h._assert_sandbox(Path("/etc/passwd"))
            assert False, "expected PermissionError for absolute escape"
        except PermissionError:
            pass


# --------------------------------------------------------------------------- #
# _assert_private_host (SSRF guard)
# --------------------------------------------------------------------------- #
def test_private_host_allows_loopback_and_private():
    for url in ("http://localhost:8000", "http://127.0.0.1:8000",
                "http://10.0.0.5", "http://192.168.1.9", "http://[::1]:8000"):
        h._assert_private_host(url)  # no raise


def test_private_host_rejects_public_name_and_ip():
    for url in ("http://evil.example.com", "http://8.8.8.8:80"):
        try:
            h._assert_private_host(url)
            assert False, f"expected PermissionError for {url}"
        except PermissionError:
            pass


def test_private_host_rejects_non_http_and_schemeless():
    """file:// and other non-http(s) schemes (empty hostname) must be refused, not
    slip past the loopback allow-list (vulnerability lens)."""
    for url in ("file:///etc/passwd", "gopher://127.0.0.1/", "ftp://127.0.0.1/",
                "//127.0.0.1/x", "127.0.0.1:8000"):
        try:
            h._assert_private_host(url)
            assert False, f"expected PermissionError for {url}"
        except PermissionError:
            pass


# --------------------------------------------------------------------------- #
# _atomic_write
# --------------------------------------------------------------------------- #
def test_atomic_write_inside_sandbox():
    with _Sandbox() as sb:
        p = sb.root / "sub" / "f.json"
        p.parent.mkdir(parents=True)
        h._atomic_write(p, '{"k": 1}')
        assert json.loads(p.read_text())["k"] == 1


def test_atomic_write_refuses_outside_sandbox_and_leaves_no_temp():
    with _Sandbox() as sb:
        outside = sb.root.parent / "outside.json"
        try:
            h._atomic_write(outside, "{}")
            assert False, "expected PermissionError"
        except PermissionError:
            pass
        # sandbox refusal happens before any temp is created in the sandbox
        leftovers = list(sb.root.glob(".*.tmp"))
        assert leftovers == [], f"temp files leaked: {leftovers}"


def test_atomic_write_closes_fd_and_cleans_temp_when_fdopen_raises():
    """If os.fdopen raises AFTER mkstemp succeeds, the raw fd must be closed (no
    FD leak) AND the temp file unlinked AND the failure logged before re-raise
    (memory-resource + observability)."""
    with _Sandbox() as sb:
        p = sb.root / "x.json"
        closed = {"fd": None}
        real_fdopen, real_close = os.fdopen, os.close

        def fdopen_raises(fd, *a, **k):
            raise OSError("simulated fdopen failure")

        def track_close(fd):
            closed["fd"] = fd
            return real_close(fd)
        os.fdopen = fdopen_raises
        os.close = track_close
        try:
            raised = False
            try:
                h._atomic_write(p, "{}")
            except OSError:
                raised = True
            assert raised, "the fdopen failure must propagate"
            assert closed["fd"] is not None, "raw fd was never closed -> FD leak"
        finally:
            os.fdopen, os.close = real_fdopen, real_close
        # no temp left behind, and the real file was not created
        assert list(sb.root.glob(".*.tmp")) == []
        assert not p.exists()


# --------------------------------------------------------------------------- #
# _read_text_capped — bounded external-file reads (adversarial-input)
# --------------------------------------------------------------------------- #
def test_read_text_capped_reads_small_file():
    with _Sandbox() as sb:
        f = sb.root / "small.txt"
        f.write_text("hello")
        assert h._read_text_capped(f) == "hello"


def test_read_text_capped_rejects_oversized_file():
    with _Sandbox() as sb:
        f = sb.root / "big.txt"
        f.write_bytes(b"a" * (h._MAX_FILE_BYTES + 10))
        try:
            h._read_text_capped(f)
            assert False, "expected ValueError for oversized file"
        except ValueError:
            pass


def test_load_security_and_config_degrade_on_oversized_file():
    """A 10GB-style config/spec must degrade to {} instead of raising MemoryError
    past the OSError/ValueError callers (adversarial-input)."""
    with _Sandbox() as sb:
        (sb.root / "data").mkdir()
        (sb.root / "data" / "auth_openapi.json").write_bytes(b"{" + b" " * (h._MAX_FILE_BYTES + 5))
        assert h.load_security() == {}
        (sb.root / "config.toml").write_bytes(b"[memory]\n" + b"#" * (h._MAX_FILE_BYTES + 5))
        assert h._config()["app_id"] is None


def test_read_text_capped_tolerates_broken_utf8():
    """Broken/hostile UTF-8 must NOT raise UnicodeDecodeError; it decodes with
    replacement chars so callers degrade via ValueError on the parse, not a crash
    (adversarial-input)."""
    with _Sandbox() as sb:
        f = sb.root / "broken.bin"
        f.write_bytes(b"\xff\xfe\x00 not utf-8 \xc3\x28")   # invalid sequences + NUL
        out = h._read_text_capped(f)                        # must not raise
        assert isinstance(out, str) and "�" in out


def test_external_files_with_broken_utf8_degrade():
    """A spec/config/metric file full of invalid UTF-8 degrades to {}/defaults
    instead of escaping the handlers (adversarial-input)."""
    with _Sandbox() as sb:
        (sb.root / "data").mkdir()
        (sb.root / "data" / "auth_openapi.json").write_bytes(b"\xff\xfe\xc3\x28{bad")
        assert h.load_security() == {}
        (sb.root / "config.toml").write_bytes(b"\xff\xfe app_id = \xc3\x28")
        assert h._config()["app_id"] is None
        (sb.root / "judge").mkdir()
        (sb.root / "judge" / "auth_metric.json").write_bytes(b"\xff\xfe\xc3\x28")
        h.emit("autf8", 1.0, "/tmp/raw.json")               # must not raise
        doc = json.loads((sb.root / "results" / "runs" / "utrun" / "autf8.json").read_text())
        assert doc["metric_name"] == "auth_flow_pass_rate_pct"  # fell back to default


# --------------------------------------------------------------------------- #
# load_security / _config resilience
# --------------------------------------------------------------------------- #
def test_load_security_happy_and_missing():
    with _Sandbox() as sb:
        assert h.load_security() == {}                      # no file -> {}
        (sb.root / "data").mkdir()
        (sb.root / "data" / "auth_openapi.json").write_text('{"components": {}}')
        assert h.load_security() == {"components": {}}


def test_load_security_malformed_degrades():
    with _Sandbox() as sb:
        (sb.root / "data").mkdir()
        (sb.root / "data" / "auth_openapi.json").write_text("{not json")
        assert h.load_security() == {}                      # degrades, no crash


def test_config_missing_and_malformed_degrade():
    with _Sandbox() as sb:
        assert h._config() == {"everos_base_url": None, "app_id": None, "project_id": None}
        (sb.root / "config.toml").write_text("[memory]\napp_id = 'forge'\n")
        assert h._config()["app_id"] == "forge"
        (sb.root / "config.toml").write_text("[memory\nbroken")
        assert h._config()["app_id"] is None                # malformed -> defaults


# --------------------------------------------------------------------------- #
# scheme_brief
# --------------------------------------------------------------------------- #
def test_scheme_brief_renders_schemes():
    with _Sandbox() as sb:
        (sb.root / "data").mkdir()
        (sb.root / "data" / "auth_openapi.json").write_text(json.dumps({
            "components": {"securitySchemes": {
                "bearerJWT": {"type": "http", "scheme": "bearer", "bearerFormat": "JWT"}}},
            "x-not-implemented": ["apiKey", "oauth2"]}))
        brief = h.scheme_brief()
        assert "protected_endpoint: GET /auth/me" in brief
        # Exact contract strings the LLM relies on (unit-test: verify verbatim).
        assert "login_endpoint: POST /auth/login (creds: emilys / emilyspass)" in brief
        assert "revoke_equivalent: POST /auth/logout (no dedicated /auth/revoke exists)" in brief
        assert "documented_security_schemes:" in brief
        assert "bearerJWT: type=http scheme=bearer format=JWT" in brief
        assert "['apiKey', 'oauth2']" in brief


def test_scheme_brief_tolerates_junk_scheme():
    with _Sandbox() as sb:
        (sb.root / "data").mkdir()
        (sb.root / "data" / "auth_openapi.json").write_text(json.dumps({
            "components": {"securitySchemes": {"weird": "not-a-dict"}}}))
        brief = h.scheme_brief()                             # must not raise
        assert "weird:" in brief


# --------------------------------------------------------------------------- #
# extract_json
# --------------------------------------------------------------------------- #
def test_extract_json_variants():
    assert h.extract_json("```json\n{\"a\": 1}\n```") == {"a": 1}
    assert h.extract_json("noise {\"b\": 2} tail") == {"b": 2}
    assert h.extract_json("no object here") is None
    assert h.extract_json(None) is None
    assert h.extract_json("") is None
    assert h.extract_json("{unbalanced") is None
    assert h.extract_json(123) is None                       # non-str


def test_extract_json_caps_huge_input_before_scan():
    """A gigantic untrusted blob is truncated to _MAX_EXTRACT_BYTES BEFORE the
    regex/brace scan, so extract_json stays fast and never pins the CPU on O(n)
    work (adversarial-input). A valid object within the cap is still found; junk
    past the cap is ignored."""
    # Valid object at the very start, then a massive tail well past the cap.
    payload = '{"ok": 1}' + ("x" * (h._MAX_EXTRACT_BYTES + 1000))
    assert h.extract_json(payload) == {"ok": 1}
    # An object located ONLY beyond the cap is not scanned (proves truncation).
    hidden = ("y" * (h._MAX_EXTRACT_BYTES + 100)) + '{"late": 2}'
    assert h.extract_json(hidden) is None


# --------------------------------------------------------------------------- #
# _message_of
# --------------------------------------------------------------------------- #
def test_message_of_variants():
    assert h._message_of('{"message": "hi"}') == "hi"
    assert h._message_of('{"other": 1}') == ""
    assert h._message_of("not json") == ""
    assert h._message_of("[1, 2, 3]") == ""                  # JSON but not an object
    assert h._message_of(None) == ""
    assert h._message_of("x" * (h._MAX_BODY_BYTES + 1)) == ""  # oversized -> ""


# --------------------------------------------------------------------------- #
# everos_note
# --------------------------------------------------------------------------- #
def test_everos_note_writes_local_even_when_pool_fails():
    with _Sandbox() as sb:
        def boom(url, body, idem_key=None):
            raise OSError("pool down")
        h._post_everos = boom
        h.everos_note("agentA", "hello world")
        note = sb.root / "memory" / "agent-notes" / "agentA.md"
        assert note.exists() and "hello world" in note.read_text()


def test_everos_note_refuses_public_pool_host_but_still_notes():
    with _Sandbox() as sb:
        (sb.root / "config.toml").write_text(
            "[memory]\neveros_base_url = 'http://8.8.8.8:8000'\n")
        called = {"n": 0}
        h._post_everos = lambda url, body, idem_key=None: called.__setitem__("n", called["n"] + 1)
        h.everos_note("agentB", "note text")
        assert called["n"] == 0, "must not POST to a public host"
        note = sb.root / "memory" / "agent-notes" / "agentB.md"
        assert note.exists() and "note text" in note.read_text()


def test_everos_note_add_carries_stable_idempotency_key():
    """The add + flush POSTs of one note share ONE idem key so a retried add is
    not double-applied (data-integrity)."""
    with _Sandbox() as sb:
        seen: list = []
        h._post_everos = lambda url, body, idem_key=None: seen.append((url, idem_key))
        h.everos_note("agentIK", "note")
        keys = {k for _, k in seen}
        assert len(seen) == 2 and len(keys) == 1 and next(iter(keys))  # one non-empty key


def test_everos_note_survives_readonly_notes_dir():
    """A failure to write the local breadcrumb must not crash the note call: the
    real _append_local_note swallows the OSError and logs it (error-handling-
    resilience). We make memory/ a FILE so its mkdir(parents=True) fails."""
    with _Sandbox() as sb:
        (sb.root / "memory").write_text("not a dir")   # blocks memory/agent-notes mkdir
        h.everos_note("agentRO", "note")               # must not raise


def test_local_note_rotates_when_oversized():
    """The per-agent notes file is bounded: once it exceeds _MAX_NOTE_BYTES the
    next append rotates it to a single .1 backup, so it cannot grow without bound
    (memory-resource)."""
    with _Sandbox() as sb:
        notes = sb.root / "memory" / "agent-notes"
        notes.mkdir(parents=True)
        note = notes / "agentROT.md"
        note.write_bytes(b"x" * (h._MAX_NOTE_BYTES + 1))   # pre-fill over the cap
        h._append_local_note("agentROT", "fresh line")
        backup = notes / "agentROT.md.1"
        assert backup.exists(), "oversized note must rotate to .1"
        assert note.exists() and note.stat().st_size < h._MAX_NOTE_BYTES
        assert "fresh line" in note.read_text()             # new content in the fresh file


def test_local_note_does_not_rotate_when_small():
    """A small notes file is appended in place (no needless rotation churn)."""
    with _Sandbox() as sb:
        h._append_local_note("agentSMALL", "line one")
        h._append_local_note("agentSMALL", "line two")
        notes = sb.root / "memory" / "agent-notes"
        assert not (notes / "agentSMALL.md.1").exists()
        body = (notes / "agentSMALL.md").read_text()
        assert "line one" in body and "line two" in body


def test_post_everos_retries_then_raises_on_persistent_transient():
    """Bounded retry: a persistently-refused pool raises after the last attempt
    (so everos_note logs+degrades), and the attempt count is bounded. This tests
    the REAL _post_everos, so it deliberately does not use _Sandbox (which stubs
    _post_everos out)."""
    attempts = {"n": 0}
    real_sleep = h.time.sleep
    orig_urlopen = h.urllib.request.urlopen
    h.time.sleep = lambda *_a, **_k: None  # don't actually back off in the test

    def refuse(req, timeout=None):
        attempts["n"] += 1
        raise h.urllib.error.URLError("refused")
    h.urllib.request.urlopen = refuse
    try:
        raised = False
        try:
            h._post_everos("http://127.0.0.1:8000/api/v1/memory/add", b"{}", "k")
        except h.urllib.error.URLError:
            raised = True
        assert raised, "persistent transient failure must surface"
        assert attempts["n"] == h._EVEROS_RETRIES + 1
    finally:
        h.urllib.request.urlopen = orig_urlopen
        h.time.sleep = real_sleep


def test_post_everos_http_error_is_definite_no_retry():
    """A 4xx/5xx HTTPError is a definite answer: _post_everos returns immediately
    (one attempt, no retry) and does not raise (unit-test gap)."""
    import io
    attempts = {"n": 0}
    orig_urlopen = h.urllib.request.urlopen

    def http_500(req, timeout=None):
        attempts["n"] += 1
        raise h.urllib.error.HTTPError(req.full_url, 500, "err", {}, io.BytesIO(b"boom"))
    h.urllib.request.urlopen = http_500
    try:
        h._post_everos("http://127.0.0.1:8000/api/v1/memory/add", b"{}", "k")  # no raise
        assert attempts["n"] == 1, "HTTPError must not be retried"
    finally:
        h.urllib.request.urlopen = orig_urlopen


# --------------------------------------------------------------------------- #
# _write_staging_findings
# --------------------------------------------------------------------------- #
def test_write_staging_findings_numbers_steps():
    with _Sandbox() as sb:
        h._write_staging_findings("agentC", "get-auth-me", "GET /auth/me",
                                  [{"assertion_result": "PASS"}, {"assertion_result": "FAIL"}])
        p = sb.root / "results" / "runs" / "utrun" / "staging" / "agentC" / "get-auth-me-findings.json"
        doc = json.loads(p.read_text())
        assert doc["agent"] == "agentC"
        assert [f["step_number"] for f in doc["findings"]] == [1, 2]


# --------------------------------------------------------------------------- #
# emit
# --------------------------------------------------------------------------- #
def test_emit_writes_result_json():
    with _Sandbox() as sb:
        h.emit("agentD", 87.5, "/tmp/raw.json", extra={"executed_cases": 5})
        p = sb.root / "results" / "runs" / "utrun" / "agentD.json"
        doc = json.loads(p.read_text())
        assert doc["metric_value"] == 87.5
        assert doc["metric_name"] == "auth_flow_pass_rate_pct"
        assert doc["executed_cases"] == 5


def test_emit_uses_metric_file_headline():
    with _Sandbox() as sb:
        (sb.root / "judge").mkdir()
        (sb.root / "judge" / "auth_metric.json").write_text('{"headline_metric": "auth_flow_fidelity"}')
        h.emit("agentE", 12.0, "/tmp/raw.json")
        doc = json.loads((sb.root / "results" / "runs" / "utrun" / "agentE.json").read_text())
        assert doc["metric_name"] == "auth_flow_fidelity"


# --------------------------------------------------------------------------- #
# run_auth_test — the full build -> send -> record workflow + failure paths
# --------------------------------------------------------------------------- #
def _responses(sb, mapping):
    """Stub _request to return (code, body) chosen by the recipe kind the sub-test
    built. We key off the recipe passed to build_credential via a closure."""
    state = {"recipe_kind": None}

    def build(recipe, base, secret):
        state["recipe_kind"] = (recipe or {}).get("kind")
        return ({"Authorization": "Bearer x"}, "stub")

    def request(base, method, path, headers=None):
        return mapping[state["recipe_kind"]]

    sb.stub_build(build)
    sb.stub_request(request)


def test_run_auth_test_happy_path_math():
    with _Sandbox() as sb:
        plan = _plan(("valid", {"kind": "valid_token"}, "2xx"),
                     ("missing", {"kind": "no_auth"}, "401"))
        _responses(sb, {"valid_token": (200, '{"message":"ok"}'),
                        "no_auth": (401, '{"message":"unauthorized"}')})
        raw = h.run_auth_test("aflow", lambda: plan)
        assert raw["executed_cases"] == 2
        assert raw["auth_flow_pass_rate_pct"] == 100.0
        assert raw["false_acceptance_rate_pct"] == 0.0
        assert raw["false_rejection_rate_pct"] == 0.0
        # result + staging files written
        assert (sb.root / "results" / "runs" / "utrun" / "aflow.json").exists()
        assert (sb.root / "results" / "runs" / "utrun" / "aflow.cases.json").exists()
        assert (sb.root / "results" / "runs" / "utrun" / "staging" / "aflow"
                / "get-auth-me-findings.json").exists()


def test_run_auth_test_false_acceptance_and_rejection():
    with _Sandbox() as sb:
        plan = _plan(("valid", {"kind": "valid_token"}, "2xx"),
                     ("missing", {"kind": "no_auth"}, "401"))
        # valid rejected (401) -> false reject; invalid accepted (200) -> false accept
        _responses(sb, {"valid_token": (401, '{"message":"no"}'),
                        "no_auth": (200, '{"message":"yes"}')})
        raw = h.run_auth_test("aflow2", lambda: plan)
        assert raw["false_rejection_count"] == 1
        assert raw["false_acceptance_count"] == 1
        assert raw["auth_flow_pass_rate_pct"] == 0.0


def test_run_auth_test_down_endpoint_records_failure_not_crash():
    with _Sandbox() as sb:
        plan = _plan(("valid", {"kind": "valid_token"}, "2xx"))
        _responses(sb, {"valid_token": (-1, "")})            # connection failed sentinel
        raw = h.run_auth_test("adown", lambda: plan)
        assert raw["executed_cases"] == 1
        assert raw["auth_flow_pass_rate_pct"] == 0.0
        assert raw["cases"][0]["actual_class"] != "2xx"


def test_run_auth_test_malformed_body_does_not_crash():
    with _Sandbox() as sb:
        plan = _plan(("valid", {"kind": "valid_token"}, "2xx"))
        _responses(sb, {"valid_token": (200, "<<<not json>>>")})
        raw = h.run_auth_test("abody", lambda: plan)
        assert raw["cases"][0]["message"] == ""              # unparseable body -> ""
        assert raw["auth_flow_pass_rate_pct"] == 100.0       # still classified 2xx


def test_run_auth_test_build_failure_records_case():
    with _Sandbox() as sb:
        plan = _plan(("valid", {"kind": "valid_token"}, "2xx"))

        def build_raises(recipe, base, secret):
            raise RuntimeError("credential build blew up")
        sb.stub_build(build_raises)
        raw = h.run_auth_test("abuild", lambda: plan)
        case = raw["cases"][0]
        assert raw["executed_cases"] == 1
        assert case["task_rule_pass"] is False
        # The exception type + message are captured verbatim in both fields, so a
        # future reader can diagnose WHICH failure happened (unit-test: tighten).
        assert case["error"] == "RuntimeError: credential build blew up"
        assert case["construction_note"] == "RuntimeError: credential build blew up"
        assert case["actual_code"] is None and case["actual_class"] == "none"


def test_run_auth_test_generate_raises_records_no_plan_case():
    with _Sandbox() as sb:
        def gen():
            raise ValueError("model exploded")
        raw = h.run_auth_test("agen", gen)
        assert raw["executed_cases"] == 0
        assert raw["cases"][-1]["label"] == "_none_"
        assert raw["cases"][-1]["task_rule_pass"] is False
        assert "model exploded" in raw["cases"][-1]["error"]


def test_run_auth_test_generate_hang_times_out_and_completes():
    """Injected fault: generate() HANGS with no exception (wedged LLM). The run
    must not wedge — it bounds generate() with a hard timeout, degrades to an empty
    plan, records the timeout as a failure, and completes (chaos-engineering).
    We shrink the timeout so the test is fast, and release the hung worker after."""
    with _Sandbox() as sb:
        release = __import__("threading").Event()
        saved_timeout = h._GENERATE_TIMEOUT_S
        h._GENERATE_TIMEOUT_S = 0.2

        def hang():
            release.wait(30)   # blocks well past the timeout; daemon worker abandoned
            return {}
        try:
            raw = h.run_auth_test("ahang", hang)   # must return, not wedge
        finally:
            h._GENERATE_TIMEOUT_S = saved_timeout
            release.set()
        assert raw["executed_cases"] == 0
        assert "timed out" in raw["cases"][-1]["error"]


def test_run_auth_test_non_local_target_degrades_no_crash():
    """Injected fault: a misconfigured non-local TARGET_BASE_URL. _assert_local
    raises, but run_auth_test must degrade to a recorded failure with NO requests
    sent, never an uncaught crash (error-handling-resilience)."""
    with _Sandbox() as sb:
        sent = {"n": 0}

        def counting_request(base, method, path, headers=None):
            sent["n"] += 1
            return (200, "{}")
        sb.stub_request(counting_request)
        saved = h.TARGET_BASE_URL
        h.TARGET_BASE_URL = "http://8.8.8.8:9999"   # public -> _assert_local refuses
        try:
            plan = _plan(("valid", {"kind": "valid_token"}, "2xx"))
            raw = h.run_auth_test("aremote", lambda: plan)   # must not raise
        finally:
            h.TARGET_BASE_URL = saved
        assert sent["n"] == 0, "no request may be sent to a refused target"
        assert raw["executed_cases"] == 0
        assert "target refused" in raw["cases"][-1]["error"]


def test_generate_plan_returns_error_on_raise():
    """_generate_plan surfaces a raised generate() as (empty plan, error string)
    without propagating (chaos-engineering / resilience unit coverage)."""
    plan, err = h._generate_plan(lambda: (_ for _ in ()).throw(ValueError("boom")))
    assert plan == {} and err == "ValueError: boom"


def test_run_auth_test_empty_plan_records_no_plan_case():
    with _Sandbox() as sb:
        raw = h.run_auth_test("aempty", lambda: {})
        assert raw["executed_cases"] == 0
        # Strong assertion: verify the full no-plan case shape, not just truthiness.
        case = raw["cases"][-1]
        assert case["label"] == "_none_"
        assert case["scheme"] is None and case["recipe"] is None
        assert case["actual_class"] == "none" and case["actual_code"] is None
        assert case["task_rule_pass"] is False
        assert case["error"] == "no executable sub-tests produced"
        # aggregate rates all zero when nothing executed
        assert (raw["auth_flow_pass_rate_pct"], raw["false_acceptance_rate_pct"],
                raw["false_rejection_rate_pct"]) == (0.0, 0.0, 0.0)


def test_run_auth_test_caps_hostile_subtest_count():
    """A plan with far more than _MAX_SUBTESTS sub-tests executes at most the cap
    (adversarial-input / system-design): a 1M-subtest plan cannot pin the target."""
    with _Sandbox() as sb:
        n = h._MAX_SUBTESTS + 50
        plan = _plan(*[("missing", {"kind": "no_auth"}, "401") for _ in range(n)])
        _responses(sb, {"no_auth": (401, "{}")})
        raw = h.run_auth_test("acap", lambda: plan)
        assert raw["executed_cases"] == h._MAX_SUBTESTS


def test_run_auth_test_survives_staging_write_failure():
    """A full/read-only disk on the staging write must degrade (logged) and still
    produce the authoritative result JSON (chaos / error-handling-resilience)."""
    with _Sandbox() as sb:
        plan = _plan(("valid", {"kind": "valid_token"}, "2xx"))
        _responses(sb, {"valid_token": (200, '{"message":"ok"}')})
        orig = h._write_staging_findings

        def boom(**kwargs):
            raise OSError("disk full")
        h._write_staging_findings = boom
        try:
            raw = h.run_auth_test("astage", lambda: plan)  # must not raise
        finally:
            h._write_staging_findings = orig
        assert raw["executed_cases"] == 1
        assert (sb.root / "results" / "runs" / "utrun" / "astage.json").exists()


def test_cases_write_failure_surfaces_and_avoids_split_write():
    """If the .cases.json write fails, the run does NOT emit a dangling {agent}.json
    pointing at a non-existent raw file (data-integrity), and it reports the loss
    to the caller via artifacts_persisted=False (error-handling-resilience). The
    run still returns its computed metrics rather than crashing (chaos)."""
    with _Sandbox() as sb:
        plan = _plan(("valid", {"kind": "valid_token"}, "2xx"))
        _responses(sb, {"valid_token": (200, '{"message":"ok"}')})
        orig = h._atomic_write

        def fail_cases(path, text):
            if str(path).endswith(".cases.json"):
                raise OSError("disk full on cases")
            return orig(path, text)
        h._atomic_write = fail_cases
        try:
            raw = h.run_auth_test("acases", lambda: plan)  # must not raise
        finally:
            h._atomic_write = orig
        assert raw["auth_flow_pass_rate_pct"] == 100.0
        assert raw["artifacts_persisted"] is False, "caller must learn of the loss"
        # No split write: neither the cases file nor the result pointer exists.
        assert not (sb.root / "results" / "runs" / "utrun" / "acases.cases.json").exists()
        assert not (sb.root / "results" / "runs" / "utrun" / "acases.json").exists()


def test_emit_failure_rolls_back_orphaned_cases_file():
    """If emit() fails AFTER the .cases.json wrote, the now-orphaned cases file is
    rolled back (unlinked) so disk holds NEITHER file — an all-or-nothing pair, no
    dangling raw file without its {agent}.json pointer (data-integrity). The run is
    reported unpersisted and never crashes (error-handling-resilience)."""
    with _Sandbox() as sb:
        plan = _plan(("valid", {"kind": "valid_token"}, "2xx"))
        _responses(sb, {"valid_token": (200, '{"message":"ok"}')})
        orig = h._atomic_write

        def fail_result(path, text):
            if str(path).endswith(".json") and not str(path).endswith(".cases.json"):
                raise OSError("disk full on result")
            return orig(path, text)
        h._atomic_write = fail_result
        try:
            raw = h.run_auth_test("aemit", lambda: plan)  # must not raise
        finally:
            h._atomic_write = orig
        assert raw["artifacts_persisted"] is False
        # All-or-nothing: the orphaned cases.json was rolled back; neither exists.
        assert not (sb.root / "results" / "runs" / "utrun" / "aemit.cases.json").exists()
        assert not (sb.root / "results" / "runs" / "utrun" / "aemit.json").exists()


def test_orphan_rollback_tombstones_when_unlink_fails():
    """Root fix: if emit() fails AND the rollback unlink() itself raises, the
    orphaned cases.json must NOT be left as a silently-misreadable result. It is
    neutralized in place with a self-describing tombstone marker, so a reader can
    never mistake it for a valid result (error-handling-resilience). The run still
    completes and reports artifacts_persisted=False, never crashing."""
    with _Sandbox() as sb:
        plan = _plan(("valid", {"kind": "valid_token"}, "2xx"))
        _responses(sb, {"valid_token": (200, '{"message":"ok"}')})
        orig_write = h._atomic_write
        cases_file = sb.root / "results" / "runs" / "utrun" / "atomb.cases.json"

        def fail_result(path, text):
            if str(path).endswith(".json") and not str(path).endswith(".cases.json"):
                raise OSError("disk full on result")
            return orig_write(path, text)

        real_unlink = Path.unlink

        def unlink_raises(self, *a, **k):
            if self == cases_file:
                raise OSError("unlink denied (read-only)")
            return real_unlink(self, *a, **k)

        h._atomic_write = fail_result
        Path.unlink = unlink_raises
        try:
            raw = h.run_auth_test("atomb", lambda: plan)   # must not raise
        finally:
            h._atomic_write = orig_write
            Path.unlink = real_unlink
        assert raw["artifacts_persisted"] is False
        # No {agent}.json pointer, and the un-removable orphan is a tombstone.
        assert not (sb.root / "results" / "runs" / "utrun" / "atomb.json").exists()
        assert cases_file.exists()
        assert json.loads(cases_file.read_text()).get("__forge_orphaned__") is True


def test_orphan_rollback_survives_unlink_and_tombstone_both_failing():
    """Absolute worst case: unlink() AND the tombstone write both raise. The run
    must STILL not crash and must report unpersisted — every rollback branch is
    exception-safe (error-handling-resilience)."""
    with _Sandbox() as sb:
        plan = _plan(("valid", {"kind": "valid_token"}, "2xx"))
        _responses(sb, {"valid_token": (200, '{"message":"ok"}')})
        orig_write = h._atomic_write
        cases_file = sb.root / "results" / "runs" / "utrun" / "aworst.cases.json"

        def fail_result(path, text):
            if str(path).endswith(".json") and not str(path).endswith(".cases.json"):
                raise OSError("disk full on result")
            return orig_write(path, text)

        real_unlink, real_wtext = Path.unlink, Path.write_text

        def unlink_raises(self, *a, **k):
            if self == cases_file:
                raise OSError("unlink denied")
            return real_unlink(self, *a, **k)

        def wtext_raises(self, *a, **k):
            if self == cases_file:
                raise OSError("tombstone denied")
            return real_wtext(self, *a, **k)

        h._atomic_write = fail_result
        Path.unlink, Path.write_text = unlink_raises, wtext_raises
        try:
            raw = h.run_auth_test("aworst", lambda: plan)   # must not raise
        finally:
            h._atomic_write = orig_write
            Path.unlink, Path.write_text = real_unlink, real_wtext
        assert raw["artifacts_persisted"] is False
        assert not (sb.root / "results" / "runs" / "utrun" / "aworst.json").exists()


def test_rollback_orphan_cases_unit_direct():
    """_rollback_orphan_cases removes an existing orphan and never raises for a
    missing one (direct unit coverage of the compensating action)."""
    with _Sandbox() as sb:
        run_dir = sb.root / "results" / "runs" / "utrun"
        run_dir.mkdir(parents=True)
        orphan = run_dir / "adirect.cases.json"
        orphan.write_text("{}")
        h._rollback_orphan_cases("adirect", orphan)
        assert not orphan.exists()
        h._rollback_orphan_cases("adirect", orphan)   # already gone -> must not raise


# --------------------------------------------------------------------------- #
# module-level guards / constants
# --------------------------------------------------------------------------- #
def test_request_timeout_mirror_matches_auth_spec():
    """The request-timeout bound is visible at the harness call site and tracks
    auth_spec's enforced value (network lens)."""
    assert h._REQUEST_TIMEOUT_S == getattr(spec, "REQUEST_TIMEOUT_S", 20)
    assert h._REQUEST_TIMEOUT_S > 0


def test_public_api_preserved():
    """Every public name dependents rely on is present with a compatible signature
    (api-contract). _post_everos gained an OPTIONAL idem_key, so old callers still
    work; run_auth_test/emit/everos_note signatures are unchanged."""
    import inspect
    names = ["_assert_sandbox", "_assert_private_host", "_atomic_write",
             "_write_staging_findings", "load_security", "scheme_brief",
             "extract_json", "_scan_balanced_object", "everos_note", "_post_everos",
             "_append_local_note", "_config", "_no_plan_case", "_execute_subtests",
             "_run_one_subtest", "_staging_steps", "_rates", "_persist_run",
             "run_auth_test", "_message_of", "emit"]
    for n in names:
        assert callable(getattr(h, n)), f"missing public symbol: {n}"
    assert list(inspect.signature(h.run_auth_test).parameters) == ["agent", "generate"]
    assert list(inspect.signature(h.emit).parameters) == \
        ["agent", "metric_value", "raw_output_path", "extra"]
    assert list(inspect.signature(h.everos_note).parameters) == ["agent", "text"]
    # _post_everos: idem_key is optional -> backward-compatible with 2-arg callers
    assert inspect.signature(h._post_everos).parameters["idem_key"].default is None


def test_run_auth_test_output_shape_unchanged():
    """The raw result dict + per-case keys match the contract dependents/gold read
    (api-contract): hardening must not add/remove/rename output keys."""
    with _Sandbox() as sb:
        plan = _plan(("valid", {"kind": "valid_token"}, "2xx"))
        _responses(sb, {"valid_token": (200, '{"message":"ok"}')})
        raw = h.run_auth_test("shape", lambda: plan)
        assert sorted(raw.keys()) == sorted([
            "agent", "run_id", "target", "auth_flow_pass_rate_pct",
            "false_acceptance_rate_pct", "false_rejection_rate_pct",
            "false_acceptance_count", "false_rejection_count", "executed_cases",
            "not_applicable_enumerated", "cases", "artifacts_persisted"])
        assert raw["artifacts_persisted"] is True   # additive resilience field
        assert sorted(raw["cases"][0].keys()) == sorted([
            "scheme", "label", "recipe", "construction_note", "expected_class",
            "actual_code", "actual_class", "message", "task_rule_pass", "error"])
        result = json.loads((sb.root / "results" / "runs" / "utrun" / "shape.json").read_text())
        assert result["metric_name"] == "auth_flow_pass_rate_pct"
        assert result["metric_value"] == 100.0


def test_no_hardcoded_default_secret():
    """There must be NO hardcoded fallback secret an attacker could read from the
    source and use to forge tokens (vulnerability / security lens). When
    JWT_SECRET is unset the fallback is a random per-process value, so two fresh
    resolutions differ and neither equals the old well-known literal."""
    import importlib
    saved = os.environ.pop("JWT_SECRET", None)
    try:
        m1 = importlib.reload(h)
        s1 = m1.SECRET
        m2 = importlib.reload(h)
        s2 = m2.SECRET
        assert s1 and s2, "SECRET must never be empty (would break signing)"
        assert s1 != "forge_test_secret" and s2 != "forge_test_secret"
        assert s1 != s2, "random fallback must differ per process/reload"
        assert not hasattr(m2, "_DEFAULT_SECRET"), "no hardcoded default secret symbol"
    finally:
        if saved is not None:
            os.environ["JWT_SECRET"] = saved
        importlib.reload(h)


def test_env_secret_is_used_when_set():
    """When JWT_SECRET is set it is used verbatim (so valid-token cases sign with
    the target's real key)."""
    import importlib
    saved = os.environ.get("JWT_SECRET")
    os.environ["JWT_SECRET"] = "an-explicit-key"
    try:
        m = importlib.reload(h)
        assert m.SECRET == "an-explicit-key"
    finally:
        if saved is None:
            os.environ.pop("JWT_SECRET", None)
        else:
            os.environ["JWT_SECRET"] = saved
        importlib.reload(h)


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
        except Exception as e:  # noqa: BLE001 -- surface unexpected errors as failures
            failed += 1
            print(f"FAIL  {t.__name__}: unexpected {type(e).__name__}: {e}")
    print(f"\n{len(tests) - failed}/{len(tests)} passed")
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
