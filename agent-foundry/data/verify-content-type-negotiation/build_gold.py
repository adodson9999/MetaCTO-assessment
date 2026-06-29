#!/usr/bin/env python3
"""Gold-set builder for the API content-type-negotiation testing task.

This is NOT one of the four agents. It is the deterministic *reference*:
it authors the negotiation contract (cn_openapi.json) + the agents' input spec,
derives the canonical correct probe matrix per endpoint, sends every probe to a
locally-running DummyJSON, and records the REAL observed behavior (status,
Content-Type header, body validity per requested format) per scenario.

DummyJSON's repo and data are NEVER modified. We only:
  - author a SEPARATE cn_openapi.json describing the negotiation contract a proper
    API would publish (so the agents have a documented produces/consumes to test
    against), and
  - probe the live API: read-only GETs for the Accept family, and the SAME
    POST/PUT/PATCH write requests the request-payloads/status builds already use
    for the Content-Type/415 family (DummyJSON's /add and update routes are
    non-persistent simulations — they do not mutate the dataset).

The reused 22-endpoint catalogue is imported straight from data/build_gold.py.
From it we derive:
  - GET targets (the readable counterpart of each write op, deduped) -> accept family
  - the 22 write ops themselves -> consumes family

The recorded per-(endpoint, scenario) observed token is the ground truth. Agents
are later ranked on how faithfully their own runs reproduce this table (coverage +
correct probe construction). The idealized contract lives in cn_spec.IDEAL_*; where
the real token differs from the ideal is a genuine QA finding about DummyJSON.

Outputs (all under data/verify-content-type-negotiation/):
  - cn_openapi.json          the negotiation contract the agents are briefed from (INPUT)
  - cn_spec.json             the endpoint catalogue (accept + consumes families) (INPUT)
  - gold/<slug>.json         per-endpoint gold scenarios
  - gold.json                consolidated gold table + empirical negotiation-accuracy summary

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. No network beyond BASE_URL. Air-gapped.
"""
import json
import os
import sys
import time
import urllib.parse
import urllib.request
import urllib.error
import xml.etree.ElementTree as ET
from pathlib import Path

# The target rate-limits 100 requests / 10s per IP. Pace below that and back off on
# 429 so the gold reflects content negotiation, not rate limiting. (DummyJSON itself
# is never modified; we just respect its limiter.)
PACE_SECONDS = 0.12
RATE_LIMIT_RETRIES = 6
RATE_LIMIT_BACKOFF = 2.0


def _pace() -> None:
    time.sleep(PACE_SECONDS)

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

# Shared scenario structure (one source of truth with the agent harness).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import cn_spec  # noqa: E402

# Reuse the 22-endpoint catalogue verbatim.
sys.path.insert(0, str(HERE.parents[1] / "data"))
import build_gold as rb  # noqa: E402

EXISTING_ID = 1


# --------------------------------------------------------------------------- #
# Derive the two endpoint families from the reused 22-endpoint catalogue
# --------------------------------------------------------------------------- #
def _read_path(path: str) -> str | None:
    """The readable GET counterpart of a write op's path, or None if not derivable.
    /collection/add        -> /collection
    /collection/{id}       -> /collection/{id}  (concrete id substituted later)
    /auth/login            -> None  (no clean public read; excluded from accept family)
    """
    if path.endswith("/add"):
        return path[: -len("/add")]
    if path.endswith("/{id}"):
        return path
    return None


def consumes_endpoints() -> list[dict]:
    """All 22 write ops -> consumes family (request Content-Type / 415 probes)."""
    out = []
    for ep in rb.ENDPOINTS:
        out.append({
            "slug": ep["slug"],
            "kind": "consumes",
            "endpoint": ep["path"],
            "method": ep["method"],
            "valid": ep.get("valid", {}),
        })
    return out


def accept_endpoints() -> list[dict]:
    """Unique GET targets derived from the 22 -> accept family (Accept probes)."""
    seen: dict[str, dict] = {}
    for ep in rb.ENDPOINTS:
        rp = _read_path(ep["path"])
        if rp is None:
            continue
        concrete = rp.replace("{id}", str(EXISTING_ID))
        if concrete in seen:
            continue
        slug = "get_" + concrete.strip("/").replace("/", "_")
        seen[concrete] = {"slug": slug, "kind": "accept", "endpoint": concrete}
    return list(seen.values())


