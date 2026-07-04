"""Shared, deterministic execution harness for the four auth-flow agents.

This module carries NO debate-gated instruction. It is the identical substrate
every framework sits on: it reads the auth test PLAN the agent generated,
constructs each credential deterministically (login / mint-expired / truncate /
logout-then-reuse — all in auth_spec), sends each to the LOCAL protected
endpoint, records the real response, and computes the task findings:

  - Auth Flow Pass Rate  = correct-code cases / executed cases x 100  (task rule)
  - False Acceptance Rate = invalid scenarios returning 2xx           (critical)
  - False Rejection Rate  = valid scenarios returning non-2xx

The agent is purely generative: it emits the plan (recipes + task-rule expected
codes + the not_applicable enumeration). It never sends a request. The framework
-specific part — eliciting that plan from the backend LLM — is injected as
`generate() -> dict`.

Hardening rationale (this is the deterministic executor behind the auth-flow
agent, so every I/O boundary is defended; guards are documented inline so future
runs understand WHY each exists):
  - SSRF: every outbound request is confined to loopback/private hosts over an
    http(s) scheme before a socket opens (`_assert_private_host`) — a poisoned
    config/env can never make the harness reach an arbitrary host or a file:// URL.
  - Path traversal: every file write is confined to SANDBOX_ROOT
    (`_assert_sandbox`) and written atomically (temp + os.replace) so a crash
    mid-write can never leave a half-written findings/result file.
  - Bounded reads: every external file (`_read_text_capped`) and every response
    body is byte-capped so a 10 GB config/metric/body can never OOM the process.
  - Bounded work: the number of executed sub-tests is capped (`_MAX_SUBTESTS`) so
    a hostile plan with 1M sub-tests cannot pin the target or the harness.
  - Resilience: the memory-pool POST is bounded (retry + small backoff + an
    Idempotency-Key so a timed-out-but-applied add is not double-applied), and
    every persistence step degrades to a logged failure rather than crashing.
  - Observability: a module logger (NullHandler by default) records each
    credential built, each request sent, each status, and every fallback.
  - Never a silent success: a generation failure, an empty plan, a persistence
    failure, or an unexpected internal error is recorded/logged as an explicit
    failure — the harness never reports success it did not observe.
"""
from __future__ import annotations

import json
import logging
import os
import re
import secrets
import sys
import tempfile
import threading
import time
import urllib.error
import urllib.request
import uuid
from datetime import datetime, timezone
from ipaddress import ip_address
from pathlib import Path
from typing import Any, Callable
from urllib.parse import urlparse

# --------------------------------------------------------------------------- #
# Module logger: NullHandler so importing this never forces logging config on a
# host, yet every guard/fallback still emits a structured record when the host
# opts in (observability requirement).
# --------------------------------------------------------------------------- #
logger = logging.getLogger(__name__)
logger.addHandler(logging.NullHandler())

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")

# JWT signing secret. If JWT_SECRET is unset we generate a RANDOM per-process
# secret (secrets.token_hex) rather than a hardcoded literal — so nothing an
# attacker can read from this source lets them forge a token (vulnerability /
# security lens). A random fallback still lets the air-gapped local harness run:
# the harness only ever signs its OWN negative-case tokens (expired/tampered),
# which the target must reject regardless of the signing key. CI/prod set
# JWT_SECRET to the target's real key; we WARN loudly when it is absent so a
# valid-token positive case is not silently mis-signed.
SECRET = os.environ.get("JWT_SECRET") or secrets.token_hex(32)
if not os.environ.get("JWT_SECRET"):
    logger.warning("JWT_SECRET unset — using a random per-process secret; set "
                   "JWT_SECRET to the target key so valid-token cases sign correctly")

