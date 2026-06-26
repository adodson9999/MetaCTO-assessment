"""Canonical scenario structure for the API IP-allowlist-enforcement testing task.

ONE definition of the IP-allowlist test plan + the per-scenario evaluation, shared by:
  - the deterministic gold reference (data/test-ip-allowlist-enforcement/build_gold.py), and
  - the harness (agents/common/ip_allowlist.py) — which executes whatever plan an agent
    emitted and scores it on exactly the same scenario-key scheme.

Pure: no env, no I/O, no LLM. Keeps agent output and the gold set on the same
(endpoint, scenario) key scheme so the judge can compare them field-for-field.

Target reality (the local ip-allowlist-gateway, never DummyJSON):
  - COMPLIANT restricted endpoints enforce the allowlist on the edge-verified source IP
    and ignore X-Forwarded-For, so every scenario matches the ideal contract.
  - DELIBERATELY-VULNERABLE endpoints honor a spoofed X-Forwarded-For, so the
    `xff_spoof_rejected` scenario returns 200 instead of 403 — a real, critical bypass
    the suite must CATCH. Where the real token differs from `ideal` is the QA finding.

The five canonical enforcement cases, in execution order (later cases mutate the
allowlist for THIS endpoint's scope; the harness resets the scope to {ALLOW_IP} first):

  1. allowlisted_baseline    ALLOW_IP, no XFF, no mgmt          -> ideal 200 + data
  2. nonallowlisted_baseline BLOCK_IP, no XFF, no mgmt          -> ideal 403 + no data
  3. xff_spoof_rejected      BLOCK_IP, XFF=ALLOW_IP, no mgmt    -> ideal 403 + no data
  4. allowlist_add_allows    add BLOCK_IP, then BLOCK_IP        -> ideal 200 + data
  5. allowlist_remove_blocks remove BLOCK_IP, then BLOCK_IP     -> ideal 403 + no data

A plan for one endpoint (the agent's output, and the reference) looks like:
  {
    "endpoint": "/restricted/orders", "method": "GET",
    "success_code": 200, "forbidden_code": 403,
    "allow_ip": "203.0.113.10", "block_ip": "198.51.100.23",
    "edge_ip_header": "X-Edge-Verified-IP", "xff_header": "X-Forwarded-For",
    "mgmt_allowlist_path": "/__waf/allowlist", "waf_scope": "ipset-orders",
    "cases": [ {case}, {case}, {case}, {case}, {case} ]
  }
where each case is:
  {"label": "...", "source_ip": "allow_ip"|"block_ip",
   "send_xff": "allow_ip"|null, "mgmt_action": "none"|"add_block_ip"|"remove_block_ip",
   "expect_code": 200|403, "expect_data": true|false}
"""
from __future__ import annotations

DEFAULT_SUCCESS_CODE = 200
DEFAULT_FORBIDDEN_CODE = 403
EDGE_IP_HEADER = "X-Edge-Verified-IP"
XFF_HEADER = "X-Forwarded-For"
MGMT_ALLOWLIST_PATH = "/__waf/allowlist"

# The full, ordered case set scored per endpoint (the metric denominator). Each entry:
#   (label, source_ip, send_xff, mgmt_action, ideal_code, ideal_data)
CASES = [
    ("allowlisted_baseline",    "allow_ip", None,       "none",             200, True),
    ("nonallowlisted_baseline", "block_ip", None,       "none",             403, False),
    ("xff_spoof_rejected",      "block_ip", "allow_ip", "none",             403, False),
    ("allowlist_add_allows",    "block_ip", None,       "add_block_ip",     200, True),
    ("allowlist_remove_blocks", "block_ip", None,       "remove_block_ip",  403, False),
]
CASE_LABELS = [c[0] for c in CASES]


def _token(code: int | None, data: bool | None) -> str:
    """Collapse (status code, data-exposed) to the comparison token.
    Code class: 200 for any 2xx, 403 exact, 'none' for no response, else 'other_<n>'.
    Data flag: 'data' when the protected payload was returned, else 'nodata'."""
    if code is None:
        return "none"
    if 200 <= code < 300:
        cls = "200"
    elif code == 403:
        cls = "403"
    else:
        cls = f"other_{code}"
    flag = "data" if data else "nodata"
    return f"{cls}:{flag}"


def ideal_for(label: str) -> str:
    """The idealized token a correctly-enforcing allowlist would produce for a case."""
    for lbl, _src, _xff, _mgmt, code, data in CASES:
        if lbl == label:
            return _token(code, data)
    raise KeyError(label)


def build_reference_plan(cfg: dict) -> dict:
    """The canonical CORRECT plan for one endpoint, derived deterministically from its
    config: the five fixed enforcement cases in order."""
    return {
        "endpoint": cfg["endpoint"],
        "method": cfg.get("method", "GET"),
        "success_code": cfg.get("success_code", DEFAULT_SUCCESS_CODE),
        "forbidden_code": cfg.get("forbidden_code", DEFAULT_FORBIDDEN_CODE),
        "allow_ip": cfg["allow_ip"],
        "block_ip": cfg["block_ip"],
        "edge_ip_header": cfg.get("edge_ip_header", EDGE_IP_HEADER),
        "xff_header": cfg.get("xff_header", XFF_HEADER),
        "mgmt_allowlist_path": cfg.get("mgmt_allowlist_path", MGMT_ALLOWLIST_PATH),
        "waf_scope": cfg["waf_scope"],
        "cases": [
            {"label": lbl, "source_ip": src, "send_xff": xff, "mgmt_action": mgmt,
             "expect_code": code, "expect_data": data}
            for (lbl, src, xff, mgmt, code, data) in CASES
        ],
    }


def evaluate(obs: dict) -> dict:
    """Compute the observed token for every case from raw harness observations.

    obs maps case label -> {"code": int|None, "data_exposed": bool|None, "ran": bool}.
    A case the agent never emitted (not run) scores 'missing' (a mismatch vs gold).

    Returns {case_label: observed_token}.
    """
    out: dict[str, str] = {}
    for label in CASE_LABELS:
        rec = obs.get(label)
        if not rec or not rec.get("ran"):
            out[label] = "missing"
            continue
        out[label] = _token(rec.get("code"), bool(rec.get("data_exposed")))
    return out


def correct(label: str, observed_token: str) -> bool:
    """Did the API enforce the allowlist per the ideal contract for this case?"""
    return observed_token == ideal_for(label)
