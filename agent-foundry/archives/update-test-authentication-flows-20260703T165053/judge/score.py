#!/usr/bin/env python3
# Standard compliance: this judge operates under agent-foundry/references/agent-authoring-standard.md
# (Articles G1-G11); all code here is reviewed by every agent in agents/code-review/ at >=85. See references/memory-everos.md.
"""Judge scorer (auth-flow) — fidelity layer.

The agents emit blind test plans (they never see the gold). This step reads each
agent's executed cases for a run, compares them to data/auth_gold.json under the
contract in judge/auth_metric.json, computes Auth-Flow Fidelity, and writes that
number back as each agent's metric_value. Then scripts/judge_score.py ranks and
updates the leaderboard.

Metric — Auth-Flow Fidelity (UNCHANGED scale/meaning):
    fidelity = 100 * matched / denominator          (a percentage in [0.0, 100.0])
where
    denominator = (# executed gold cases) + (# not_applicable gold items), and
    matched     = (executed cases whose agent-observed actual_class equals gold)
                + (not_applicable items the agent enumerated as needing build/test).
A perfect plan scores 100.0; each unmatched gold item lowers the score by
100/denominator. Missing/malformed agent output contributes 0 matches (never a
crash, never a false match). The number's scale and meaning are preserved exactly
so the golden tournament baseline does not move.

Usage:
    python judge/api-tester/test-authentication-flows/score.py --workspace . --run-id <id>
"""
from __future__ import annotations

import argparse
import contextlib
import contextvars
import json
import logging
import os
import re
import time
import uuid
from pathlib import Path
from typing import Any, Iterator, NamedTuple, Optional

log = logging.getLogger(__name__)
log.addHandler(logging.NullHandler())

# observability: a run-level correlation id, threaded into EVERY log record via a filter
# (below) so one run — all its agents and any concurrent judges — is greppable end to end.
# A ContextVar (not a parameter) keeps it out of every function signature, so the public
# API (_load / gold_truth / agent_observed / ...) is preserved exactly.
_CORRELATION_ID: contextvars.ContextVar[str] = contextvars.ContextVar("correlation_id", default="-")


class _CorrelationFilter(logging.Filter):
    """Prefix each record's message with the current correlation id.

    Rewriting the message text (not just adding a record attribute) makes the id visible
    regardless of the downstream handler/formatter — it survives even a bare NullHandler,
    so the id is always present when the record is grepped."""

    def filter(self, record: logging.LogRecord) -> bool:
        cid = _CORRELATION_ID.get()
        if not str(record.msg).startswith("[cid="):   # idempotent: never double-prefix
            record.msg = f"[cid={cid}] {record.msg}"
        return True


log.addFilter(_CorrelationFilter())

# --- bounds (chaos / adversarial / device-stack) ---------------------------
# A judge must survive malformed, partial, or hostile agent output. These caps
# bound work and memory so a pathological run degrades gracefully instead of
# exhausting the process.
_MAX_JSON_BYTES = 32 * 1024 * 1024          # 32 MiB: largest doc we will parse
_MAX_RESULT_FILES = 100_000                 # cap files scanned per run dir
_MAX_CASES = 1_000_000                       # cap cases iterated per doc
# actual_class / label values that mean "the agent did not really observe this".
# Kept as ONE table (DRY) so gold and observed sides filter identically — the
# logic-error/data-integrity fix depends on symmetric filtering.
_NON_OBSERVED_LABELS = frozenset({None, "", "_none_", "none"})
_NON_OBSERVED_CLASSES = frozenset({None, "", "none"})
_METRIC_NAME = "auth_flow_fidelity"
# A run-id names a single results subdirectory. It must be a plain segment: no
# path separators, no traversal, no leading dot. This is the primary traversal
# guard (security/vulnerability lens).
_RUN_ID_RE = re.compile(r"^[A-Za-z0-9._-]+$")
# Bounded, best-effort wait for a contended result-file lock. A judge backgrounded
# (SIGSTOP) mid-write must never make a waiter block forever (device-stack); we poll
# with LOCK_NB up to this budget, then proceed unlocked rather than hang.
_LOCK_WAIT_S = 10.0
_LOCK_POLL_S = 0.05