# --------------------------------------------------------------------------- #
# cn_openapi.json — the declared negotiation contract (does NOT touch DummyJSON)
# --------------------------------------------------------------------------- #
def build_cn_openapi(accepts: list[dict], consumes: list[dict]) -> dict:
    paths: dict[str, dict] = {}
    for a in accepts:
        paths.setdefault(a["endpoint"], {})["get"] = {
            "summary": f"List/read {a['endpoint']}",
            "produces": list(cn_spec.SUPPORTED_FORMATS),   # json (default), xml, csv
        }
    for c in consumes:
        paths.setdefault(c["endpoint"], {})[c["method"].lower()] = {
            "summary": f"{c['method']} {c['endpoint']}",
            "consumes": [cn_spec.SUPPORTED_CONTENT_TYPE],  # application/json only
        }
    return {
        "openapi": "3.0.0",
        "info": {
            "title": "DummyJSON content-negotiation contract (authored for the "
                     "content-type-negotiation task; DummyJSON itself is unmodified)",
            "version": "1.0.0",
            "description": "Describes the produces/consumes a properly content-"
                           "negotiating API would publish for these resources. The "
                           "live DummyJSON ignores Accept and request Content-Type; "
                           "the gold records that real behavior, and the gap is the "
                           "QA finding.",
        },
        "x-default-produces": cn_spec.DEFAULT_FORMAT,
        "x-unsupported-accept-probe": cn_spec.UNSUPPORTED_ACCEPT,
        "x-unsupported-content-type-probes": list(cn_spec.UNSUPPORTED_CONTENT_TYPES),
        "paths": paths,
    }


def build_cn_spec_catalogue(accepts: list[dict], consumes: list[dict]) -> dict:
    return {
        "title": "Content-type-negotiation endpoint catalogue (authored for the task)",
        "description": "Agents are briefed one endpoint at a time. 'accept' endpoints "
                       "get Accept-header response-negotiation probes; 'consumes' "
                       "endpoints get request Content-Type probes. DummyJSON is never "
                       "modified — read-only GETs for accept, non-persistent simulated "
                       "writes for consumes.",
        "target": BASE_URL,
        "supported_formats": list(cn_spec.SUPPORTED_FORMATS),
        "default_format": cn_spec.DEFAULT_FORMAT,
        "unsupported_accept_probe": cn_spec.UNSUPPORTED_ACCEPT,
        "wildcard_probe": cn_spec.WILDCARD,
        "supported_content_type": cn_spec.SUPPORTED_CONTENT_TYPE,
        "unsupported_content_type_probes": list(cn_spec.UNSUPPORTED_CONTENT_TYPES),
        "endpoints": accepts + consumes,
    }


# --------------------------------------------------------------------------- #
# HTTP probing (records empirical truth)
# --------------------------------------------------------------------------- #
def _body_valid(fmt: str, raw: bytes) -> bool:
    """Structural validity of the response body for the REQUESTED format, per the
    task's definitions (valid JSON / valid XML / CSV first line has comma-separated
    column headers)."""
    if raw is None:
        return False
    try:
        text = raw.decode("utf-8", "replace")
    except Exception:  # noqa
        return False
    f = fmt.lower()
    if f.startswith("application/json"):
        try:
            json.loads(text)
            return True
        except Exception:  # noqa
            return False
    if f.startswith("application/xml") or f.endswith("/xml"):
        try:
            ET.fromstring(text)
            return True
        except Exception:  # noqa
            return False
    if f.startswith("text/csv"):
        first = text.splitlines()[0] if text.splitlines() else ""
        return ("," in first) and len([c for c in first.split(",") if c.strip()]) >= 2
    return False


def _get_accept(path: str, accept: str) -> dict:
    url = f"{BASE_URL}{path}"
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        _pace()
        req = urllib.request.Request(url, method="GET")
        req.add_header("Accept", accept)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return {"status": r.getcode(), "content_type": r.headers.get("Content-Type"),
                        "body_valid": None, "_raw": r.read()}
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < RATE_LIMIT_RETRIES:
                time.sleep(RATE_LIMIT_BACKOFF); continue   # respect the limiter, not a finding
            raw = e.read() if hasattr(e, "read") else b""
            ct = e.headers.get("Content-Type") if e.headers else None
            return {"status": e.code, "content_type": ct, "body_valid": None, "_raw": raw}
        except Exception as ex:  # noqa
            return {"status": -1, "content_type": None, "body_valid": False, "error": str(ex)}
    return {"status": 429, "content_type": None, "body_valid": False}


