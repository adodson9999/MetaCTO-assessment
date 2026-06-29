#!/usr/bin/env python3
"""Gold-set builder for the API IP-allowlist-enforcement testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors the
restricted-endpoint catalogue + the agents' input spec (ip_allowlist_spec.json), derives
the canonical correct IP-allowlist plan per endpoint, executes that plan against the
locally-running ip-allowlist-gateway (setting the edge-verified source IP, the spoofable
X-Forwarded-For, and the allowlist add/remove management actions exactly as each case
specifies), and records the REAL observed behavior (status code + whether protected
resource data leaked) per scenario.

The target is the local gateway, never DummyJSON (DummyJSON has no IP allowlist and is
never modified). The gateway's COMPLIANT endpoints enforce correctly; its
DELIBERATELY-VULNERABLE endpoints honor a spoofed X-Forwarded-For, so the recorded ground
truth includes a real critical bypass (the xff_spoof_rejected case returns 200 instead of
403) — a legitimate QA finding the suite must catch, mirroring how timeout-gateway seeds
one non-compliant endpoint. The idealized contract lives in ip_allowlist_spec.ideal_for();
where the real token differs from the ideal is the finding.

Outputs (all under data/test-ip-allowlist-enforcement/):
  - ip_allowlist_spec.json   the endpoint catalogue the agents are briefed from (INPUT)
  - gold/<endpoint>.json     per-endpoint gold scenarios
  - gold.json                consolidated gold table + empirical summary

Usage:
  BASE_URL=http://127.0.0.1:8913 python3 build_gold.py
Stdlib only. No network beyond BASE_URL (the local gateway).
"""
import json
import os
import sys
import time
import urllib.request
import urllib.error
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://127.0.0.1:8913").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
import ip_allowlist_spec  # noqa: E402

SUCCESS_CODE = ip_allowlist_spec.DEFAULT_SUCCESS_CODE  # 200
FORBIDDEN_CODE = ip_allowlist_spec.DEFAULT_FORBIDDEN_CODE  # 403
EDGE_IP_HEADER = ip_allowlist_spec.EDGE_IP_HEADER
XFF_HEADER = ip_allowlist_spec.XFF_HEADER
MGMT_PATH = ip_allowlist_spec.MGMT_ALLOWLIST_PATH
METHOD = "GET"
SCOPE_HEADER = "X-Waf-Scope"

# Documentation-only RFC 5737 test addresses.
ALLOW_IP = "203.0.113.10"   # on the allowlist
BLOCK_IP = "198.51.100.23"  # not on the allowlist

# Restricted endpoints. COMPLIANT enforce on the edge-verified IP; VULNERABLE honor a
# spoofed X-Forwarded-For (seeded defect so the suite has a real bypass to catch).
ENDPOINTS = [
    {"endpoint": "/restricted/orders",         "compliant": True},
    {"endpoint": "/restricted/invoices",       "compliant": True},
    {"endpoint": "/restricted/audit-log",      "compliant": True},
    {"endpoint": "/restricted/billing",        "compliant": True},
    {"endpoint": "/restricted/legacy-reports", "compliant": False},
    {"endpoint": "/restricted/partner-feed",   "compliant": False},
]


def _cfg(entry: dict) -> dict:
    scope = "ipset-" + entry["endpoint"].strip("/").replace("/", "-")
    return {
        "endpoint": entry["endpoint"], "method": METHOD,
        "success_code": SUCCESS_CODE, "forbidden_code": FORBIDDEN_CODE,
        "allow_ip": ALLOW_IP, "block_ip": BLOCK_IP,
        "edge_ip_header": EDGE_IP_HEADER, "xff_header": XFF_HEADER,
        "mgmt_allowlist_path": MGMT_PATH, "waf_scope": scope,
    }


def _request(method: str, path: str, headers=None, body=None, _retries=2):
    url = f"{BASE_URL}{path}"
    data = json.dumps(body).encode() if body is not None else None
    for attempt in range(_retries + 1):
        req = urllib.request.Request(url, data=data, method=method)
        if data is not None:
            req.add_header("Content-Type", "application/json")
        for k, v in (headers or {}).items():
            if k and v is not None:
                req.add_header(k, str(v))
        try:
            with urllib.request.urlopen(req, timeout=15) as r:
                raw = r.read()
                try:
                    return r.getcode(), json.loads(raw or b"{}")
                except Exception:  # noqa
                    return r.getcode(), {}
        except urllib.error.HTTPError as e:
            try:
                return e.code, json.loads(e.read() or b"{}")
            except Exception:  # noqa
                return e.code, {}
        except Exception:  # noqa
            if attempt < _retries:
                time.sleep(0.5 * (attempt + 1))
    return -1, {}


def _data_exposed(body: dict) -> bool:
    return isinstance(body, dict) and ("records" in body or "secret" in json.dumps(body))


def _resolve(cfg, token):
    return {"allow_ip": cfg["allow_ip"], "block_ip": cfg["block_ip"]}.get(token)