class _Row(NamedTuple):
    """One leaderboard row — a self-documenting record so the report is not a bare,
    positionally-unpacked 8-tuple (maintainability). Field order == print order."""
    agent: str
    fidelity: float
    exec_matches: int
    exec_total: int
    na_matches: int
    na_total: int
    pass_rate: Any
    far: Any


def _load(p: Path, default: Any = None) -> Any:
    """Read + parse JSON from ``p``, returning ``default`` on any failure.

    Bounded (device-stack/chaos): refuses files larger than ``_MAX_JSON_BYTES``
    before reading so a huge/adversarial file cannot exhaust memory. Even under the
    byte cap, a low-RAM host can still hit MemoryError while decoding or parsing; that
    (and RecursionError on pathological nesting) is caught so the judge degrades to
    ``default`` instead of crashing. Every failure mode (missing file, oversize, bad
    encoding, invalid JSON, out-of-memory, unreadable) is logged (observability) with
    the reason and returns ``default`` — the caller always gets a usable value and
    never an exception."""
    try:
        size = p.stat().st_size
    except OSError as exc:
        log.warning("json load: cannot stat %s (%s); using default", p, exc.__class__.__name__)
        return default
    if size > _MAX_JSON_BYTES:
        log.error("json load: %s is %d bytes (> %d cap); using default", p, size, _MAX_JSON_BYTES)
        return default
    try:
        text = p.read_text(encoding="utf-8")
    except (OSError, ValueError) as exc:
        log.warning("json load: cannot read %s (%s); using default", p, exc.__class__.__name__)
        return default
    except MemoryError:
        # device-stack: read_text/decode can exhaust RAM on a constrained host even within
        # the byte cap. Degrade gracefully rather than crashing the whole run.
        log.error("json load: out of memory reading %s; using default", p)
        return default
    try:
        return json.loads(text)
    except (json.JSONDecodeError, ValueError) as exc:
        log.error("json load: %s is not valid JSON (%s); using default", p, exc)
        return default
    except RecursionError:
        # Adversarial: pathologically nested JSON ({"a":{"b":{...}}} x thousands) blows
        # the C-stack in json.loads before any size cap can catch it. Treat as unparseable
        # rather than letting the RecursionError crash the whole judge.
        log.error("json load: %s exceeds JSON nesting depth limit; using default", p)
        return default
    except MemoryError:
        # device-stack: parsing a large-but-under-cap document can still exhaust memory on
        # a low-RAM host (json builds the whole object tree). Degrade, don't crash.
        log.error("json load: out of memory parsing %s; using default", p)
        return default


def _dict_rows(doc: Any, key: str) -> list[dict]:
    """Return ``doc[key]`` as a bounded list of dict rows, tolerating garbage.

    Named for what it RETURNS (a list of dict rows), not an iterator — the ``_iter_``
    prefix would wrongly imply a lazy generator (maintainability).

    Adversarial-input hardening: ``doc`` may be a non-dict, ``doc[key]`` may be a
    non-list (e.g. a string, which would otherwise be iterated char-by-char), and
    elements may be non-dicts. Non-dict rows are dropped (logged) instead of
    crashing on attribute/index access. The list is truncated at ``_MAX_CASES``."""
    if not isinstance(doc, dict):
        log.warning("cases: document is %s, not an object; treating as empty", type(doc).__name__)
        return []
    raw = doc.get(key)
    if not isinstance(raw, list):
        if raw is not None:
            log.warning("cases: %r is %s, not a list; treating as empty", key, type(raw).__name__)
        return []
    if len(raw) > _MAX_CASES:
        log.error("cases: %r has %d rows (> %d cap); truncating", key, len(raw), _MAX_CASES)
        raw = raw[:_MAX_CASES]
    rows = [r for r in raw if isinstance(r, dict)]
    dropped = len(raw) - len(rows)
    if dropped:
        log.warning("cases: dropped %d non-object row(s) under %r", dropped, key)
    return rows


