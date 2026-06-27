"""Shared, deterministic plumbing for the four concurrent-request-handling agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never to
divergent plumbing. In particular, the *concurrency mechanism itself* lives here
(one asyncio barrier-release of N requests), so all four agents fire requests the
exact same way; what differs is only the PLAN each agent emitted.

Responsibilities (all deterministic, no LLM):
  - load the run config from data/test-concurrent-request-handling/concurrency_spec.json
  - build the compact brief handed to the agent
  - execute whatever plan the agent emitted:
      * READ test : N simultaneous GETs to the (read-only) DummyJSON read endpoint
      * WRITE test: N simultaneous POSTs to the local SQLite write target, each with
        a unique, per-(run,agent)-namespaced test_id materialized from the template
  - query the SQLite DB FILE directly (the task's "psql/mysql CLI" step) for the
    count delta, duplicates, and missing test_ids
  - evaluate every scenario (shared concurrency_spec.evaluate), record, emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON is tested AS-IS and never modified: the read test is GET-only, no body,
no mutation. Only the separate, purpose-built local SQLite target is written to.

The framework-specific part — turning the brief into the concurrency test plan via
the backend LLM — is injected as `generate(cfg) -> plan dict`.
"""
from __future__ import annotations

import asyncio
import json
import os
import sqlite3
import sys
import time
import urllib.parse
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
SPEC_PATH = WORKSPACE / "data" / "test-concurrent-request-handling" / "concurrency_spec.json"

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import concurrency_spec  # noqa: E402

try:
    import httpx  # noqa: E402
except Exception as _e:  # noqa
    httpx = None


# --------------------------------------------------------------------------- #
# Sandbox + host guards
# --------------------------------------------------------------------------- #
def _assert_sandbox(path: Path) -> None:
    p = path.resolve()
    if p != SANDBOX_ROOT and SANDBOX_ROOT not in p.parents:
        raise PermissionError(f"sandbox violation: {p} is outside {SANDBOX_ROOT}")