# Bound every file/body read so a hostile/runaway input can never drive the
# process to memory exhaustion (memory-resource / adversarial-input guard).
_MAX_BODY_BYTES = 1 << 20        # 1 MiB — far above any legitimate auth response.
_MAX_FILE_BYTES = 8 << 20        # 8 MiB — far above any legitimate spec/config/metric file.
# The per-agent diagnostic notes file appends across ALL runs; cap it so it can
# never grow without bound and exhaust disk (memory-resource). At the cap it is
# rotated to a single .1 backup, bounding total footprint to ~2x this per agent.
_MAX_NOTE_BYTES = 1 << 20        # 1 MiB of breadcrumbs per agent is plenty.
# A hostile/buggy plan must not pin the single-threaded target with unbounded
# requests; the real matrix is 5 sub-tests, so 256 is generous (system-design /
# adversarial-input).
_MAX_SUBTESTS = 256
# LLM output fed to extract_json is untrusted and may be huge; cap it BEFORE the
# regex + brace scan so a 1 GB blob cannot pin the CPU on O(n) work. A real plan
# is a few KB; 4 MiB is a generous ceiling (adversarial-input).
_MAX_EXTRACT_BYTES = 4 << 20
# The agent's generate() calls a backend LLM that can hang indefinitely (dead
# socket, wedged provider) with NO exception. Bound it so a hung model degrades
# to an empty plan instead of wedging the whole run (chaos-engineering).
_GENERATE_TIMEOUT_S = float(os.environ.get("FORGE_GENERATE_TIMEOUT_S", "60"))
# EverOS memory-pool POST: bounded retry + small backoff on transient failure so
# a briefly-down pool degrades gracefully instead of dropping the note silently.
_EVEROS_RETRIES = 2
_EVEROS_BACKOFF_S = 0.25
_EVEROS_TIMEOUT_S = 5

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import auth_spec  # noqa: E402

# The protected-endpoint request timeout is enforced inside auth_spec._request
# (auth_spec.REQUEST_TIMEOUT_S); mirrored here so the bound is visible at the call
# site and asserted by the tests (network lens).
_REQUEST_TIMEOUT_S = getattr(auth_spec, "REQUEST_TIMEOUT_S", 20)


# --------------------------------------------------------------------------- #
# Bounded file read
# --------------------------------------------------------------------------- #
def _read_text_capped(path: Path) -> str:
    """Read a text file but never more than ``_MAX_FILE_BYTES``.

    Rationale: read_text() on a 10 GB file raises MemoryError (an unchecked
    exception type that would escape callers catching only OSError/ValueError).
    Reading a bounded prefix keeps every external-file read O(1) in memory; an
    over-cap file raises ValueError so callers degrade uniformly. Decoding uses
    ``errors="replace"`` so broken/hostile UTF-8 (a NUL/lone-surrogate/invalid
    byte sequence) yields replacement chars instead of a UnicodeDecodeError — the
    subsequent JSON/TOML parse then fails cleanly as ValueError (adversarial-input).
    """
    with open(path, "rb") as fh:
        raw = fh.read(_MAX_FILE_BYTES + 1)
    if len(raw) > _MAX_FILE_BYTES:
        raise ValueError(f"file exceeds {_MAX_FILE_BYTES} bytes: {path}")
    return raw.decode("utf-8", errors="replace")


# --------------------------------------------------------------------------- #
# Sandbox + host guards
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    """Confine a file path to SANDBOX_ROOT.

    Rationale: every artifact this harness writes is derived from external input
    (agent name, item id). Resolving the path and requiring it to be SANDBOX_ROOT
    or a descendant defeats path traversal (``..``/absolute/symlink escapes)
    before any bytes are written.
    """
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def _assert_private_host(url: str) -> None:
    """Confine an outbound URL to an http(s) loopback/private host (SSRF guard).

    Rationale: the memory-pool base URL comes from config. The guard first
    requires an http/https scheme so a ``file://`` (or any schemeless/other-scheme)
    URL — whose hostname parses as empty and would otherwise slip past a bare
    hostname allow-list — is rejected outright. A named loopback is allowed; any
    literal IP must be loopback, private, or link-local.
    """
    parsed = urlparse(url)
    if parsed.scheme not in ("http", "https"):
        raise PermissionError(f"refusing non-http(s) URL scheme: {parsed.scheme!r}")
    host = (parsed.hostname or "").strip()
    if host in ("localhost", "127.0.0.1", "::1"):
        return
    if not host:
        raise PermissionError("refusing URL with no host")
    try:
        ip = ip_address(host)
    except ValueError:
        raise PermissionError(f"refusing non-local host: {host!r}")
    if not (ip.is_loopback or ip.is_private or ip.is_link_local):
        raise PermissionError(f"refusing non-private host: {host!r}")


