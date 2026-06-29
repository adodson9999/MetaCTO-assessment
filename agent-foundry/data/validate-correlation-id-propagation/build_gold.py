#!/usr/bin/env python3
"""Gold-set builder for the API correlation-ID-propagation testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors the
fixed propagation contract + the agents' input brief (cid_spec.json), derives the
canonical correct propagation test plan, obtains a read-only auth token, sends the two
planned requests to a locally-running DummyJSON, greps the captured API server log and
the per-downstream-service logs for the correlation id (and any auto-generated UUID), and
records the REAL observed behavior per scenario.

DummyJSON is tested AS-IS and never modified. The single POST is its simulated,
non-persisting create (MONGODB_URI unset); auth login is read-only.

The recorded per-scenario observed token is the ground truth. Agents are later ranked on
how faithfully their own runs reproduce this table (coverage + correct plan construction).
The idealized contract lives in cid_spec.IDEAL; where the real token differs from the ideal
is a genuine QA finding about DummyJSON (it propagates no correlation id at all -> 0%).

Outputs (all under data/validate-correlation-id-propagation/):
  - cid_spec.json   the contract the agents are briefed from (INPUT)
  - gold/reference.json  the reference plan + per-scenario gold
  - gold.json            consolidated gold table + empirical propagation summary

Usage:
  BASE_URL=http://localhost:8899 FORGE_API_LOG_PATH=/path/api.log python3 build_gold.py
Stdlib only. No network beyond BASE_URL (read-only auth + the two requests). Air-gapped.
"""
import json
import os
import re
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
API_LOG_PATH = os.environ.get("FORGE_API_LOG_PATH", "")
DOWNSTREAM_LOG_DIR = os.environ.get("FORGE_DOWNSTREAM_LOG_DIR", "")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import cid_spec  # noqa: E402

FIXED_POST_BODY = {"title": "forge-corr-probe"}
CREDS = {"username": "emilys", "password": "emilyspass"}


def _login_token() -> str | None:
    body = json.dumps(CREDS).encode()
    req = urllib.request.Request(f"{BASE_URL}/auth/login", data=body, method="POST",
                                 headers={"Content-Type": "application/json"})
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            data = json.loads(r.read())
        return data.get("accessToken") or data.get("token")
    except Exception:  # noqa
        return None


def _send(method: str, path: str, headers: dict, body: dict | None):
    data = json.dumps(body).encode() if body is not None else None
    h = dict(headers)
    if data is not None:
        h.setdefault("Content-Type", "application/json")
    req = urllib.request.Request(f"{BASE_URL}{path}", data=data, method=method, headers=h)
    try:
        with urllib.request.urlopen(req, timeout=20) as r:
            return r.getcode(), {k: v for k, v in r.getheaders()}
    except urllib.error.HTTPError as e:
        return e.code, {k: v for k, v in (e.headers.items() if e.headers else [])}
    except Exception:  # noqa
        return -1, {}


def _header_value(resp_headers: dict, name: str) -> str | None:
    low = {str(k).lower(): v for k, v in (resp_headers or {}).items()}
    return low.get(str(name).lower())


def _read_log(path: str) -> list[str]:
    if not path or not Path(path).exists():
        return []
    try:
        return Path(path).read_text(errors="replace").splitlines()
    except Exception:  # noqa
        return []


def _hits(lines, needle) -> int:
    return sum(1 for ln in lines if needle and needle in ln)