def _write_ctype(method: str, path: str, content_type: str, valid_body: dict) -> dict:
    url = f"{BASE_URL}{path.replace('{id}', str(EXISTING_ID))}"
    ct = content_type.lower()
    if ct.startswith("application/json"):
        data = json.dumps(valid_body or {"probe": "forge"}).encode()
    elif ct.startswith("application/xml") or ct.endswith("/xml"):
        data = b"<probe>forge</probe>"
    else:  # text/plain et al.
        data = b"forge content-type probe"
    for attempt in range(RATE_LIMIT_RETRIES + 1):
        _pace()
        req = urllib.request.Request(url, data=data, method=method)
        req.add_header("Content-Type", content_type)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return {"status": r.getcode()}
        except urllib.error.HTTPError as e:
            if e.code == 429 and attempt < RATE_LIMIT_RETRIES:
                time.sleep(RATE_LIMIT_BACKOFF); continue   # respect the limiter
            return {"status": e.code}
        except Exception as ex:  # noqa
            return {"status": -1, "error": str(ex)}
    return {"status": 429}


# --------------------------------------------------------------------------- #
# Probe one endpoint's reference plan -> observed tokens
# --------------------------------------------------------------------------- #
def probe_accept(cfg: dict) -> dict:
    plan = cn_spec.build_reference_plan(cfg)
    probe_obs, reqlog = {}, []
    for p in plan["probes"]:
        label, accept = p["label"], p["accept"]
        raw = _get_accept(cfg["endpoint"], accept)
        fmt = cn_spec.ACCEPT_PROBE_FORMAT[label]
        body_valid = _body_valid(fmt, raw.get("_raw")) if raw.get("status") == 200 else False
        rec = {"status": raw["status"], "content_type": raw.get("content_type"),
               "body_valid": body_valid}
        probe_obs[label] = rec
        reqlog.append({"label": label, "accept": accept, "status": rec["status"],
                       "content_type": rec["content_type"], "body_valid": body_valid,
                       "requested_format": fmt})
    observed = cn_spec.evaluate_accept(probe_obs)
    return observed, reqlog


def probe_consumes(cfg: dict) -> dict:
    plan = cn_spec.build_reference_plan(cfg)
    probe_obs, reqlog = {}, []
    for p in plan["probes"]:
        label, ctype = p["label"], p["content_type"]
        rec = _write_ctype(cfg["method"], cfg["endpoint"], ctype, cfg.get("valid", {}))
        probe_obs[label] = rec
        reqlog.append({"label": label, "content_type": ctype, "status": rec["status"]})
    observed = cn_spec.evaluate_consumes(probe_obs)
    return observed, reqlog


# --------------------------------------------------------------------------- #
# Main
# --------------------------------------------------------------------------- #
def main() -> int:
    accepts = accept_endpoints()
    consumes = consumes_endpoints()
    endpoints = accepts + consumes

    # Author the INPUT specs (do not touch DummyJSON).
    HERE.mkdir(parents=True, exist_ok=True)
    GOLD_DIR.mkdir(parents=True, exist_ok=True)
    (HERE / "cn_openapi.json").write_text(
        json.dumps(build_cn_openapi(accepts, consumes), indent=2))
    (HERE / "cn_spec.json").write_text(
        json.dumps(build_cn_spec_catalogue(accepts, consumes), indent=2))

    all_cases = []
    total = correct = 0
    for cfg in endpoints:
        if cfg["kind"] == "accept":
            observed, reqlog = probe_accept(cfg)
        else:
            observed, reqlog = probe_consumes(cfg)

        scen_labels = cn_spec.scenarios_for(cfg["kind"])
        ideal = cn_spec.ideal_for(cfg["kind"])
        scenarios = []
        for label in scen_labels:
            tok = observed.get(label, "missing")
            ok = cn_spec.correct(cfg["kind"], label, tok)
            scenarios.append({"endpoint": cfg["endpoint"], "kind": cfg["kind"],
                              "scenario": label, "ideal": ideal[label],
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
        case = {"slug": cfg["slug"], "endpoint": cfg["endpoint"], "kind": cfg["kind"],
                "method": cfg.get("method"), "request_log": reqlog, "scenarios": scenarios}
        all_cases.append(case)
        (GOLD_DIR / f"{cfg['slug']}.json").write_text(json.dumps(case, indent=2))

    rate = round(100.0 * correct / total, 2) if total else 0.0
    gold = {
        "task": "api-tester / verify-content-type-negotiation",
        "target": BASE_URL,
        "content_type_negotiation_accuracy_pct": rate,
        "scenarios_total": total,
        "scenarios_api_correct": correct,
        "accept_endpoints": len(accepts),
        "consumes_endpoints": len(consumes),
        "endpoints": all_cases,
    }
    (HERE / "gold.json").write_text(json.dumps(gold, indent=2))

    print(f"endpoints: {len(accepts)} accept + {len(consumes)} consumes = {len(endpoints)}")
    print(f"scenarios: {total}  api_correct: {correct}")
    print(f"Content-Type Negotiation Accuracy = {rate}%")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