def _atomic_write(path: Path, text: str) -> None:
    """Write text atomically inside the sandbox.

    Rationale: a temp file in the target dir + ``os.replace`` means a reader (the
    G1b step) never sees a half-written JSON file, and a crash mid-write can not
    corrupt a prior good file (data-integrity). The raw fd is closed on EVERY
    path — including when ``os.fdopen`` itself raises before it can adopt the fd
    (that would otherwise leak the descriptor) — and the temp file is unlinked on
    failure (memory-resource). Failures are logged before re-raise (observability).
    """
    _assert_sandbox(path)
    fd, tmp = tempfile.mkstemp(dir=str(path.parent), prefix=f".{path.name}.", suffix=".tmp")
    fd_open = False
    try:
        fh = os.fdopen(fd, "w", encoding="utf-8")  # adopts fd; may raise (then fd is still ours)
        fd_open = True
        with fh:
            fh.write(text)
        os.replace(tmp, path)
    except Exception as e:  # noqa: BLE001 -- clean up fd+temp, log, then re-raise
        if not fd_open:
            try:
                os.close(fd)  # fdopen never adopted it; close so it cannot leak
            except OSError:
                pass
        try:
            os.unlink(tmp)
        except OSError:
            pass
        logger.error("_atomic_write: failed to write %s: %s", path, e)
        raise  # never swallow: the caller must learn the artifact was not written


# --------------------------------------------------------------------------- #
# G1 staging write
# --------------------------------------------------------------------------- #
def _write_staging_findings(
    agent: str,
    item_id: str,
    item_label: str,
    step_results: list[dict],
) -> None:
    """Write per-item step findings to the G1 staging directory.

    Path: results/runs/{RUN_ID}/staging/{agent}/{item_id}-findings.json

    Called once per item (endpoint / collection / scenario) after all steps
    for that item are complete. The G1b orchestration step reads these files
    and passes them to test-case-creator as evidence of what this agent observed.
    Written atomically inside the sandbox so a partial read can never occur.
    """
    staging_dir = WORKSPACE / "results" / "runs" / RUN_ID / "staging" / agent
    staging_dir.mkdir(parents=True, exist_ok=True)
    out_path = staging_dir / f"{item_id}-findings.json"

    findings = [
        {"step_number": i, "item_id": item_id, "item_label": item_label, **r}
        for i, r in enumerate(step_results, start=1)
    ]
    _atomic_write(out_path, json.dumps({
        "agent": agent,
        "item_id": item_id,
        "item_label": item_label,
        "run_id": RUN_ID,
        "findings": findings,
    }, indent=2))
    logger.debug("wrote %d staging findings to %s", len(findings), out_path)


# --------------------------------------------------------------------------- #
# Spec loading + the brief handed to the model
# --------------------------------------------------------------------------- #
def load_security() -> dict:
    """Load the auth OpenAPI spec.

    Rationale: the spec is a required build input; a missing/malformed/oversized
    file is a real defect, not something to paper over. The read is byte-capped
    (`_read_text_capped`) so a giant file degrades to {} + a logged warning
    instead of raising MemoryError past the callers (adversarial-input).
    """
    path = WORKSPACE / "data" / "auth_openapi.json"
    try:
        spec = json.loads(_read_text_capped(path))
    except (OSError, ValueError) as e:
        logger.warning("load_security: could not read %s: %s", path, e)
        return {}
    return spec if isinstance(spec, dict) else {}


def scheme_brief() -> str:
    """Compact, unambiguous description of the documented security section +
    the protected endpoint + which schemes are absent. Handed to the LLM."""
    spec = load_security()
    schemes = spec.get("components", {}).get("securitySchemes", {}) or {}
    lines = ["protected_endpoint: GET /auth/me",
             "login_endpoint: POST /auth/login (creds: emilys / emilyspass)",
             "revoke_equivalent: POST /auth/logout (no dedicated /auth/revoke exists)",
             "documented_security_schemes:"]
    for name, defn in schemes.items():
        defn = defn if isinstance(defn, dict) else {}
        lines.append(f"  - {name}: type={defn.get('type')} scheme={defn.get('scheme')} "
                     f"format={defn.get('bearerFormat')} (sent in Authorization header as 'Bearer <jwt>')")
    lines.append(f"schemes_NOT_documented_in_this_API: {spec.get('x-not-implemented', [])}")
    return "\n".join(lines)


