"""Shared, deterministic plumbing for the four content-type-negotiation agents.

This module is NOT agent instruction (it carries no debate-gated prompt lines).
It is the identical substrate every framework sits on, so leaderboard differences
are attributable to the framework + its gated prompt + its evolved skill — never
to divergent plumbing.

Responsibilities (all deterministic, no LLM):
  - load the endpoint catalogue from data/verify-content-type-negotiation/cn_spec.json
  - build the compact per-endpoint negotiation brief handed to the agent
  - execute whatever plan the agent emitted:
      * accept family   -> GET <endpoint> with the agent's Accept header
      * consumes family -> <method> <endpoint> with the agent's Content-Type header
                           and a harness-supplied body matching that content type
  - record real status + Content-Type + body-validity, evaluate every scenario
    (shared cn_spec.evaluate), emit result JSON
  - best-effort write a breadcrumb to the shared EverOS memory pool

DummyJSON's repo/data are never modified: accept probes are read-only GETs;
consumes probes use DummyJSON's non-persistent simulated write routes (the same
ones the request-payloads/status builds already exercise).

CRITICAL fidelity property: the body-validity of an accept probe is checked against
the format the AGENT requested (derived from the probe's own Accept value), not a
canonical label — so an agent that emits the wrong Accept header is penalized.

The framework-specific part — turning one endpoint's brief into the negotiation
test plan via the backend LLM — is injected as `generate(cfg) -> plan dict`.
"""
from __future__ import annotations

import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from datetime import datetime, timezone
from pathlib import Path

WORKSPACE = Path(os.environ.get("FORGE_WORKSPACE", ".")).resolve()
SANDBOX_ROOT = Path(os.environ.get("FORGE_SANDBOX_ROOT", WORKSPACE)).resolve()
RUN_ID = os.environ.get("FORGE_RUN_ID", "manual")
TARGET_BASE_URL = os.environ.get("FORGE_TARGET_BASE_URL", "http://localhost:8899").rstrip("/")
SPEC_PATH = WORKSPACE / "data" / "verify-content-type-negotiation" / "cn_spec.json"
EXISTING_ID = 1

# The target rate-limits 100 requests / 10s per IP. Pace below that and back off on
# 429 so a probe measures content negotiation, not rate limiting. The target is never
# modified — we just respect its limiter.
PACE_SECONDS = float(os.environ.get("FORGE_PACE_SECONDS", "0.12"))
RATE_LIMIT_RETRIES = 6
RATE_LIMIT_BACKOFF = 2.0

sys.path.insert(0, str(WORKSPACE / "scripts"))
sys.path.insert(0, str(WORKSPACE / "agents" / "common"))
import cn_spec  # noqa: E402


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
# Spec loading + briefing
# --------------------------------------------------------------------------- #
def load_spec() -> dict:
    return json.loads(SPEC_PATH.read_text())


def endpoint_cfgs() -> list[dict]:
    spec = load_spec()
    out = list(spec["endpoints"])
    only = os.environ.get("FORGE_ONLY_ENDPOINTS", "").strip()
    if only:
        wanted = {s.strip() for s in only.split(",") if s.strip()}
        out = [c for c in out if c["endpoint"] in wanted or c["slug"] in wanted]
    return out


def endpoint_brief(cfg: dict) -> str:
    """Compact, unambiguous negotiation contract handed to the LLM."""
    if cfg["kind"] == "accept":
        return "\n".join([
            f"endpoint_path: {cfg['endpoint']}",
            "kind: accept   # test Accept-header response negotiation on a GET",
            f"supported_formats: {', '.join(cn_spec.SUPPORTED_FORMATS)}   # documented produces, in order",
            f"default_format: {cn_spec.DEFAULT_FORMAT}   # the produces entry the API uses by default",
            f"unsupported_format_probe: {cn_spec.UNSUPPORTED_ACCEPT}   # a format NOT in produces",
            f"wildcard_probe: {cn_spec.WILDCARD}",
        ])
    return "\n".join([
        f"endpoint_path: {cfg['endpoint']}",
        "kind: consumes   # test request-body Content-Type acceptance on a write",
        f"method: {cfg['method']}",
        f"supported_content_type: {cn_spec.SUPPORTED_CONTENT_TYPE}   # documented consumes",
        f"unsupported_content_type_probes: {', '.join(cn_spec.UNSUPPORTED_CONTENT_TYPES)}",
    ])


