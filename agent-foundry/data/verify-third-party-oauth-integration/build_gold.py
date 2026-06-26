#!/usr/bin/env python3
"""Gold-set builder for the Verify-Third-Party-OAuth-Integration testing task.

This is NOT one of the four agents. It is the deterministic *reference*: it authors
the OAuth flow catalogue + the agents' input spec (oauth_spec.json), derives the
canonical correct 5-stage plan per flow, executes that plan against a locally-running
DummyJSON, and records the REAL observed behavior per assertion (the redirect status &
parsed Location params, the callback code/state, the token-exchange body, the userinfo
profile, and the refresh outcome).

DummyJSON is tested AS-IS and never modified, per the Phase-2 owner decision. It ships
NO OAuth2 authorization-code flow (no /auth/oauth/<provider> redirect, no /auth/callback,
no code-exchange /auth/token, no OAuth refresh-token grant), so the recorded ground
truth is that every stage fails the idealized contract — a legitimate QA finding,
mirroring how the webhook/header-propagation builds surfaced absent features. The
idealized contract lives in oauth_spec.ideal_for(); where the real token differs from
the ideal is the finding. Headline OAuth Flow Completion Rate = 0%.

Outputs (all under data/verify-third-party-oauth-integration/):
  - oauth_spec.json     the OAuth flow catalogue the agents are briefed from (INPUT)
  - gold/<provider>.json per-flow gold assertions
  - gold.json           consolidated gold table + empirical summary

Usage:
  BASE_URL=http://localhost:8899 python3 build_gold.py
Stdlib only. No network beyond BASE_URL. The cloud LLM backend is NOT used here — the
gold reference is pure deterministic code.
"""
import json
import os
import sys
from pathlib import Path

BASE_URL = os.environ.get("BASE_URL", "http://localhost:8899").rstrip("/")
HERE = Path(__file__).resolve().parent
GOLD_DIR = HERE / "gold"

# Shared structure (one source of truth with the agent harness).
sys.path.insert(0, str(HERE.parents[1] / "agents" / "common"))
os.environ.setdefault("FORGE_TARGET_BASE_URL", BASE_URL)
os.environ["FORGE_WORKSPACE"] = str(HERE.parents[1])
import oauth_spec  # noqa: E402
import oauth as oauth_harness  # noqa: E402  (reuse the harness's flow executor for identical semantics)

# The five documented OAuth endpoints (the idealized contract, shared by every flow).
AUTHORIZE_TMPL = "/auth/oauth/{provider}"
CALLBACK_ENDPOINT = "/auth/callback"
TOKEN_ENDPOINT = "/auth/token"
USERINFO_ENDPOINT = "/me"
REFRESH_ENDPOINT = "/auth/refresh"
STATE_MIN_LENGTH = oauth_spec.MIN_STATE_LENGTH

# Three configured third-party OAuth integrations tested as-is. Each is an independent
# flow with its own client_id / redirect_uri / scope.
FLOWS = [
    {"provider": "google", "client_id": "forge-google-client-id",
     "redirect_uri": "https://app.forge.local/auth/callback/google",
     "scope": "openid email profile"},
    {"provider": "github", "client_id": "forge-github-client-id",
     "redirect_uri": "https://app.forge.local/auth/callback/github",
     "scope": "read:user user:email"},
    {"provider": "facebook", "client_id": "forge-facebook-client-id",
     "redirect_uri": "https://app.forge.local/auth/callback/facebook",
     "scope": "email public_profile"},
]


def _cfg(entry: dict) -> dict:
    return {
        "provider": entry["provider"],
        "authorize_endpoint": AUTHORIZE_TMPL.format(provider=entry["provider"]),
        "callback_endpoint": CALLBACK_ENDPOINT,
        "token_endpoint": TOKEN_ENDPOINT,
        "userinfo_endpoint": USERINFO_ENDPOINT,
        "refresh_endpoint": REFRESH_ENDPOINT,
        "client_id": entry["client_id"],
        "redirect_uri": entry["redirect_uri"],
        "scope": entry["scope"],
        "state_min_length": STATE_MIN_LENGTH,
    }