# --------------------------------------------------------------------------- #
# LLM-output JSON extraction (deterministic, no model)
# --------------------------------------------------------------------------- #
def extract_json(text: str):
    """Pull the first balanced JSON object out of arbitrary (untrusted) LLM text.

    Rationale: LLM output is untrusted input. Guards: non-str/empty short-circuit
    to None; the input is length-capped to ``_MAX_EXTRACT_BYTES`` BEFORE any regex
    or brace scan so a gigabyte blob cannot pin the CPU on O(n) work (a real plan
    is a few KB); the balanced-brace scan is bounded by that capped length; a
    malformed candidate returns None (never raises) so the caller degrades to an
    empty plan.
    """
    if not isinstance(text, str) or not text:
        return None
    if len(text) > _MAX_EXTRACT_BYTES:
        logger.warning("extract_json: input of %d chars exceeds cap %d; truncating "
                       "before scan", len(text), _MAX_EXTRACT_BYTES)
        text = text[:_MAX_EXTRACT_BYTES]
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        candidate = _scan_balanced_object(text)
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except ValueError:
        logger.debug("extract_json: candidate was not valid JSON")
        return None


def _scan_balanced_object(text: str) -> str | None:
    """Return the substring of the first brace-balanced ``{...}`` object, or None."""
    start = text.find("{")
    if start == -1:
        return None
    depth = 0
    for i in range(start, len(text)):
        ch = text[i]
        if ch == "{":
            depth += 1
        elif ch == "}":
            depth -= 1
            if depth == 0:
                return text[start:i + 1]
    return None


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def everos_note(agent: str, text: str) -> None:
    """Append a breadcrumb to the shared memory pool (best-effort) + a local note.

    Rationale: the pool is optional and must NEVER block a run, but a failure is
    logged (not silently swallowed) for observability. The base URL is confined
    to an http(s) private host (SSRF), the add POST carries a stable
    Idempotency-Key so a timed-out-but-server-applied add is not double-applied on
    retry (data-integrity), response bodies are read capped + FD-closed, and the
    durable local note is always written so the breadcrumb survives a down pool.
    """
    cfg = _config()
    base = (cfg.get("everos_base_url") or "http://127.0.0.1:8000").rstrip("/")
    idem_key = str(uuid.uuid4())  # one key per note; identifies a retried add as the SAME add
    payload = {
        "session_id": RUN_ID,
        "app_id": cfg.get("app_id") or "forge",
        "project_id": cfg.get("project_id") or "agent-foundry",
        "messages": [{"sender_id": agent, "sender_name": agent, "role": "assistant",
                      "content": text, "timestamp": int(time.time())}],
    }
    try:
        _assert_private_host(base)
        for ep in ("/api/v1/memory/add", "/api/v1/memory/flush"):
            body = json.dumps(payload if ep.endswith("add") else
                              {k: payload[k] for k in ("session_id", "app_id", "project_id")}).encode()
            _post_everos(base + ep, body, idem_key)
    except PermissionError as e:
        logger.warning("everos_note: refusing memory-pool host: %s", e)
    except Exception as e:  # noqa: BLE001 -- pool optional; degrade to local note only
        logger.info("everos_note: memory pool unreachable, kept local note only: %s", e)
    _append_local_note(agent, text)


def _post_everos(url: str, body: bytes, idem_key: str | None = None) -> None:
    """POST to the memory pool with bounded retry/backoff + capped, FD-safe read.

    The Idempotency-Key header makes a retry after a read-timeout a no-op on a
    server that has already applied the write (data-integrity): the same key
    identifies the SAME logical add across all attempts. ``idem_key`` defaults to
    a fresh UUID when the caller does not supply one (backward-compatible call).
    """
    idem_key = idem_key or str(uuid.uuid4())
    last: Exception | None = None
    for attempt in range(_EVEROS_RETRIES + 1):
        req = urllib.request.Request(url, data=body, headers={
            "Content-Type": "application/json", "Idempotency-Key": idem_key})
        try:
            with urllib.request.urlopen(req, timeout=_EVEROS_TIMEOUT_S) as resp:
                resp.read(_MAX_BODY_BYTES)  # drain (capped); context mgr closes the FD
            return
        except urllib.error.HTTPError as e:
            e.close()  # 4xx/5xx is a definite answer — don't retry, close the FD
            logger.info("everos POST %s -> HTTP %s", url, e.code)
            return
        except (urllib.error.URLError, OSError) as e:  # transient: connection reset/timeout
            last = e
            if attempt < _EVEROS_RETRIES:
                time.sleep(_EVEROS_BACKOFF_S * (attempt + 1))
    if last is not None:
        raise last