def _observed_cases(cases_doc: Any) -> dict:
    """Return {(scheme,label)->actual_class} for genuinely-observed rows in ``cases_doc``.

    DRY (maintainability): this is the single canonical case-admission filter used by
    BOTH gold_truth() and agent_observed(), so the two sides can never drift out of
    sync. A row is admitted only when it has a real ``scheme`` and neither its label
    nor its actual_class is a non-observed placeholder — the invariant the whole
    metric's correctness depends on."""
    out: dict[tuple, Any] = {}
    for c in _dict_rows(cases_doc, "cases"):
        scheme, label, actual = c.get("scheme"), c.get("label"), c.get("actual_class")
        if scheme is None or label in _NON_OBSERVED_LABELS or actual in _NON_OBSERVED_CLASSES:
            continue
        out[(scheme, label)] = actual
    return out


def gold_truth(ws: Path) -> tuple[dict, set]:
    """Return (executed truth {(scheme,label)->actual_class}, not_applicable item set).

    Data-integrity: only cases with a usable (scheme, label) key and a genuinely
    observed actual_class are admitted to the executed-truth map, applying the SAME
    non-observed filter used on the agent side (via _observed_cases) so the two are
    comparable (fixes the logic-error where gold kept 'none' cases the observed side
    dropped)."""
    gold = _load(ws / "data" / "auth_gold.json", {"cases": [], "summary": {}})
    exec_truth = _observed_cases(gold)
    summary = gold.get("summary") if isinstance(gold, dict) else None
    na_raw = summary.get("not_applicable", []) if isinstance(summary, dict) else []
    na_items = {x["item"] for x in na_raw if isinstance(x, dict) and "item" in x}
    if not exec_truth and not na_items:
        # observability: an absent/empty gold makes EVERY agent score 0% — a silent,
        # systemic failure. Log at ERROR so it is impossible to miss when triaging a run
        # where all fidelities collapsed to zero.
        log.error("gold: no truth loaded from %s — all agents will score 0%%",
                  ws / "data" / "auth_gold.json")
    else:
        log.info("gold: %d executed truth cases, %d not_applicable items", len(exec_truth), len(na_items))
    return exec_truth, na_items


def agent_observed(cases_doc: Any) -> tuple[dict, set]:
    """Return (observed {(scheme,label)->actual_class}, enumerated not_applicable set).

    A row is admitted only when it has a real (scheme, label) and a genuinely
    observed actual_class — the identical non-observed filter used on the gold side
    (both call _observed_cases), so 'the agent never reported it' can never
    masquerade as a match. Rows missing ``scheme`` are dropped (they cannot form a
    comparable key)."""
    obs = _observed_cases(cases_doc)
    na = {
        x.get("item")
        for x in _dict_rows(cases_doc, "not_applicable_enumerated")
        if x.get("status") == "needs_to_be_built_and_tested" and x.get("item") is not None
    }
    return obs, na


def _score_one(exec_truth: dict, na_truth: set, cases_doc: Any) -> tuple[float, int, int, int]:
    """Score one agent's cases doc against the gold. Returns (fidelity, matches, exec_matches, na_matches).

    math-correctness: a case counts as an executed match ONLY when the agent's
    observed map contains the key AND its value equals the gold value — using an
    explicit sentinel so an absent observation can never equal an absent gold value
    (the None==None false-match bug). Deterministic: pure function of its inputs."""
    obs_exec, obs_na = agent_observed(cases_doc)
    _MISSING = object()
    exec_matches = sum(1 for k, v in exec_truth.items() if obs_exec.get(k, _MISSING) == v)
    na_matches = sum(1 for item in na_truth if item in obs_na)
    matches = exec_matches + na_matches
    denom = len(exec_truth) + len(na_truth)
    fidelity = round(100.0 * matches / denom, 2) if denom else 0.0
    return fidelity, matches, exec_matches, na_matches


def _validate_run_id(run_id: str) -> str:
    """Return ``run_id`` if it is a safe single path segment, else raise ValueError.

    security/vulnerability (path traversal): the run-id flows into a filesystem
    path; a value like '../../etc' would escape the results tree. We accept only a
    plain [A-Za-z0-9._-]+ segment and explicitly reject '..' and separators."""
    if not run_id or not _RUN_ID_RE.match(run_id) or run_id in (".", ".."):
        raise ValueError(f"unsafe run-id {run_id!r}: expected a plain [A-Za-z0-9._-] segment")
    return run_id