def build_input_spec() -> dict:
    """The INPUT the four agents are briefed from. Describes each flow's OAuth contract
    WITHOUT the answer plan."""
    return {
        "title": "Third-party OAuth2 authorization-code contract "
                 "(authored for the verify-third-party-oauth-integration testing task)",
        "description": "Each flow is documented to run the OAuth2 authorization-code flow in "
                       "five stages: (1) authorize 302-redirect to the provider with client_id/"
                       "redirect_uri/scope/state; (2) approval returns to the callback with code+"
                       "state (CSRF); (3) token exchange -> 200 with access_token/token_type Bearer/"
                       "refresh_token/expires_in; (4) userinfo -> 200 with a non-empty profile field; "
                       "(5) refresh -> 200 with a new access_token, and userinfo with it -> 200. Agents "
                       "construct the 5-stage test plan from this; ground truth is the live API's observed "
                       "behavior. DummyJSON is tested as-is and never modified, and ships no OAuth "
                       "authorization-code flow, so the observed behavior is the QA finding.",
        "target": BASE_URL,
        "authorize_endpoint": AUTHORIZE_TMPL.format(provider="<provider>"),
        "callback_endpoint": CALLBACK_ENDPOINT,
        "token_endpoint": TOKEN_ENDPOINT,
        "userinfo_endpoint": USERINFO_ENDPOINT,
        "refresh_endpoint": REFRESH_ENDPOINT,
        "state_min_length": STATE_MIN_LENGTH,
        "flows": [
            {"provider": e["provider"],
             "authorize_endpoint": AUTHORIZE_TMPL.format(provider=e["provider"]),
             "callback_endpoint": CALLBACK_ENDPOINT,
             "token_endpoint": TOKEN_ENDPOINT,
             "userinfo_endpoint": USERINFO_ENDPOINT,
             "refresh_endpoint": REFRESH_ENDPOINT,
             "client_id": e["client_id"], "redirect_uri": e["redirect_uri"],
             "scope": e["scope"]}
            for e in FLOWS
        ],
    }


def main():
    GOLD_DIR.mkdir(parents=True, exist_ok=True)

    # health gate
    import urllib.request
    try:
        urllib.request.urlopen(BASE_URL + "/test", timeout=5)
    except Exception as e:  # noqa
        print(f"FATAL: target API not reachable at {BASE_URL} ({e})", file=sys.stderr)
        sys.exit(2)

    (HERE / "oauth_spec.json").write_text(json.dumps(build_input_spec(), indent=2))

    consolidated = []
    total = correct = 0
    flows_complete = 0
    stage_pass_counts = {s["name"]: 0 for s in oauth_spec.STAGE_DEFS}

    for entry in FLOWS:
        cfg = _cfg(entry)
        # Execute the canonical CORRECT plan through the SAME harness executor the agents
        # use, so gold semantics are byte-identical to agent semantics.
        plan = oauth_spec.build_reference_plan(cfg)
        raw, reqlog = oauth_harness._exec_flow(cfg, plan)
        observed = oauth_spec.evaluate(raw)

        assertions = []
        for label in oauth_spec.SCENARIO_LABELS:
            tok = observed.get(label, "missing")
            ok = oauth_spec.correct(label, tok)
            assertions.append({"scenario": label, "ideal": oauth_spec.ideal_for(label),
                               "observed_token": tok, "api_correct": ok})
            total += 1
            correct += 1 if ok else 0

        stages = []
        for s in oauth_spec.STAGE_DEFS:
            sc = oauth_spec.stage_correct(s["stage"], observed)
            if sc:
                stage_pass_counts[s["name"]] += 1
            stages.append({"stage": s["stage"], "name": s["name"], "stage_correct": sc})

        complete = oauth_spec.flow_complete(observed)
        if complete:
            flows_complete += 1

        rec = {
            "provider": cfg["provider"], "client_id": cfg["client_id"],
            "redirect_uri": cfg["redirect_uri"], "scope": cfg["scope"],
            "flow_complete": complete, "stages": stages,
            "reference_plan": plan, "request_log": reqlog, "assertions": assertions,
        }
        (GOLD_DIR / f"{entry['provider']}.json").write_text(json.dumps(rec, indent=2))
        consolidated.append(rec)

    n = len(FLOWS)
    completion_rate = round(100.0 * flows_complete / n, 2) if n else None
    assertion_rate = round(100.0 * correct / total, 2) if total else None
    summary = {
        "target": BASE_URL,
        "flows": n,
        "assertions_per_flow": len(oauth_spec.SCENARIO_LABELS),
        "total_assertions": total,
        "api_correct_assertions": correct,
        "empirical_oauth_flow_completion_rate_pct": completion_rate,
        "empirical_assertion_correctness_rate_pct": assertion_rate,
        "flows_complete": flows_complete,
        "stage_pass_counts": stage_pass_counts,
        "note": "Ground truth = live DummyJSON observed token per (flow, assertion). DummyJSON "
                "ships no OAuth2 authorization-code flow, so the authorize endpoint does not 302 "
                "to a provider, no authorization code is ever issued, the token-exchange endpoint "
                "does not return OAuth tokens, and the refresh endpoint is JWT-session refresh, "
                "not an OAuth refresh-token grant. Every stage fails the idealized contract, so the "
                "headline OAuth Flow Completion Rate = 0% by design — those gaps are real QA "
                "findings (no third-party OAuth integration exists), not agent failures.",
    }
    (HERE / "gold.json").write_text(json.dumps({"summary": summary, "flows": consolidated}, indent=2))
    print(json.dumps(summary, indent=2))


if __name__ == "__main__":
    main()