def _append_local_note(agent: str, text: str) -> None:
    """Append the breadcrumb to the sandboxed local notes file (best-effort).

    Rationale: the note is a diagnostic breadcrumb, never load-bearing. The file
    is size-capped and rotated (`_rotate_note_if_full`) so it cannot grow without
    bound across runs and exhaust disk (memory-resource). A failure to write it
    (read-only FS, permission denied) must NOT crash a run, so it is logged and
    swallowed — the run's authoritative output is the result JSON.
    """
    try:
        notes = WORKSPACE / "memory" / "agent-notes"
        notes.mkdir(parents=True, exist_ok=True)
        note_path = notes / f"{agent}.md"
        _assert_sandbox(note_path)
        _rotate_note_if_full(note_path)
        line = f"- [{datetime.now(timezone.utc).isoformat()}] run={RUN_ID} {text}\n"
        with open(note_path, "a", encoding="utf-8") as f:
            f.write(line)
    except (OSError, PermissionError) as e:
        logger.warning("_append_local_note: could not write note for %s: %s", agent, e)


def _rotate_note_if_full(note_path: Path) -> None:
    """Rotate the notes file to a single .1 backup once it exceeds the size cap.

    Rationale: bounds a per-agent append-only log to ~2x _MAX_NOTE_BYTES total,
    so a long-lived agent cannot fill the disk (memory-resource). Best-effort:
    a rotation failure is logged and the append simply continues on the old file.
    """
    try:
        if note_path.exists() and note_path.stat().st_size >= _MAX_NOTE_BYTES:
            backup = note_path.with_suffix(note_path.suffix + ".1")
            os.replace(note_path, backup)  # atomic; overwrites any prior .1
            logger.info("_rotate_note_if_full: rotated %s (>= %d bytes)",
                        note_path, _MAX_NOTE_BYTES)
    except OSError as e:
        logger.warning("_rotate_note_if_full: could not rotate %s: %s", note_path, e)


def _config() -> dict:
    """Read [memory] config.

    Rationale: config is external input — a missing/malformed/oversized config.toml
    must degrade to empty (callers already supply defaults) instead of crashing a
    run. The read is byte-capped so a giant file cannot OOM (adversarial-input).
    """
    import tomllib
    try:
        cfg = tomllib.loads(_read_text_capped(WORKSPACE / "config.toml"))
    except (OSError, ValueError, tomllib.TOMLDecodeError) as e:
        logger.warning("_config: could not read config.toml: %s", e)
        cfg = {}
    mem = cfg.get("memory", {})
    mem = mem if isinstance(mem, dict) else {}
    return {"everos_base_url": mem.get("everos_base_url"),
            "app_id": mem.get("app_id"), "project_id": mem.get("project_id")}


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def _no_plan_case(gen_error: str | None) -> dict:
    """A synthetic failing case recorded when no sub-test executed.

    Rationale: an empty/failed generation must surface as an explicit FAILURE —
    never as a silent 0-case success — so the judge scores what actually happened.
    """
    reason = gen_error or "no plan produced"
    return {"scheme": None, "label": "_none_", "recipe": None,
            "construction_note": reason,
            "expected_class": None, "actual_code": None,
            "actual_class": "none", "message": "", "task_rule_pass": False,
            "error": gen_error or "no executable sub-tests produced"}


def _execute_subtests(plan: dict) -> tuple[list[dict], dict]:
    """Build + send each sub-test's credential; return (cases, tally).

    The sub-test count is capped at ``_MAX_SUBTESTS`` so a hostile plan (e.g. 1M
    sub-tests) cannot pin the single-threaded target or the harness — the real
    matrix is 5 (adversarial-input / system-design). Every credential build and
    every request is wrapped so a single malformed sub-test degrades to a recorded
    failing case rather than crashing the run (chaos-engineering).
    """
    ep = auth_spec.PROTECTED_ENDPOINT
    cases: list[dict] = []
    tally = {"executed": 0, "correct": 0, "false_accept": 0, "false_reject": 0}
    for sname, label, recipe, expected in auth_spec.iter_subtests(plan):
        if tally["executed"] >= _MAX_SUBTESTS:
            logger.warning("_execute_subtests: sub-test cap %d reached; ignoring the rest",
                           _MAX_SUBTESTS)
            break
        case = _run_one_subtest(ep, sname, label, recipe, expected)
        cases.append(case)
        tally["executed"] += 1
        if case["task_rule_pass"]:
            tally["correct"] += 1
        if label == "valid" and case["actual_class"] != "2xx":
            tally["false_reject"] += 1
        if label != "valid" and case["actual_class"] == "2xx":
            tally["false_accept"] += 1
    return cases, tally