def _confined_cases_path(raw_output_path: str, ws: Path) -> Optional[Path]:
    """Resolve an agent-declared cases path, confined to the workspace, or None.

    security/vulnerability (arbitrary file read): ``raw_output_path`` comes from
    attacker-influenceable metadata JSON. We resolve it and require it to live
    UNDER the resolved workspace; anything outside (traversal, absolute /etc/...) is
    refused (logged) and treated as 'no cases'. Empty/garbage input -> None.

    data-integrity (determinism): a RELATIVE raw_output_path is anchored to the
    (already-absolute) workspace, NOT the process CWD, so the same metadata resolves
    to the same file and yields the same score no matter which directory the judge is
    launched from."""
    if not isinstance(raw_output_path, str) or not raw_output_path.strip():
        return None
    try:
        raw = Path(raw_output_path).expanduser()
        base = raw if raw.is_absolute() else (ws / raw)
        candidate = base.resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        log.warning("raw_output_path %r is not a valid path (%s); ignoring", raw_output_path, exc.__class__.__name__)
        return None
    try:
        candidate.relative_to(ws)
    except ValueError:
        log.error("raw_output_path %r escapes workspace %s; refusing to read", str(candidate), ws)
        return None
    return candidate


def _try_acquire(lock_path: Path) -> Optional[int]:
    """Poll to create ``lock_path`` exclusively up to _LOCK_WAIT_S; return the held fd or None.

    data-integrity: uses O_CREAT|O_EXCL, whose create-if-absent check is atomic on EVERY
    OS (POSIX and Windows) — unlike fcntl.flock, which was unavailable on Windows and left
    the read-modify-write UNGUARDED there, so two judges could lose an update. This gives
    real cross-platform mutual exclusion. device-stack: the wait is BOUNDED (non-blocking
    poll), so a holder that is backgrounded/stopped mid-write never wedges a waiter — on
    timeout we log a distinct lock-timeout event and return None (best-effort, proceed)."""
    deadline = time.monotonic() + _LOCK_WAIT_S
    while True:
        try:
            return os.open(str(lock_path), os.O_CREAT | os.O_EXCL | os.O_RDWR, 0o600)
        except FileExistsError:
            if time.monotonic() >= deadline:
                log.warning("lock-timeout: %s held > %.0fs; proceeding UNLOCKED (holder may be stopped) "
                            "— concurrent write may be lost", lock_path, _LOCK_WAIT_S)
                return None
            time.sleep(_LOCK_POLL_S)
        except OSError as exc:
            log.warning("could not create lock %s (%s); proceeding without it", lock_path, exc.__class__.__name__)
            return None


@contextlib.contextmanager
def _result_lock(path: Path) -> Iterator[bool]:
    """Hold an exclusive lock for the read-modify-write of one result file, cross-platform.

    concurrency/data-integrity: two judges scoring the same run would otherwise race — A
    reads, B reads, A writes, B's os.replace() silently clobbers A's metric_value (lost
    update). An O_EXCL sidecar ``.lock`` serialises the whole read→compute→write on ALL
    platforms, so the second judge waits and re-runs on A's persisted state instead of
    overwriting it. Yields True if the lock was actually held, False if it could not be
    acquired within the bounded wait — the caller still proceeds (best-effort). The lock
    file is always removed and the fd closed, even on error (error-handling-resilience)."""
    lock_path = path.with_name(f"{path.name}.lock")
    fd = _try_acquire(lock_path)
    try:
        yield fd is not None
    finally:
        if fd is not None:
            with contextlib.suppress(OSError):
                os.close(fd)
            with contextlib.suppress(OSError):
                lock_path.unlink()


def _atomic_write_json(path: Path, payload: dict) -> bool:
    """Write ``payload`` as JSON to ``path`` atomically; return success.

    concurrency/data-integrity: write to a unique temp file in the same directory
    then os.replace() — an atomic rename — so a concurrent judge or a mid-write
    fault (chaos) never leaves a torn/partial metadata file. Any I/O failure is
    logged and returns False instead of raising, so one unwritable file cannot
    abort scoring of the rest (error-handling-resilience)."""
    tmp = path.with_name(f"{path.name}.{os.getpid()}.tmp")
    try:
        tmp.write_text(json.dumps(payload, indent=2), encoding="utf-8")
        os.replace(tmp, path)
        return True
    except OSError as exc:
        log.error("could not write metric back to %s (%s)", path, exc.__class__.__name__)
        try:
            tmp.unlink(missing_ok=True)
        except OSError:
            log.debug("temp cleanup for %s failed; leaving orphan", tmp)
        return False