# --------------------------------------------------------------------------- #
# Body validity (response body structurally valid for a requested format)
# --------------------------------------------------------------------------- #
def _format_of_accept(accept: str) -> str:
    a = (accept or "").strip().lower()
    return cn_spec.DEFAULT_FORMAT if a == cn_spec.WILDCARD else accept


def _body_valid(fmt: str, raw: bytes | None) -> bool:
    if raw is None:
        return False
    try:
        text = raw.decode("utf-8", "replace")
    except Exception:  # noqa
        return False
    f = (fmt or "").lower()
    if f.startswith("application/json"):
        try:
            json.loads(text); return True
        except Exception:  # noqa
            return False
    if f.startswith("application/xml") or f.endswith("/xml"):
        try:
            ET.fromstring(text); return True
        except Exception:  # noqa
            return False
    if f.startswith("text/csv"):
        lines = text.splitlines()
        first = lines[0] if lines else ""
        return ("," in first) and len([c for c in first.split(",") if c.strip()]) >= 2
    return False


# --------------------------------------------------------------------------- #
# HTTP (accept GET + consumes write) with a small retry on transient failure
# --------------------------------------------------------------------------- #
def _get_accept(path: str, accept: str, _retries: int = 2) -> dict:
    url = f"{TARGET_BASE_URL}{path}"
    _assert_local_target(url)
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        time.sleep(PACE_SECONDS)
        req = urllib.request.Request(url, method="GET")   # GET only — never mutate
        req.add_header("Accept", accept if accept else "*/*")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return {"status": r.getcode(), "content_type": r.headers.get("Content-Type"),
                        "_raw": r.read()}
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < RATE_LIMIT_RETRIES:
                time.sleep(RATE_LIMIT_BACKOFF); continue   # respect the limiter
            return {"status": e.code,
                    "content_type": (e.headers.get("Content-Type") if e.headers else None),
                    "_raw": (e.read() if hasattr(e, "read") else b"")}
        except Exception:  # noqa  -- transient connection failure: retry briefly
            if attempt < RATE_LIMIT_RETRIES:
                time.sleep(0.5 * (attempt + 1))
    return {"status": -1, "content_type": None, "_raw": None}


def _write_ctype(method: str, path: str, content_type: str, valid_body: dict,
                 _retries: int = 2) -> dict:
    url = f"{TARGET_BASE_URL}{path.replace('{id}', str(EXISTING_ID))}"
    _assert_local_target(url)
    ct = (content_type or "").lower()
    if ct.startswith("application/json"):
        data = json.dumps(valid_body or {"probe": "forge"}).encode()
    elif ct.startswith("application/xml") or ct.endswith("/xml"):
        data = b"<probe>forge</probe>"
    else:
        data = b"forge content-type probe"
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        time.sleep(PACE_SECONDS)
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", content_type if content_type else "application/octet-stream")
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return {"status": r.getcode()}
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < RATE_LIMIT_RETRIES:
                time.sleep(RATE_LIMIT_BACKOFF); continue   # respect the limiter
            return {"status": e.code}
        except Exception:  # noqa
            if attempt < RATE_LIMIT_RETRIES:
                time.sleep(0.5 * (attempt + 1))
    return {"status": -1}


# --------------------------------------------------------------------------- #
# Execute the AGENT's plan (tolerant of missing/malformed keys)
# --------------------------------------------------------------------------- #
def _exec_accept(cfg: dict, plan: dict):
    probe_obs, reqlog = {}, []
    for p in (plan.get("probes", []) if isinstance(plan, dict) else []):
        if not isinstance(p, dict) or "label" not in p:
            continue
        accept = p.get("accept")
        if accept is None:
            continue
        raw = _get_accept(cfg["endpoint"], accept)
        fmt = _format_of_accept(accept)   # validate vs the AGENT's requested format
        body_valid = _body_valid(fmt, raw.get("_raw")) if raw.get("status") == 200 else False
        probe_obs[p["label"]] = {"status": raw["status"],
                                 "content_type": raw.get("content_type"),
                                 "body_valid": body_valid}
        reqlog.append({"label": p["label"], "accept": accept, "status": raw["status"],
                       "content_type": raw.get("content_type"),
                       "requested_format": fmt, "body_valid": body_valid})
    return probe_obs, reqlog