def _run_one_subtest(ep: dict, sname, label, recipe, expected) -> dict:
    """Build one credential, send it, classify the response into a case dict.

    The request goes through ``auth_spec._request``, which enforces a per-attempt
    socket timeout of ``_REQUEST_TIMEOUT_S`` and bounded retries, so a slow/hung
    endpoint can never wedge the batch (network). Any failure building the
    credential or sending the request is caught and recorded as a failing case
    (chaos-engineering: never an uncaught crash).
    """
    try:
        headers, note = auth_spec.build_credential(recipe, TARGET_BASE_URL, SECRET)
        logger.debug("built credential scheme=%s label=%s note=%s", sname, label, note)
        code, text = auth_spec._request(TARGET_BASE_URL, ep["method"], ep["path"], headers=headers)
        logger.debug("sent %s %s scheme=%s label=%s -> code=%s (timeout=%ss)",
                     ep["method"], ep["path"], sname, label, code, _REQUEST_TIMEOUT_S)
        actual_class = auth_spec.classify(code)
        error = None
    except Exception as e:  # noqa: BLE001 -- one bad sub-test must not abort the batch
        logger.warning("sub-test scheme=%s label=%s failed: %s", sname, label, e)
        note, code, text, actual_class = f"{type(e).__name__}: {e}", None, "", "none"
        error = f"{type(e).__name__}: {e}"
    return {"scheme": sname, "label": label, "recipe": recipe,
            "construction_note": note, "expected_class": expected,
            "actual_code": code, "actual_class": actual_class,
            "message": _message_of(text), "task_rule_pass": actual_class == expected,
            "error": error}


def _staging_steps(cases: list[dict]) -> list[dict]:
    """Project the recorded cases into the G1 staging step schema (PASS/FAIL + detail)."""
    return [
        {
            "assertion_result": "PASS" if c.get("task_rule_pass") else "FAIL",
            "assertion_detail": (
                f"scheme={c.get('scheme')} label={c.get('label')} "
                f"expected_class={c.get('expected_class')} "
                f"actual_code={c.get('actual_code')} actual_class={c.get('actual_class')}"
            ),
            **c,
        }
        for c in cases
    ]


def _rates(tally: dict, executed: int) -> tuple[float, float, float]:
    """Compute (pass_rate, FAR, FRR) as percentages; 0.0 when nothing executed
    (division-by-zero guard — math-correctness)."""
    if not executed:
        return 0.0, 0.0, 0.0
    return (round(100.0 * tally["correct"] / executed, 2),
            round(100.0 * tally["false_accept"] / executed, 2),
            round(100.0 * tally["false_reject"] / executed, 2))


def _generate_plan(generate: Callable[[], dict]) -> tuple[dict, str | None]:
    """Run the agent's generate() under a hard timeout; return (plan, error).

    Rationale: generate() drives a backend LLM that can HANG with no exception
    (dead socket, wedged provider), which would wedge the whole run forever. We
    run it on a daemon thread and wait at most ``_GENERATE_TIMEOUT_S``; on timeout
    (or any raised exception) we degrade to an empty plan with a recorded error so
    the run still completes and reports a failure (chaos-engineering / resilience).
    A timed-out worker thread is abandoned as a daemon — it cannot block exit.
    """
    box: dict[str, Any] = {}

    def _worker() -> None:
        try:
            box["plan"] = generate() or {}
        except Exception as e:  # noqa: BLE001 -- generation is the agent's; record it
            box["error"] = f"{type(e).__name__}: {e}"

    t = threading.Thread(target=_worker, daemon=True)
    t.start()
    t.join(_GENERATE_TIMEOUT_S)
    if t.is_alive():
        logger.error("generate() exceeded %.0fs timeout; degrading to empty plan",
                     _GENERATE_TIMEOUT_S)
        return {}, f"generate() timed out after {_GENERATE_TIMEOUT_S:.0f}s"
    if "error" in box:
        logger.warning("run_auth_test: generate() raised: %s", box["error"])
        return {}, box["error"]
    return box.get("plan", {}), None