def _result_files(run_dir: Path) -> list[Path]:
    """Return the run's metric JSON files, sorted, bounded, excluding *.cases.json.

    device-stack: iterate the directory lazily and stop after ``_MAX_RESULT_FILES``
    so a directory with millions of files cannot exhaust memory; the bounded subset
    is then sorted for deterministic, reproducible ordering (math/logic determinism)."""
    picked: list[Path] = []
    try:
        # The for-loop itself (not just iterdir()) can raise OSError if another process
        # deletes the directory or revokes permission mid-scan (device-stack/chaos):
        # a lazy scandir advances on each __next__. Guard the whole walk, not just setup.
        for entry in run_dir.iterdir():
            name = entry.name
            if not name.endswith(".json") or name.endswith(".cases.json"):
                continue
            picked.append(entry)
            if len(picked) >= _MAX_RESULT_FILES:
                log.error("run dir %s exceeds %d result files; truncating", run_dir, _MAX_RESULT_FILES)
                break
    except OSError as exc:
        log.error("run dir %s became unreadable mid-scan (%s); scoring %d file(s) collected so far",
                  run_dir, exc.__class__.__name__, len(picked))
    return sorted(picked)


def _metric_fields(meta: dict, fidelity: float, matches: int,
                   denom: int, exec_matches: int, na_matches: int) -> dict:
    """Return an immutable copy of ``meta`` with the metric fields set (never mutates meta)."""
    return {
        **meta,
        "metric_name": _METRIC_NAME,
        "metric_value": fidelity,
        "fidelity_matches": matches,
        "fidelity_denominator": denom,
        "exec_matches": exec_matches,
        "na_matches": na_matches,
    }


def _process_file(jf: Path, exec_truth: dict, na_truth: set, ws: Path) -> Optional[_Row]:
    """Score one result file and persist the metric; return a print row or None.

    The whole read-modify-write is held under _result_lock so concurrent judges
    cannot lose an update. Every boundary (load, confine, write) is guarded so a
    single bad file degrades to a skip, never a crash. error-handling-resilience:
    if the metric cannot be PERSISTED, the row is DROPPED (returns None) so the
    printed leaderboard never reports a score that was not written to disk."""
    with _result_lock(jf):
        meta = _load(jf, {})
        if not isinstance(meta, dict):
            log.error("result %s did not parse to an object; skipping", jf.name)
            return None
        agent = meta.get("agent") or jf.stem
        cases_path = _confined_cases_path(meta.get("raw_output_path", ""), ws)
        if cases_path is None:
            # observability: make the empty-cases fallback explicit — otherwise a missing/
            # invalid/escaped raw_output_path silently scores the agent 0% with no trace of why.
            log.warning("agent=%s has no usable raw_output_path (%r); scoring against empty cases",
                        agent, meta.get("raw_output_path"))
            cases_doc: Any = {"cases": []}
        else:
            cases_doc = _load(cases_path, {"cases": []})

        fidelity, matches, exec_matches, na_matches = _score_one(exec_truth, na_truth, cases_doc)
        denom = len(exec_truth) + len(na_truth)
        log.info("scored agent=%s fidelity=%.2f matches=%d/%d (exec=%d/%d na=%d/%d)",
                 agent, fidelity, matches, denom, exec_matches, len(exec_truth), na_matches, len(na_truth))

        if not _atomic_write_json(jf, _metric_fields(meta, fidelity, matches, denom, exec_matches, na_matches)):
            log.error("agent=%s scored fidelity=%.2f but metric was NOT persisted; dropping from report",
                      agent, fidelity)
            return None
    pass_rate = cases_doc.get("auth_flow_pass_rate_pct") if isinstance(cases_doc, dict) else None
    far = cases_doc.get("false_acceptance_rate_pct") if isinstance(cases_doc, dict) else None
    return _Row(agent, fidelity, exec_matches, len(exec_truth), na_matches, len(na_truth), pass_rate, far)