def _assert_local_target(url: str) -> None:
    host = urllib.parse.urlparse(url).hostname or ""
    if host not in ("localhost", "127.0.0.1", "::1"):
        raise PermissionError(f"refusing non-local HTTP target: {host}")


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
    """
    staging_dir = WORKSPACE / "results" / "runs" / RUN_ID / "staging" / agent
    staging_dir.mkdir(parents=True, exist_ok=True)
    out_path = staging_dir / f"{item_id}-findings.json"
    _assert_sandbox(out_path)

    findings = []
    for i, r in enumerate(step_results, start=1):
        findings.append({
            "step_number": i,
            "item_id": item_id,
            "item_label": item_label,
            **r,
        })

    out_path.write_text(json.dumps({
        "agent": agent,
        "item_id": item_id,
        "item_label": item_label,
        "run_id": RUN_ID,
        "findings": findings,
    }, indent=2))


# --------------------------------------------------------------------------- #
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    spec = json.loads(SPEC_PATH.read_text())
    # env overrides for the runner/phase4 script (ports may differ run to run)
    spec["read_base_url"] = os.environ.get("FORGE_READ_BASE_URL", spec["read_base_url"]).rstrip("/")
    spec["write_base_url"] = os.environ.get("FORGE_WRITE_BASE_URL", spec["write_base_url"]).rstrip("/")
    # held-out VARIANT overrides (used only by the SkillOpt evolution gate) so a
    # candidate skill is validated on a config it was NOT tuned on, without editing
    # the spec file. Absent in normal runs.
    ho_c = os.environ.get("FORGE_HELDOUT_CONCURRENCY")
    if ho_c:
        spec["concurrency"] = int(ho_c)
    ho_re = os.environ.get("FORGE_HELDOUT_READ_ENDPOINT")
    if ho_re:
        spec["read_endpoint"] = ho_re
    ho_t = os.environ.get("FORGE_HELDOUT_TEST_ID_TEMPLATE")
    if ho_t:
        spec["test_id_template"] = ho_t
    return spec


def run_cfg() -> dict:
    return load_spec()


def brief(cfg: dict) -> str:
    """Compact, unambiguous concurrency contract handed to the LLM."""
    return "\n".join([
        f"read_endpoint: {cfg['read_endpoint']}   # one GET path on the read target",
        f"read_expected_status: {cfg['read_expected_status']}",
        f"write_endpoint: {cfg['write_endpoint']}  # one POST path on the write target",
        f"write_expected_status: {cfg['write_expected_status']}",
        f"concurrency: {cfg['concurrency']}   # number of simultaneous requests per test",
        f"test_id_field: {cfg['test_id_field']}   # JSON body field carrying the unique id",
        f"test_id_template: {cfg['test_id_template']}   # '[VU_ID]' is replaced by the VU number 1..{cfg['concurrency']}",
    ])


# --------------------------------------------------------------------------- #
# Concurrent execution (one barrier-release of N requests) — deterministic
# --------------------------------------------------------------------------- #
async def _fire(method: str, url: str, bodies: list | None, n: int,
                timeout: float = 30.0, repair_rounds: int = 10):
    """Fire n requests, all released together (the 'ramp to N VUs in 0s' analog), then
    REPAIR any that hit a transport failure. Returns (results, first_wave_ok) where
    results is a list of (status:int, json_body|None) in VU order.

    Two phases:
      1. SIMULTANEOUS first wave — all n requests gated to release at once. This is the
         actual concurrency measurement.
      2. PACED repair — a single-process target (e.g. DummyJSON's Node server) may reset
         some of 50+ concurrent sockets at accept time (a capacity artifact, NOT data
         corruption). Indices that came back as status -1 (connection reset/refused/
         timeout — never a real HTTP response) are re-issued in paced sequential rounds
         until they complete or the cap is hit, so the correctness assertions (all 200,
         identical bodies / all 201, exactly-50 rows) can be evaluated on completed
         requests. Real HTTP codes (200/201/4xx/5xx) are answers and are never repaired.

    Idempotency of repair:
      - GET is idempotent.
      - POST targets a UNIQUE(test_id) endpoint, so re-issuing after a possibly-successful
        insert returns 409 (no second row); a repaired-409 is mapped back to 201 because
        the row exists exactly once — preserving the exactly-50 / zero-duplicate contract.
    """
    _assert_local_target(url)
    results: list = [None] * n
    gate = asyncio.Event()
    limits = httpx.Limits(max_connections=n + 10, max_keepalive_connections=n + 10)

    async with httpx.AsyncClient(timeout=timeout, limits=limits) as client:
        async def issue(i: int, repaired: bool):
            try:
                if method == "GET":
                    resp = await client.get(url)
                else:
                    resp = await client.post(url, json=(bodies[i] if bodies else None))
                status = resp.status_code
                if method == "POST" and repaired and status == 409:
                    status = 201  # our own earlier attempt already inserted this test_id
                try:
                    parsed = resp.json()
                except Exception:  # noqa
                    parsed = None
                results[i] = (status, parsed)
            except Exception:  # noqa  -- transient transport failure
                results[i] = (-1, None)

        async def one(i: int):
            await gate.wait()  # hold until every VU is ready, then go at once
            await issue(i, repaired=False)

        tasks = [asyncio.create_task(one(i)) for i in range(n)]
        await asyncio.sleep(0.05)  # let all tasks reach the gate
        gate.set()
        await asyncio.gather(*tasks)

        first_wave_ok = sum(1 for s, _ in results if s is not None and s != -1)

        # paced repair of transport-failed (-1) AND rate-limited (429) indices.
        # 429 is the read target's documented "retry later" (DummyJSON rate-limits
        # ~100 req / 10s per IP); GET is idempotent so re-issuing after a short pace
        # is correct and recovers any request that hit a window edge.
        for rnd in range(repair_rounds):
            failed = [i for i in range(n)
                      if results[i] is None or results[i][0] in (-1, 429)]
            if not failed:
                break
            rate_limited = any(results[i] is not None and results[i][0] == 429
                               for i in failed)
            for i in failed:
                await issue(i, repaired=True)
                await asyncio.sleep(0.01)  # pace so the repair wave never re-collides
            # If the stragglers are rate-limited 429s, back off long enough to span a
            # fresh rate-limit window (~10s); transport -1s only need a short pace.
            await asyncio.sleep(2.5 if rate_limited else 0.2 * (rnd + 1))

    return results, first_wave_ok


def _wait_for_clear_window(url: str, max_wait: float = 14.0) -> int:
    """Wait until the read target's rate-limit window is clear before the timed burst.

    DummyJSON rate-limits ~100 requests / 10s per IP (express-rate-limit; the
    development skip does not take effect in this fork), so a 50-request burst fired
    right after a prior burst can collide with a window already near its cap and draw
    429s. Since we are testing CONCURRENCY (can the server serve 50 simultaneous reads
    with identical bodies), not rate-limit policy, we send single probe GETs until one
    returns a non-429 status — meaning the window has refilled — then fire the burst
    into a clean window. Returns the number of probe seconds waited (best-effort).
    """
    import time as _t
    import urllib.request
    import urllib.error
    try:
        _assert_local_target(url)
    except Exception:  # noqa
        return 0
    waited = 0.0
    while waited < max_wait:
        try:
            urllib.request.urlopen(url, timeout=10).read()
            return int(waited)  # non-429 success => window is clear
        except urllib.error.HTTPError as e:
            if e.code != 429:
                return int(waited)  # some other real code; not a rate-limit wait
            _t.sleep(1.0)
            waited += 1.0
        except Exception:  # noqa  -- transient; brief wait then retry probe
            _t.sleep(0.5)
            waited += 0.5
    return int(waited)


# --------------------------------------------------------------------------- #
# Direct DB query (the task's psql/mysql step) — read the SQLite file directly
# --------------------------------------------------------------------------- #
def _db_path(cfg: dict) -> Path:
    raw = os.environ.get("CONCURRENCY_DB_PATH") or str(WORKSPACE / cfg["db_path"])
    return Path(raw).resolve()


def _db_count(cfg: dict, like_prefix: str) -> int:
    p = _db_path(cfg)
    if not p.exists():
        return 0
    conn = sqlite3.connect(str(p), timeout=10.0)
    try:
        conn.execute("PRAGMA busy_timeout=10000;")
        cur = conn.execute(
            f"SELECT COUNT(*) FROM {cfg['db_table']} WHERE test_id LIKE ?", (like_prefix + "%",)
        )
        return int(cur.fetchone()[0])
    except sqlite3.OperationalError:
        return 0  # table not created yet (write target initializes it on first insert)
    finally:
        conn.close()


def _db_scope_state(cfg: dict, like_prefix: str) -> dict:
    """present_test_ids + duplicate_test_ids within this run/agent's scope."""
    p = _db_path(cfg)
    present, dups = [], []
    if not p.exists():
        return {"present_test_ids": present, "duplicate_test_ids": dups}
    conn = sqlite3.connect(str(p), timeout=10.0)
    try:
        conn.execute("PRAGMA busy_timeout=10000;")
        cur = conn.execute(
            f"SELECT test_id, COUNT(*) FROM {cfg['db_table']} "
            f"WHERE test_id LIKE ? GROUP BY test_id", (like_prefix + "%",)
        )
        for tid, c in cur.fetchall():
            present.append(tid)
            if c > 1:
                dups.append(tid)
    except sqlite3.OperationalError:
        pass  # table not created yet
    finally:
        conn.close()
    return {"present_test_ids": present, "duplicate_test_ids": dups}


def _db_reset_scope(cfg: dict, like_prefix: str) -> None:
    """Isolate this run/agent: delete any prior rows in its namespace so
    COUNT_BEFORE is a clean baseline and the four agents never collide."""
    p = _db_path(cfg)
    if not p.exists():
        return
    conn = sqlite3.connect(str(p), timeout=10.0)
    try:
        conn.execute("PRAGMA busy_timeout=10000;")
        conn.execute(f"DELETE FROM {cfg['db_table']} WHERE test_id LIKE ?", (like_prefix + "%",))
        conn.commit()
    except sqlite3.OperationalError:
        pass  # table not created yet (nothing to reset)
    finally:
        conn.close()


# --------------------------------------------------------------------------- #
# Plan execution
# --------------------------------------------------------------------------- #
def _exec_plan(agent: str, cfg: dict, plan: dict) -> tuple[dict, dict, dict, dict]:
    """Execute the AGENT's plan. Tolerant of missing/malformed keys — whatever the
    agent omits simply does not get exercised and scores as 'missing'."""
    plan = plan if isinstance(plan, dict) else {}
    read = plan.get("read") if isinstance(plan.get("read"), dict) else {}
    write = plan.get("write") if isinstance(plan.get("write"), dict) else {}

    # ---- READ ----
    read_obs: dict = {}
    read_log: dict = {}
    r_ep = read.get("endpoint")
    r_n = _to_int(read.get("concurrency"))
    if r_ep and r_n:
        url = f"{cfg['read_base_url']}{r_ep}"
        # ensure a clean rate-limit window so the burst measures concurrency, not
        # rate-limit collisions (DummyJSON caps ~100 req/10s per IP).
        wait_s = _wait_for_clear_window(url)
        res, fw_ok = asyncio.run(_fire("GET", url, None, r_n))
        read_obs = {"statuses": [s for s, _ in res], "bodies": [b for _, b in res], "n": r_n}
        read_log = {"endpoint": r_ep, "concurrency": r_n, "url": url,
                    "rate_limit_wait_s": wait_s, "first_wave_ok": fw_ok,
                    "statuses": read_obs["statuses"]}

    # ---- WRITE ----
    write_obs: dict = {}
    db_obs: dict = {}
    write_log: dict = {}
    w_ep = write.get("endpoint")
    w_n = _to_int(write.get("concurrency"))
    template = write.get("test_id_template", cfg["test_id_template"])
    field = write.get("test_id_field", cfg["test_id_field"])
    vu_start = _to_int(write.get("vu_start")) or 1
    vu_end = _to_int(write.get("vu_end")) or (w_n if w_n else 0)
    if w_ep and w_n:
        # logical ids from the plan's template ("concurrent-test-1".."-50")
        logical = concurrency_spec.materialize_test_ids(template, vu_start, vu_end)
        # per-(run,agent) namespace so parallel agents never collide on UNIQUE(test_id)
        prefix = f"{RUN_ID}:{agent}:"
        materialized = [prefix + t for t in logical]
        extra = write.get("payload_fields") if isinstance(write.get("payload_fields"), dict) else {}
        bodies = [{**extra, field: mid} for mid in materialized]

        _db_reset_scope(cfg, prefix)
        count_before = _db_count(cfg, prefix)
        url = f"{cfg['write_base_url']}{w_ep}"
        res, fw_ok = asyncio.run(_fire("POST", url, bodies, w_n))
        count_after = _db_count(cfg, prefix)
        scope = _db_scope_state(cfg, prefix)

        write_obs = {"statuses": [s for s, _ in res], "n": w_n}
        db_obs = {
            "count_before": count_before, "count_after": count_after,
            "expected_test_ids": materialized, "materialized_test_ids": materialized,
            "present_test_ids": scope["present_test_ids"],
            "duplicate_test_ids": scope["duplicate_test_ids"],
        }
        write_log = {"endpoint": w_ep, "concurrency": w_n, "url": url,
                     "first_wave_ok": fw_ok,
                     "count_before": count_before, "count_after": count_after,
                     "statuses": write_obs["statuses"],
                     "duplicates": scope["duplicate_test_ids"]}

    return read_obs, write_obs, db_obs, {"read": read_log, "write": write_log}


def _to_int(v):
    try:
        return int(v)
    except Exception:  # noqa
        return None


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def everos_note(agent: str, text: str) -> None:
    cfg = _config()
    base = cfg.get("everos_base_url", "http://127.0.0.1:8000").rstrip("/")
    import urllib.request
    payload = {
        "session_id": RUN_ID, "app_id": cfg.get("app_id", "forge"),
        "project_id": cfg.get("project_id", "agent-foundry"),
        "messages": [{"sender_id": agent, "sender_name": agent, "role": "assistant",
                      "content": text, "timestamp": int(time.time())}],
    }
    try:
        for ep in ("/api/v1/memory/add", "/api/v1/memory/flush"):
            body = json.dumps(payload if ep.endswith("add") else
                              {k: payload[k] for k in ("session_id", "app_id", "project_id")}).encode()
            req = urllib.request.Request(base + ep, data=body,
                                         headers={"Content-Type": "application/json"})
            urllib.request.urlopen(req, timeout=5).read()
    except Exception:  # noqa
        pass
    notes = WORKSPACE / "memory" / "agent-notes"
    notes.mkdir(parents=True, exist_ok=True)
    with open(notes / f"{agent}.md", "a") as f:
        f.write(f"- [{datetime.now(timezone.utc).isoformat()}] run={RUN_ID} {text}\n")


def _config() -> dict:
    import tomllib
    cfg = tomllib.loads((WORKSPACE / "config.toml").read_text())
    mem = cfg.get("memory", {})
    return {"everos_base_url": mem.get("everos_base_url"),
            "app_id": mem.get("app_id"), "project_id": mem.get("project_id")}


# --------------------------------------------------------------------------- #
# The shared driver
# --------------------------------------------------------------------------- #
def run_concurrency_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the concurrency plan object (see concurrency_spec): a dict
        with `read`, `write`, and `assert_zero_500`. The harness executes the AGENT's
        plan (N simultaneous GETs + N simultaneous namespaced POSTs), queries the DB
        directly, and evaluates every scenario. Whatever the agent fails to emit scores
        as 'missing'. generate may raise; recorded.
    """
    if httpx is None:
        raise RuntimeError("httpx is required for the concurrency harness; install it in the venv")

    cfg = run_cfg()
    try:
        plan = generate(cfg) or {}
        gen_error = None
    except Exception as e:  # noqa
        plan, gen_error = {}, f"{type(e).__name__}: {e}"

    read_obs, write_obs, db_obs, reqlog = _exec_plan(agent, cfg, plan)
    observed = concurrency_spec.evaluate(read_obs, write_obs, db_obs)

    scenarios = []
    total = correct = 0
    for label in concurrency_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = concurrency_spec.correct(label, tok)
        scenarios.append({"scenario": label, "ideal": concurrency_spec.IDEAL[label],
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0

    # G1 staging write — write per-item findings for G1b orchestration
    _write_staging_findings(
        agent=agent,
        item_id="concurrency",
        item_label=f"read={cfg.get('read_endpoint')} write={cfg.get('write_endpoint')}",
        step_results=[
            {
                "assertion_result": "PASS" if s.get("api_correct") else "FAIL",
                "assertion_detail": (
                    f"scenario={s.get('scenario')} ideal={s.get('ideal')} "
                    f"observed={s.get('observed_token')}"
                ),
                **s,
            }
            for s in scenarios
        ],
    )

    headline = concurrency_spec.success_rate(read_obs, write_obs, db_obs)
    rate = headline["rate_pct"]

    raw = {
        "agent": agent, "run_id": RUN_ID,
        "read_target": cfg["read_base_url"], "write_target": cfg["write_base_url"],
        "concurrent_request_success_rate_pct": rate,
        "read_correct": headline["read_correct"], "write_correct": headline["write_correct"],
        "requests_total": headline["total"],
        "db_count_delta": (db_obs.get("count_after", 0) - db_obs.get("count_before", 0))
        if db_obs else None,
        "scenarios_total": total, "scenarios_api_correct": correct,
        "emitted_plan": plan, "request_log": reqlog,
        "scenarios": scenarios, "error": gen_error,
    }
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "concurrent_request_success_rate_pct": rate,
        "scenarios_total": total,
        "db_count_delta": raw["db_count_delta"]})

    everos_note(agent, f"concurrent-request-handling run: success_rate={rate}% "
                       f"(read_ok={headline['read_correct']}/{read_obs.get('n', 0)}, "
                       f"write_ok={headline['write_correct']}/{write_obs.get('n', 0)}, "
                       f"db_delta={raw['db_count_delta']})")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    Concurrent Request Success Rate; the judge later overwrites metric_value with
    fidelity-to-gold for ranking."""
    metric = {}
    mp = WORKSPACE / "judge" / "test-concurrent-request-handling" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "concurrent_request_success_rate_pct"),
               "metric_value": metric_value, "raw_output_path": raw_output_path,
               "ts": datetime.now(timezone.utc).isoformat()}
    if extra:
        payload.update(extra)
    out.write_text(json.dumps(payload, indent=2))


def extract_json(text: str):
    """Pull the first balanced JSON object out of arbitrary LLM text."""
    import re
    if not text:
        return None
    fence = re.search(r"```(?:json)?\s*(\{.*?\})\s*```", text, re.DOTALL)
    candidate = fence.group(1) if fence else None
    if candidate is None:
        start = text.find("{")
        if start == -1:
            return None
        depth = 0
        for i in range(start, len(text)):
            if text[i] == "{":
                depth += 1
            elif text[i] == "}":
                depth -= 1
                if depth == 0:
                    candidate = text[start:i + 1]
                    break
    if candidate is None:
        return None
    try:
        return json.loads(candidate)
    except Exception:  # noqa
        return None