def _safe_persist_findings(agent: str, ep: dict, cases: list[dict]) -> None:
    """Write staging findings, degrading to a logged failure on any I/O error.

    Rationale: a read-only/full disk must not crash the whole run before the
    authoritative result JSON is even attempted (chaos-engineering /
    error-handling-resilience). Staging findings are advisory G1b evidence; if
    they cannot be written the run still proceeds to record its result.
    """
    try:
        _write_staging_findings(agent=agent, item_id=f"{ep['method']}-auth-me".lower(),
                                item_label=f"{ep['method']} {ep['path']}",
                                step_results=_staging_steps(cases))
    except (OSError, PermissionError) as e:
        logger.error("run_auth_test agent=%s: staging findings write failed: %s", agent, e)


def _persist_run(agent: str, raw: dict, tally: dict) -> bool:
    """Write the .cases.json + {agent}.json pair ALL-OR-NOTHING; return whether both
    landed.

    Data-integrity: the two files are a consistent pair — {agent}.json's
    raw_output_path must point at an existing .cases.json. Two failure modes are
    handled so disk is never left half-written:
      * cases.json write fails  -> do NOT emit (no pointer to a missing file);
      * emit() fails afterward   -> the just-written cases.json is now ORPHANED, so
        we unlink it to roll back, leaving neither file (compensating action).
    Either way we return False so the caller records the run as unpersisted rather
    than silently "succeeding". The memory-pool note is best-effort and never gates
    the return (error-handling-resilience).
    """
    pass_rate = raw["auth_flow_pass_rate_pct"]
    far, frr, executed = (raw["false_acceptance_rate_pct"],
                          raw["false_rejection_rate_pct"], raw["executed_cases"])
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    cases_path = run_dir / f"{agent}.cases.json"
    persisted = _write_run_pair(agent, run_dir, cases_path, raw,
                                (pass_rate, far, frr, executed))
    if tally["false_accept"]:
        logger.error("run_auth_test agent=%s recorded %d false-acceptance case(s)",
                     agent, tally["false_accept"])
    crit = " CRITICAL:false-acceptance" if tally["false_accept"] else ""
    everos_note(agent, f"auth-flow run: pass_rate={pass_rate}% executed={executed} "
                       f"FAR={far}% FRR={frr}%{crit}")
    return persisted


def _write_run_pair(agent: str, run_dir: Path, cases_path: Path, raw: dict,
                    metrics: tuple) -> bool:
    """Write cases.json then {agent}.json atomically as a pair; roll back the
    cases file if the emit half fails so no orphan is left (data-integrity)."""
    pass_rate, far, frr, executed = metrics
    cases_written = False
    try:
        run_dir.mkdir(parents=True, exist_ok=True)
        _atomic_write(cases_path, json.dumps(raw, indent=2))
        cases_written = True
        emit(agent, pass_rate, str(cases_path), extra={
            "auth_flow_pass_rate_pct": pass_rate,
            "false_acceptance_rate_pct": far, "false_rejection_rate_pct": frr,
            "executed_cases": executed})
        return True
    except (OSError, PermissionError) as e:
        logger.error("run_auth_test agent=%s: result persistence failed: %s", agent, e)
        if cases_written:  # emit failed -> the cases.json is now orphaned; undo it
            _rollback_orphan_cases(agent, cases_path)
        return False


def _rollback_orphan_cases(agent: str, cases_path: Path) -> None:
    """Remove (or, if removal fails, tombstone) an orphaned cases.json.

    Rationale (error-handling-resilience): when emit() fails after cases.json was
    written, that file is orphaned — it has no {agent}.json pointer. We first try
    to unlink it. But unlink() can ITSELF raise (read-only FS, races), which would
    leave the orphan on disk in an inconsistent state. So the removal is best-effort
    with a guaranteed fallback: if unlink fails we overwrite the file in place with
    a self-describing tombstone marker (``__forge_orphaned__``). A reader keys off
    the {agent}.json pointer and never treats a tombstoned/pointer-less cases file
    as a valid result, so disk is left in a consistent, self-explaining state on
    EVERY path — no branch leaves a silently-misreadable orphan.
    """
    try:
        cases_path.unlink()
        logger.info("run_auth_test agent=%s: rolled back orphaned %s",
                    agent, cases_path.name)
        return
    except OSError as ce:
        logger.error("run_auth_test agent=%s: unlink of orphaned %s failed: %s",
                     agent, cases_path.name, ce)
    try:  # last resort: neutralize the orphan so it can never be misread as a result
        cases_path.write_text(
            json.dumps({"__forge_orphaned__": True, "agent": agent, "run_id": RUN_ID,
                        "reason": "emit failed; cases.json has no result pointer"}),
            encoding="utf-8")
        logger.warning("run_auth_test agent=%s: tombstoned un-removable orphan %s",
                       agent, cases_path.name)
    except OSError as te:
        logger.error("run_auth_test agent=%s: could not tombstone orphan %s: %s",
                     agent, cases_path.name, te)