def _print_report(rows: list[_Row], exec_n: int, na_n: int, denom: int) -> None:
    """Print the deterministic leaderboard (sorted by fidelity desc, then agent).

    Reads _Row by NAME so the columns can't drift from the data (maintainability)."""
    ordered = sorted(rows, key=lambda r: (-r.fidelity, r.agent))
    print(f"Auth-Flow Fidelity (denominator = {denom}: {exec_n} executed + {na_n} not_applicable)")
    print(f"{'agent':40} {'fidelity%':>9} {'exec':>7} {'na':>5} {'pass%':>6} {'FAR%':>6}")
    for r in ordered:
        print(f"{r.agent:40} {r.fidelity:>9} {f'{r.exec_matches}/{r.exec_total}':>7} "
              f"{f'{r.na_matches}/{r.na_total}':>5} {str(r.pass_rate):>6} {str(r.far):>6}")


def main() -> int:
    ap = argparse.ArgumentParser()
    ap.add_argument("--workspace", default=".")
    ap.add_argument("--run-id", required=True)
    ap.add_argument("--correlation-id", default=None,
                    help="run correlation id stamped into every log line; default: a fresh UUIDv4")
    a = ap.parse_args()
    # observability: bind the correlation id FIRST so even early validation failures below
    # are tagged and attributable to this run/invocation.
    correlation_id = a.correlation_id or str(uuid.uuid4())
    _CORRELATION_ID.set(correlation_id)
    try:
        ws = Path(a.workspace).expanduser().resolve()
    except (OSError, ValueError, RuntimeError) as exc:
        log.error("invalid --workspace %r (%s)", a.workspace, exc.__class__.__name__)
        return 2
    try:
        run_id = _validate_run_id(a.run_id)
    except ValueError as exc:
        log.error("%s", exc)
        return 2

    # observability: an entry log so a crash before the first score is attributable to
    # a specific workspace + run, not an invisible startup failure.
    log.info("auth-flow judge starting: workspace=%s run-id=%s", ws, run_id)
    exec_truth, na_truth = gold_truth(ws)
    denom = len(exec_truth) + len(na_truth)
    run_dir = ws / "results" / "runs" / run_id

    rows: list[_Row] = []
    for jf in _result_files(run_dir):
        row = _process_file(jf, exec_truth, na_truth, ws)
        if row is not None:
            rows.append(row)

    _print_report(rows, len(exec_truth), len(na_truth), denom)
    if not rows:
        log.warning("no agent results found for run %s", run_id)
        print("[warn] no agent results found for this run.")
        return 1
    log.info("scored %d agent result file(s) for run %s (denominator=%d)", len(rows), run_id, denom)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())

# --- Contract-oracle rollout (plan 40): hard guardrail carried in every prompt copy ---
# ## Contract-conformance oracle & deviation findings (hard guardrail)
#
# Your expected outcome for every case is the UNIVERSAL HTTP/REST contract for that operation, read from
# `agent-foundry/references/contract-oracle.md` — NEVER the target's own documentation or observed
# behaviour. For each case emit `expected_by_contract` (the status + invariants from the contract table)
# and, only when the target's documented expectation differs, `expected_by_docs`. A separate
# deterministic harness fills `observed` and emits `deviations[]` — every case where observed differs
# from expected_by_contract, or where expected_by_docs differs from expected_by_contract — as findings,
# surfaced EVEN WHEN the response is acceptable by the target's own docs. Verify every effect BLACK-BOX by
# read-back (a follow-up request): a create is proven by a follow-up GET returning the resource, a delete
# by a follow-up GET returning 404, an update by a follow-up GET reflecting the change — never by a
# database row, log line, or injected instrumentation the target may not expose; where such an assertion
# is impossible black-box, degrade to the observable signal rather than skipping it. Repeat each case the
# configured soak count and flag any non-deterministic result as a deviation. Enumerate the FULL
# documented surface — every resource × every method, and every field/parameter including nested paths and
# date/range; a documented capability that is unimplemented (404 or ignored) is a `missing_capability`
# deviation. You MUST NOT encode the target's observed behaviour as the contract, and MUST NOT carry an
# `also_accept` that admits a deviation from a standard code (e.g. accepting 200 for a creation the
# contract fixes at 201); either is a hard-guardrail violation and fails closed.