def run_reference_plan(cfg: dict):
    """Execute the canonical correct plan against the live gateway. Returns obs +
    request log on the same key scheme ip_allowlist_spec.evaluate expects."""
    scope = f"gold:{cfg['waf_scope']}"
    plan = ip_allowlist_spec.build_reference_plan(cfg)
    obs = {label: {"ran": False, "code": None, "data_exposed": None}
           for label in ip_allowlist_spec.CASE_LABELS}
    reqlog = []

    _request("POST", "/__waf/reset", body={"scope": scope, "ips": [cfg["allow_ip"]]})

    for case in plan["cases"]:
        action = case["mgmt_action"]
        if action == "add_block_ip":
            _request("PUT", MGMT_PATH, body={"scope": scope, "ip": cfg["block_ip"]})
        elif action == "remove_block_ip":
            _request("DELETE", MGMT_PATH, body={"scope": scope, "ip": cfg["block_ip"]})

        headers = {SCOPE_HEADER: scope, cfg["edge_ip_header"]: _resolve(cfg, case["source_ip"])}
        xff_val = _resolve(cfg, case["send_xff"]) if case["send_xff"] else None
        if xff_val is not None:
            headers[cfg["xff_header"]] = xff_val

        code, body = _request(METHOD, cfg["endpoint"], headers=headers)
        exposed = _data_exposed(body)
        obs[case["label"]] = {"ran": True, "code": code, "data_exposed": exposed}
        reqlog.append({"label": case["label"], "source_ip": case["source_ip"],
                       "sent_xff": xff_val, "mgmt_action": action,
                       "status": code, "data_exposed": exposed})
    return obs, reqlog


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each endpoint's allowlist
    contract WITHOUT the answer plan."""
    return {
        "title": "IP-allowlist contract (authored for the IP-allowlist-enforcement testing task)",
        "description": "Each restricted endpoint is fronted by an IP allowlist (an AWS-WAF-style "
                       "IP set). An allowlisted source IP must receive success_code with the "
                       "resource data; a non-allowlisted source IP must receive forbidden_code "
                       "with no resource data; the allowlist decision must NOT honor the "
                       "X-Forwarded-For header; and the management API can add/remove an IP from "
                       "the set. Agents construct the IP-allowlist test plan from this; ground "
                       "truth is the live local gateway's observed behavior. DummyJSON is never "
                       "used or modified — the target is the local ip-allowlist-gateway.",
        "target": BASE_URL,
        "method": METHOD,
        "success_code": SUCCESS_CODE,
        "forbidden_code": FORBIDDEN_CODE,
        "allow_ip": ALLOW_IP,
        "block_ip": BLOCK_IP,
        "edge_ip_header": EDGE_IP_HEADER,
        "xff_header": XFF_HEADER,
        "mgmt_allowlist_path": MGMT_PATH,
        "endpoints": [
            {"endpoint": e["endpoint"], "allow_ip": ALLOW_IP, "block_ip": BLOCK_IP,
             "waf_scope": "ipset-" + e["endpoint"].strip("/").replace("/", "-")}
            for e in ENDPOINTS
        ],
    }


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    try:
        urllib.request.urlopen(BASE_URL + "/__health", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: gateway not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    (HERE / "ip_allowlist_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    total = correct = 0
    any_bypass = False
    findings = {}
    for entry in ENDPOINTS:
        cfg = _cfg(entry)
        raw, reqlog = run_reference_plan(cfg)
        observed = ip_allowlist_spec.evaluate(raw)

        scenarios = []
        ep_correct = 0
        for label in ip_allowlist_spec.CASE_LABELS:
            tok = observed.get(label, "missing")
            ok = ip_allowlist_spec.correct(label, tok)
            scenarios.append({"scenario": label, "ideal": ip_allowlist_spec.ideal_for(label),
                              "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0
            ep_correct += 1 if ok else 0
            if label in ("nonallowlisted_baseline", "xff_spoof_rejected",
                         "allowlist_remove_blocks") and tok.startswith("200"):
                any_bypass = True
        findings[cfg["endpoint"]] = f"{ep_correct}/{len(ip_allowlist_spec.CASE_LABELS)}"

        rec = {"endpoint": cfg["endpoint"], "waf_scope": cfg["waf_scope"],
               "allow_ip": cfg["allow_ip"], "block_ip": cfg["block_ip"],
               "documented_compliant": entry["compliant"],
               "reference_plan": ip_allowlist_spec.build_reference_plan(cfg),
               "request_log": reqlog, "scenarios": scenarios}
        (GOLD_DIR / (cfg["endpoint"].strip("/").replace("/", "-") + ".json")).write_text(
            json.dumps(rec, indent=2))
        consolidated.append(rec)

    rate = round(100.0 * correct / total, 2) if total else None
    summary = {
        "target": BASE_URL,
        "endpoints": len(ENDPOINTS),
        "scenarios_per_endpoint": len(ip_allowlist_spec.CASE_LABELS),
        "total_scenarios": total,
        "api_correct_scenarios": correct,
        "empirical_ip_allowlist_enforcement_rate_pct": rate,
        "any_nonallowlisted_200_bypass": any_bypass,
        "headline_pass": (correct == total and not any_bypass),
        "per_endpoint_correct": findings,
        "note": "Ground truth = live local gateway observed token per (endpoint, scenario). "
                "The four COMPLIANT endpoints enforce the allowlist on the edge-verified IP and "
                "ignore X-Forwarded-For, so all five cases pass. The two VULNERABLE endpoints "
                "(legacy-reports, partner-feed) honor a spoofed X-Forwarded-For, so the "
                "xff_spoof_rejected case returns 200+data instead of 403 — a CRITICAL bypass "
                "(a non-allowlisted IP reaching the resource). Those are seeded defects so the "
                "metric is non-degenerate and the suite's catch-rate is demonstrated. Headline "
                "IP Allowlist Enforcement = FAIL (a non-allowlisted IP receives 200 via XFF "
                "spoofing on two endpoints).",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "endpoints": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