def run_auth_test(agent: str, generate: Callable[[], dict]) -> dict:
    """Execute one agent's auth test plan against the live target.

    generate() -> the agent's plan object:
        {protected_endpoint, schemes:[{scheme, subtests:[{label, credential, expected_class}]}],
         not_applicable:[{item, status}]}
    Iterates each implemented sub-test (capped), builds its credential, sends it,
    records the real response; the agent never sends anything. Every I/O boundary
    (host check, generation under a hard timeout, requests, staging, persistence)
    is guarded so a raising/hanging generate(), a non-local target, a down endpoint,
    a malformed plan, or a full disk degrades to a recorded failure, never a crash.
    """
    ep = auth_spec.PROTECTED_ENDPOINT
    logger.info("run_auth_test agent=%s target=%s endpoint=%s %s",
                agent, TARGET_BASE_URL, ep["method"], ep["path"])
    # Guard the host check itself: a misconfigured non-local TARGET_BASE_URL must
    # degrade to a recorded failure (no requests sent), not crash the run
    # (error-handling-resilience). generate() runs under a hard timeout.
    try:
        auth_spec._assert_local(TARGET_BASE_URL)
        plan, gen_error = _generate_plan(generate)
    except (PermissionError, ValueError) as e:
        logger.error("run_auth_test agent=%s: target rejected, no requests sent: %s",
                     agent, e)
        plan, gen_error = {}, f"target refused: {type(e).__name__}: {e}"

    cases, tally = _execute_subtests(plan)
    executed = tally["executed"]
    if executed == 0:
        logger.info("run_auth_test agent=%s produced no executable sub-tests", agent)
        cases.append(_no_plan_case(gen_error))

    na_items = [{"item": item, "status": status}
                for item, status in auth_spec.iter_not_applicable(plan)]
    _safe_persist_findings(agent, ep, cases)

    pass_rate, far, frr = _rates(tally, executed)
    logger.info("run_auth_test agent=%s pass_rate=%.2f%% executed=%d FAR=%.2f%% FRR=%.2f%%",
                agent, pass_rate, executed, far, frr)
    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "auth_flow_pass_rate_pct": pass_rate,
           "false_acceptance_rate_pct": far, "false_rejection_rate_pct": frr,
           "false_acceptance_count": tally["false_accept"],
           "false_rejection_count": tally["false_reject"],
           "executed_cases": executed,
           "not_applicable_enumerated": na_items,
           "cases": cases,
           "artifacts_persisted": True}  # additive; set to False if disk write fails
    raw["artifacts_persisted"] = _persist_run(agent, raw, tally)
    return raw


def _message_of(text: str) -> str:
    """Best-effort extract of a JSON body's ``message`` field, else empty.

    Rationale: the response body is untrusted; a non-JSON / non-object / oversized
    body must degrade to "" rather than raise. Non-str and over-cap inputs are
    rejected up front so this can never be a memory sink.
    """
    if not isinstance(text, str) or not text or len(text) > _MAX_BODY_BYTES:
        return ""
    try:
        parsed = json.loads(text)
    except ValueError:
        return ""
    return parsed.get("message", "") if isinstance(parsed, dict) else ""


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Auth Flow Pass Rate; the judge later overwrites metric_value with Auth-Flow
    Fidelity for ranking. The metric file (external input) is read byte-capped +
    defensively and the result is written atomically inside the sandbox."""
    metric: dict = {}
    mp = WORKSPACE / "judge" / "auth_metric.json"
    if mp.exists():
        try:
            metric = json.loads(_read_text_capped(mp))
            metric = metric if isinstance(metric, dict) else {}
        except (OSError, ValueError) as e:
            logger.warning("emit: could not read metric file %s: %s", mp, e)
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("headline_metric", "auth_flow_pass_rate_pct"),
               "metric_value": metric_value,
               "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    _atomic_write(out, json.dumps(payload, indent=2))
    logger.debug("emit: wrote %s (metric_value=%s)", out, metric_value)