def _exec_consumes(cfg: dict, plan: dict):
    probe_obs, reqlog = {}, []
    method = cfg["method"]
    for p in (plan.get("probes", []) if isinstance(plan, dict) else []):
        if not isinstance(p, dict) or "label" not in p:
            continue
        ctype = p.get("content_type")
        if ctype is None:
            continue
        rec = _write_ctype(method, cfg["endpoint"], ctype, cfg.get("valid", {}))
        probe_obs[p["label"]] = {"status": rec["status"]}
        reqlog.append({"label": p["label"], "content_type": ctype, "status": rec["status"]})
    return probe_obs, reqlog


# --------------------------------------------------------------------------- #
# Shared EverOS memory pool (best-effort, non-fatal, air-gapped)
# --------------------------------------------------------------------------- #
def everos_note(agent: str, text: str) -> None:
    cfg = _config()
    base = cfg.get("everos_base_url", "http://127.0.0.1:8000").rstrip("/")
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
def run_cn_test(agent: str, generate) -> dict:
    """Drive the whole task for one agent.

    generate(cfg: dict) -> the negotiation plan object (see cn_spec): a dict with
        "probes" (accept probes {label, accept} OR consumes probes {label,
        content_type}). The harness executes the AGENT's planned probes against the
        one local target and evaluates every scenario. Whatever the agent fails to
        emit scores as 'missing'. generate may raise; recorded per-endpoint.
    """
    cfgs = endpoint_cfgs()
    all_cases = []
    total = correct = 0

    for cfg in cfgs:
        try:
            plan = generate(cfg) or {}
            gen_error = None
        except Exception as e:  # noqa
            plan, gen_error = {}, f"{type(e).__name__}: {e}"

        if cfg["kind"] == "accept":
            probe_obs, reqlog = _exec_accept(cfg, plan)
        else:
            probe_obs, reqlog = _exec_consumes(cfg, plan)
        observed = cn_spec.evaluate(cfg["kind"], probe_obs)

        scenarios = []
        ideal = cn_spec.ideal_for(cfg["kind"])
        for label in cn_spec.scenarios_for(cfg["kind"]):
            tok = observed.get(label, "missing")
            ok = cn_spec.correct(cfg["kind"], label, tok)
            scenarios.append({"endpoint": cfg["endpoint"], "kind": cfg["kind"],
                              "scenario": label, "ideal": ideal[label],
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        all_cases.append({"slug": cfg["slug"], "endpoint": cfg["endpoint"],
                          "kind": cfg["kind"], "method": cfg.get("method"),
                          "emitted_plan": plan, "request_log": reqlog,
                          "scenarios": scenarios, "error": gen_error})

    rate = round(100.0 * correct / total, 2) if total else 0.0
    raw = {"agent": agent, "run_id": RUN_ID, "target": TARGET_BASE_URL,
           "content_type_negotiation_accuracy_pct": rate,
           "scenarios_total": total, "scenarios_api_correct": correct,
           "endpoints": all_cases}
    run_dir = WORKSPACE / "results" / "runs" / RUN_ID
    run_dir.mkdir(parents=True, exist_ok=True)
    cases_path = run_dir / f"{agent}.cases.json"
    _assert_sandbox(cases_path)
    cases_path.write_text(json.dumps(raw, indent=2))

    emit(agent, rate, str(cases_path), extra={
        "content_type_negotiation_accuracy_pct": rate,
        "scenarios_total": total})
    everos_note(agent, f"content-type-negotiation run: accuracy_rate={rate}% "
                       f"over {len(cfgs)} endpoints ({total} scenarios)")
    return raw


def emit(agent: str, metric_value: float, raw_output_path: str, extra: dict | None = None) -> None:
    """Write results/runs/<run>/<agent>.json. metric_value here is the headline
    negotiation-accuracy rate; the judge later overwrites it with fidelity-to-gold."""
    metric = {}
    mp = WORKSPACE / "judge" / "verify-content-type-negotiation" / "metric.json"
    if mp.exists():
        metric = json.loads(mp.read_text())
    out = WORKSPACE / "results" / "runs" / RUN_ID / f"{agent}.json"
    _assert_sandbox(out)
    out.parent.mkdir(parents=True, exist_ok=True)
    payload = {"agent": agent, "run_id": RUN_ID,
               "metric_name": metric.get("metric_name", "content_type_negotiation_accuracy_pct"),
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