def _downstream_path(svc: str) -> str:
    return str(Path(DOWNSTREAM_LOG_DIR) / f"{svc}.log") if DOWNSTREAM_LOG_DIR else ""


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from — the contract WITHOUT the plan."""
    return {
        "title": "DummyJSON correlation-ID propagation contract (authored for the propagation task)",
        "description": "A single endpoint carries a known X-Correlation-ID; the contract requires "
                       "the identical id to appear in the response header, the API server log, and "
                       "every downstream service log, and a no-header request to auto-generate a "
                       "UUID v4. Agents construct the propagation test plan from this; ground truth "
                       "is the live API's observed behavior. DummyJSON is never modified.",
        "target": BASE_URL,
        "correlation_id": cid_spec.CORR_ID,
        "header_name": cid_spec.HEADER_NAME,
        "endpoint": cid_spec.ENDPOINT,
        "downstream_services": cid_spec.DOWNSTREAM_SERVICES,
        "uuid_v4_regex": cid_spec.UUID_V4_REGEX,
        "auth": {"login_endpoint": {"method": "POST", "path": "/auth/login"},
                 "scheme": "Bearer", "creds": CREDS,
                 "token_placeholder": cid_spec.TOKEN_PLACEHOLDER},
    }


def run_reference():
    """Execute the canonical reference plan against the live API + captured logs."""
    plan = cid_spec.build_reference_plan()
    uuid_re = re.compile(cid_spec.UUID_V4_REGEX)
    token = _login_token()
    obs = {"with_request_sent": False, "no_header_request_sent": False}
    reqlog = []

    def _resolve(headers):
        return {k: (v.replace("<valid_token>", token) if token and isinstance(v, str)
                    and "<valid_token>" in v else v) for k, v in headers.items()}

    wr = plan["with_header_request"]
    status, rh = _send(wr["method"], wr["path"], _resolve(wr["headers"]), FIXED_POST_BODY)
    obs["with_request_sent"] = True
    obs["resp_header_value"] = _header_value(rh, cid_spec.HEADER_NAME)
    reqlog.append({"phase": "with_header", "status": status,
                   "resp_header_value": obs["resp_header_value"]})

    nr = plan["no_header_request"]
    status, rh = _send(nr["method"], nr["path"], _resolve(nr["headers"]), FIXED_POST_BODY)
    obs["no_header_request_sent"] = True
    gen = _header_value(rh, cid_spec.HEADER_NAME)
    obs["no_header_resp_value"] = gen
    obs["no_header_is_uuid_v4"] = bool(gen and uuid_re.match(gen))
    reqlog.append({"phase": "no_header", "status": status, "resp_header_value": gen})

    time.sleep(1.0)
    api_lines = _read_log(API_LOG_PATH)
    inv_lines = _read_log(_downstream_path("inventory-service"))
    pay_lines = _read_log(_downstream_path("payment-service"))

    obs["api_log_hits_corr"] = _hits(api_lines, cid_spec.CORR_ID)
    obs["api_log_corr_unmodified"] = any(cid_spec.CORR_ID in ln for ln in api_lines)
    obs["inventory_log_hits_corr"] = _hits(inv_lines, cid_spec.CORR_ID)
    obs["payment_log_hits_corr"] = _hits(pay_lines, cid_spec.CORR_ID)
    obs["downstream_services_observed"] = sum(
        1 for svc in cid_spec.DOWNSTREAM_SERVICES
        if _downstream_path(svc) and Path(_downstream_path(svc)).exists())

    if gen and obs["no_header_is_uuid_v4"]:
        obs["api_log_hits_uuid"] = _hits(api_lines, gen)
        obs["inventory_log_hits_uuid"] = _hits(inv_lines, gen)
        obs["payment_log_hits_uuid"] = _hits(pay_lines, gen)
    else:
        obs["api_log_hits_uuid"] = obs["inventory_log_hits_uuid"] = obs["payment_log_hits_uuid"] = 0

    return plan, obs, reqlog, bool(token)


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    (HERE / "cid_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    plan, obs, reqlog, got_token = run_reference()
    observed = cid_spec.evaluate(obs)

    scenarios = []
    total = correct = propagated = 0
    findings = []
    for label in cid_spec.SCENARIO_LABELS:
        tok = observed.get(label, "missing")
        ok = cid_spec.correct(label, tok)
        scenarios.append({"scenario": label, "ideal": cid_spec.IDEAL[label],
                          "observed_token": tok, "api_correct": ok})
        total += 1
        correct += 1 if ok else 0
        propagated += 1 if tok == "true" else 0
        if not ok:
            findings.append({"scenario": label, "ideal": cid_spec.IDEAL[label], "observed": tok})

    reference = {"reference_plan": plan, "observations": obs, "request_log": reqlog,
                 "scenarios": scenarios, "token_obtained": got_token}
    (GOLD_DIR / "reference.json").write_text(json.dumps(reference, indent=2))

    rate = round(100.0 * propagated / total, 2) if total else None
    summary = {
        "target": BASE_URL,
        "scenarios_total": total,
        "scenarios_propagated": propagated,
        "api_correct_scenarios": correct,
        "empirical_correlation_id_propagation_rate_pct": rate,
        "qa_findings": findings,
        "note": "Ground truth = live DummyJSON observed token per scenario. DummyJSON sets no "
                "X-Correlation-ID on responses, its request logger records no headers/correlation "
                "id, it calls no downstream services, and it auto-generates no UUID for a no-header "
                "request -> propagation rate 0%. That is a real QA finding, not an agent failure.",
    }
    # The gold table the judge/agents are scored against uses the SAME 'collections'
    # envelope shape as the other tasks, with one synthetic entry for this single-endpoint task.
    consolidated = [{"collection": cid_spec.ENDPOINT["path"], "scenarios": scenarios}]
    (HERE / "gold.json").write_text(json.dumps(
        {"summary": summary, "reference": reference, "collections": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
